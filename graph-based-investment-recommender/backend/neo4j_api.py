from flask import Flask, jsonify, send_from_directory, request
from neo4j import GraphDatabase
import traceback

app = Flask(__name__)

# -----------------------------
# Neo4j Connection
# -----------------------------
uri = "bolt://localhost:7687"
username = "neo4j"
password = "testpassword" 
driver = GraphDatabase.driver(uri, auth=(username, password))

# -----------------------------
# Utilities
# -----------------------------
def graph_exists(session, graph_name):
    try:
        r = session.run(
            f"CALL gds.graph.exists('{graph_name}') "
            "YIELD exists RETURN exists"
        ).single()
        return bool(r and r["exists"])
    except:
        return False


def create_co_invest_graph(session, graph_name="investorCoInvest"):

    if graph_exists(session, graph_name):
        try:
            session.run(f"CALL gds.graph.drop('{graph_name}', false)")
        except:
            pass

    cypher_nodes = """
        MATCH (i:Investor) 
        RETURN id(i) AS id
    """

    cypher_rels = """
        MATCH (i1:Investor)-[:INVESTS_IN]->(a:Asset)<-[:INVESTS_IN]-(i2:Investor)
        WHERE id(i1) <> id(i2)
        RETURN id(i1) AS source, id(i2) AS target
    """

    session.run(
        "CALL gds.graph.project.cypher("
        "$graph_name, $nodeQuery, $relQuery)",
        graph_name=graph_name,
        nodeQuery=cypher_nodes,
        relQuery=cypher_rels
    )

    return True


# -----------------------------
# Serve Frontend
# -----------------------------
@app.route('/')
def serve_frontend():
    return send_from_directory('static', 'index.html')


# -----------------------------
# Top Investors
# -----------------------------
@app.route("/top_investors")
def top_investors():

    query = """
    MATCH (i:Investor)-[:INVESTS_IN]->(a:Asset)
    RETURN 
        i.name AS name, 
        i.risk_tolerance AS risk_tolerance, 
        count(a) AS investments
    ORDER BY investments DESC LIMIT 10
    """

    try:
        with driver.session() as session:
            rows = session.run(query)
            data = [dict(r) for r in rows]
        return jsonify(data)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# -----------------------------
# Similar Investors (shared assets)
# -----------------------------
@app.route("/similar_investors")
def similar_investors():

    query = """
    MATCH (i1:Investor)-[:INVESTS_IN]->(a:Asset)<-[:INVESTS_IN]-(i2:Investor)
    WHERE i1 <> i2
    WITH i1.name AS source, i2.name AS target, count(a) AS shared
    WHERE shared >= 2
    RETURN source, target, shared
    ORDER BY shared DESC LIMIT 200
    """

    try:
        with driver.session() as session:
            rows = session.run(query)
            return jsonify([dict(r) for r in rows])

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# -----------------------------
# Communities (Louvain)
# -----------------------------
@app.route("/communities")
def get_communities():

    graph_name = "investorCoInvest"

    try:
        with driver.session() as session:

            if not graph_exists(session, graph_name):
                create_co_invest_graph(session, graph_name)

            com_q = f"""
            CALL gds.louvain.stream('{graph_name}')
            YIELD nodeId, communityId
            RETURN 
                gds.util.asNode(nodeId).name AS name,
                communityId
            """

            rows = session.run(com_q).data()

            nodes = [
                {
                    "id": r["name"],
                    "name": r["name"],
                    "community": int(r["communityId"])
                }
                for r in rows
            ]

            # edges for UI
            edge_q = """
            MATCH (i1:Investor)-[:INVESTS_IN]->(a:Asset)<-[:INVESTS_IN]-(i2:Investor)
            WHERE i1 <> i2
            WITH DISTINCT i1.name AS source, i2.name AS target
            RETURN source, target LIMIT 1000
            """

            edges = [
                {"source": r["source"], "target": r["target"]}
                for r in session.run(edge_q).data()
            ]

        return jsonify({"nodes": nodes, "edges": edges})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# -----------------------------
# PageRank
# -----------------------------
@app.route("/pagerank")
def get_pagerank():

    graph_name = "investorCoInvest"

    try:
        with driver.session() as session:

            if not graph_exists(session, graph_name):
                create_co_invest_graph(session, graph_name)

            pr_q = f"""
            CALL gds.pageRank.stream('{graph_name}')
            YIELD nodeId, score
            RETURN 
                gds.util.asNode(nodeId).name AS investor,
                score
            ORDER BY score DESC LIMIT 50
            """

            rows = session.run(pr_q).data()
            data = [
                {"investor": r["investor"], "score": float(r["score"])}
                for r in rows
            ]

        return jsonify(data)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# -----------------------------
