from flask import Flask, jsonify, send_from_directory, request
from neo4j import GraphDatabase
import traceback

app = Flask(__name__)

# -----------------------------
# Neo4j Connection
# -----------------------------
uri = "bolt://localhost:7687"
username = "neo4j"
password = "testpassword"  # update if needed
driver = GraphDatabase.driver(uri, auth=(username, password))

# -----------------------------
# Utilities
# -----------------------------
def graph_exists(session, graph_name):
    # gds.graph.exists is available on GDS 1.5+ (Neo4j 5.x)
    try:
        r = session.run(f"CALL gds.graph.exists('{graph_name}') YIELD exists RETURN exists").single()
        return bool(r and r["exists"])
    except Exception:
        # older behaviour fallback
        return False

def create_co_invest_graph(session, graph_name="investorCoInvest"):
    """
    Creates a co-investor graph where nodes = Investor, and edges connect
    investors who invested in the same Asset (co-invest relationships).
    We use a Cypher projection so edges are investor->investor directly.
    """
    # Drop if exists then create cleanly (safe)
    if graph_exists(session, graph_name):
        try:
            session.run(f"CALL gds.graph.drop('{graph_name}', false)")
        except Exception:
            pass

    cypher_nodes = "MATCH (i:Investor) RETURN id(i) AS id"
    cypher_rels = """
    MATCH (i1:Investor)-[:INVESTS_IN]->(a:Asset)<-[:INVESTS_IN]-(i2:Investor)
    WHERE id(i1) <> id(i2)
    RETURN id(i1) AS source, id(i2) AS target
    """

    session.run(
        f"CALL gds.graph.project.cypher('{graph_name}', $nodeQuery, $relQuery)",
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
    RETURN i.name AS name, i.risk_tolerance AS risk_tolerance, count(a) AS investments
    ORDER BY investments DESC LIMIT 10
    """
    try:
        with driver.session() as session:
            result = session.run(query)
            data = [dict(record) for record in result]
        return jsonify(data)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# -----------------------------
# Similar Investors (shared investments simple view)
# -----------------------------
@app.route("/similar_investors")
def similar_investors():
    query = """
    MATCH (i1:Investor)-[:INVESTS_IN]->(a:Asset)<-[:INVESTS_IN]-(i2:Investor)
    WHERE i1 <> i2
    WITH i1.name AS source, i2.name AS target, count(a) AS shared
    WHERE shared >= 2
    RETURN source, target, shared
    LIMIT 200
    """
    try:
        with driver.session() as session:
            result = session.run(query)
            data = [dict(record) for record in result]
        return jsonify(data)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# -----------------------------
# Communities (Louvain on co-investor graph)
# -----------------------------
@app.route("/communities", methods=["GET"])
def get_communities():
    graph_name = "investorCoInvest"
    try:
        with driver.session() as session:
            # create projection if missing
            if not graph_exists(session, graph_name):
                create_co_invest_graph(session, graph_name)

            # Louvain
            q = f"""
            CALL gds.louvain.stream('{graph_name}')
            YIELD nodeId, communityId
            RETURN gds.util.asNode(nodeId).name AS name, communityId
            """
            rows = session.run(q).data()

            # nodes list
            nodes = [{"id": r["name"], "name": r["name"], "community": int(r["communityId"])} for r in rows]

            # create edges for visualization (co-invest edges)
            edge_q = """
            MATCH (i1:Investor)-[:INVESTS_IN]->(a:Asset)<-[:INVESTS_IN]-(i2:Investor)
            WHERE i1 <> i2
            WITH DISTINCT i1.name AS source, i2.name AS target
            RETURN source, target
            LIMIT 1000
            """
            edges = [{"source": e["source"], "target": e["target"]} for e in session.run(edge_q).data()]

        return jsonify({"nodes": nodes, "edges": edges})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# -----------------------------
# PageRank (Influence) on co-investor graph
# -----------------------------
@app.route("/pagerank", methods=["GET"])
def get_pagerank():
    graph_name = "investorCoInvest"
    try:
        with driver.session() as session:
            if not graph_exists(session, graph_name):
                create_co_invest_graph(session, graph_name)

            q = f"""
            CALL gds.pageRank.stream('{graph_name}')
            YIELD nodeId, score
            RETURN gds.util.asNode(nodeId).name AS investor, score
            ORDER BY score DESC
            LIMIT 50
            """
            rows = session.run(q).data()
            data = [{"investor": r["investor"], "score": float(r["score"])} for r in rows]
        return jsonify(data)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# -----------------------------
# Jaccard similarity (via GDS nodeSimilarity on co-investor graph)
# -----------------------------
@app.route("/similarity", methods=["GET"])
def get_similarity():
    graph_name = "investorCoInvest"
    try:
        with driver.session() as session:
            if not graph_exists(session, graph_name):
                create_co_invest_graph(session, graph_name)

            # nodeSimilarity.stream on a graph of investors (co-invest edges)
            q = f"""
            CALL gds.nodeSimilarity.stream('{graph_name}')
            YIELD node1, node2, similarity
            RETURN gds.util.asNode(node1).name AS investor1,
                   gds.util.asNode(node2).name AS investor2,
                   similarity
            ORDER BY similarity DESC
            LIMIT 50
            """
            rows = session.run(q).data()

            # Fallback: if no results (rare), compute via Cypher Jaccard pairwise
            if not rows:
                # Cypher-based Jaccard (robust fallback)
                fallback_q = """
                MATCH (a:Investor),(b:Investor)
                WHERE id(a) < id(b)
                WITH a,b,
                     size((a)-[:INVESTS_IN]->()<-[:INVESTS_IN]-(b)) AS intersection,
                     size((a)-[:INVESTS_IN]->()) AS sa,
                     size((b)-[:INVESTS_IN]->()) AS sb
                WITH a,b,intersection, (sa + sb - intersection) AS unionSize
                WHERE unionSize > 0 AND intersection > 0
                RETURN a.name AS investor1, b.name AS investor2, toFloat(intersection)/toFloat(unionSize) AS similarity
                ORDER BY similarity DESC LIMIT 50
                """
                rows = session.run(fallback_q).data()

            data = [{
                "investor1": r["investor1"],
                "investor2": r["investor2"],
                "similarity": float(r["similarity"])
            } for r in rows]
        return jsonify(data)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# -----------------------------
# Personalized Recommendations
# -----------------------------
@app.route("/recommendations/<investor>", methods=["GET"])
def recommend_investors(investor):
    try:
        with driver.session() as session:
            info_q = """
            MATCH (i:Investor {name: $investor})
            RETURN i.name AS name, i.risk_tolerance AS risk, i.domain AS domain
            """
            info = session.run(info_q, {"investor": investor}).data()
            if not info:
                return jsonify({"error": f"Investor '{investor}' not found"}), 404
            risk = info[0].get("risk", "Unknown")
            domain = info[0].get("domain") or "General"

            # similar by shared investments (top 5)
            similar_q = """
            MATCH (i1:Investor {name: $investor})-[:INVESTS_IN]->(a:Asset)<-[:INVESTS_IN]-(i2:Investor)
            WHERE i1 <> i2
            WITH i2, count(a) AS shared
            RETURN i2.name AS similar_investor, shared
            ORDER BY shared DESC LIMIT 5
            """
            similar = session.run(similar_q, {"investor": investor}).data()

            # recommended assets from peers
            rec_q = """
            MATCH (i:Investor {name: $investor})-[:INVESTS_IN]->(owned:Asset)
            WITH collect(owned) AS ownedList
            MATCH (i)-[:INVESTS_IN]->(:Asset)<-[:INVESTS_IN]-(peer:Investor)-[:INVESTS_IN]->(a:Asset)
            WHERE NOT a IN ownedList
            RETURN DISTINCT a.name AS recommended_asset LIMIT 10
            """
            rec_assets = session.run(rec_q, {"investor": investor}).data()

            # community (ensure co-invest graph exists)
            if not graph_exists(session, "investorCoInvest"):
                create_co_invest_graph(session, "investorCoInvest")

            comm_q = """
            CALL gds.louvain.stream('investorCoInvest')
            YIELD nodeId, communityId
            WITH gds.util.asNode(nodeId) AS n, communityId
            WHERE n.name = $investor
            RETURN communityId
            """
            comm = session.run(comm_q, {"investor": investor}).data()
            community_id = comm[0]["communityId"] if comm else None

            peers_q = """
            CALL gds.louvain.stream('investorCoInvest')
            YIELD nodeId, communityId
            WITH gds.util.asNode(nodeId) AS n, communityId
            WHERE communityId = $cid AND n.name <> $investor
            RETURN n.name AS peer LIMIT 10
            """
            community_peers = []
            if community_id is not None:
                community_peers = [r["peer"] for r in session.run(peers_q, {"cid": community_id, "investor": investor}).data()]

            summary = {
                "investor": investor,
                "risk_tolerance": risk,
                "domain": domain,
                "similar_investors": [r["similar_investor"] for r in similar],
                "recommended_assets": [r["recommended_asset"] for r in rec_assets],
                "community_id": int(community_id) if community_id is not None else None,
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