# Jaccard / Node Similarity
# -----------------------------
@app.route("/similarity")
def get_similarity():

    graph_name = "investorCoInvest"

    try:
        with driver.session() as session:

            if not graph_exists(session, graph_name):
                create_co_invest_graph(session, graph_name)

            sim_q = f"""
            CALL gds.nodeSimilarity.stream('{graph_name}')
            YIELD node1, node2, similarity
            RETURN 
                gds.util.asNode(node1).name AS investor1,
                gds.util.asNode(node2).name AS investor2,
                similarity
            ORDER BY similarity DESC LIMIT 50
            """

            rows = session.run(sim_q).data()

            # fallback if needed
            if not rows:
                fallback = """
                MATCH (a:Investor),(b:Investor)
                WHERE id(a) < id(b)
                WITH a,b,
                     size((a)-[:INVESTS_IN]->()<-[:INVESTS_IN]-(b)) AS inter,
                     size((a)-[:INVESTS_IN]->()) AS sa,
                     size((b)-[:INVESTS_IN]->()) AS sb
                WITH a,b,inter,(sa+sb-inter) AS u
                WHERE inter > 0 AND u > 0
                RETURN 
                    a.name AS investor1,
                    b.name AS investor2,
                    toFloat(inter)/u AS similarity
                ORDER BY similarity DESC LIMIT 50
                """
                rows = session.run(fallback).data()

            data = [
                {
                    "investor1": r["investor1"],
                    "investor2": r["investor2"],
                    "similarity": float(r["similarity"])
                }
                for r in rows
            ]

        return jsonify(data)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# -----------------------------
# Recommendations
# -----------------------------
@app.route("/recommendations/<investor>", methods=["GET"])
def recommend_investors(investor):

    try:
        with driver.session() as session:

            info_q = """
            MATCH (i:Investor {name: $investor})
            RETURN 
                i.name AS name,
                i.risk_tolerance AS risk,
                i.domain AS domain
            """

            info = session.run(info_q, {"investor": investor}).data()

            if not info:
                return jsonify({"error": f"Investor '{investor}' not found"}), 404

            risk = info[0]["risk"]
            domain = info[0]["domain"]

            # similar investors
            similar_q = """
            MATCH (i1:Investor {name: $investor})-[:INVESTS_IN]->(a:Asset)
                  <-[:INVESTS_IN]-(i2:Investor)
            WHERE i1 <> i2
            WITH i2, count(a) AS shared
            RETURN i2.name AS similar_investor, shared
            ORDER BY shared DESC LIMIT 5
            """

            similar = session.run(similar_q, {"investor": investor}).data()

            # recommendations
            rec_q = """
            MATCH (i:Investor {name: $investor})-[:INVESTS_IN]->(owned:Asset)
            WITH collect(owned) AS ownedList
            MATCH (i)-[:INVESTS_IN]->(:Asset)
                  <-[:INVESTS_IN]-(peer:Investor)-[:INVESTS_IN]->(a:Asset)
            WHERE NOT a IN ownedList
            RETURN DISTINCT a.name AS recommended_asset
            LIMIT 10
            """

            rec_assets = session.run(rec_q, {"investor": investor}).data()

            # community detection
            if not graph_exists(session, "investorCoInvest"):
                create_co_invest_graph(session)

            comm_q = """
            CALL gds.louvain.stream('investorCoInvest')
            YIELD nodeId, communityId
            WITH gds.util.asNode(nodeId) AS n, communityId
            WHERE n.name = $investor
            RETURN communityId
            """

            comm = session.run(comm_q, {"investor": investor}).data()
            community_id = comm[0]["communityId"] if comm else None

            peer_q = """
            CALL gds.louvain.stream('investorCoInvest')
            YIELD nodeId, communityId
            WITH gds.util.asNode(nodeId) AS n, communityId
            WHERE communityId = $cid AND n.name <> $target
            RETURN n.name AS peer LIMIT 10
            """

            community_peers = []
            if community_id is not None:
                community_peers = [
                    r["peer"]
                    for r in session.run(
                        peer_q, {"cid": community_id, "target": investor}
                    ).data()
                ]

            summary = {
                "investor": investor,
                "risk_tolerance": risk,
                "domain": domain,
                "similar_investors": [r["similar_investor"] for r in similar],
                "recommended_assets": [r["recommended_asset"] for r in rec_assets],
                "community_id": int(community_id) if community_id else None,
                "community_peers": community_peers
            }

            return jsonify(summary)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500



# -----------------------------
# Run App
# -----------------------------
if __name__ == "__main__":
    app.run(debug=True)
