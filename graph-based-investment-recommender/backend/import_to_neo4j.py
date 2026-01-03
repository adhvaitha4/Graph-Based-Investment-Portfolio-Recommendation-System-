from neo4j import GraphDatabase
import pandas as pd

# Connect to Neo4j
uri = "bolt://localhost:7687"
username = "neo4j"
password = "testpassword"   # same as Docker
driver = GraphDatabase.driver(uri, auth=(username, password))

# Load CSVs
investors = pd.read_csv("investors.csv")
assets = pd.read_csv("assets.csv")
edges = pd.read_csv("investor_asset_edges.csv")   # NEW dataset

# Create Schema
def create_constraints(tx):
    tx.run("CREATE CONSTRAINT IF NOT EXISTS FOR (i:Investor) REQUIRE i.investor_id IS UNIQUE")
    tx.run("CREATE CONSTRAINT IF NOT EXISTS FOR (a:Asset) REQUIRE a.symbol IS UNIQUE")

# Create Investor Node

def load_investors(tx, row):
    tx.run("""
        MERGE (i:Investor {investor_id: $investor_id})
        SET i.name = $name,
            i.risk_tolerance = $risk_tolerance,
            i.preferred_sector = $preferred_sector,
            i.domain = $domain,
            i.investment_goal = $investment_goal
    """, **row)

# Create Asset Node

def load_assets(tx, row):
    tx.run("""
        MERGE (a:Asset {symbol: $symbol})
        SET a.name = $name,
            a.sector = $sector,
            a.volatility = $volatility,
            a.avg_return = $avg_return
    """, **row)

# Create INVESTS_IN Edges

def create_invest_edge(tx, inv_id, asset_symbol, amount):
    tx.run("""
        MATCH (i:Investor {investor_id: $inv_id})
        MATCH (a:Asset {symbol: $symbol})
        MERGE (i)-[r:INVESTS_IN]->(a)
        SET r.amount = $amount
    """, inv_id=inv_id, symbol=asset_symbol, amount=amount)

# Create CORRELATED_WITH Edges

def correlate_assets(tx, s1, s2):
    tx.run("""
        MATCH (a1:Asset {symbol: $s1}), (a2:Asset {symbol: $s2})
        MERGE (a1)-[:CORRELATED_WITH]->(a2)
    """, s1=s1, s2=s2)

# Import Pipeline
with driver.session() as session:

    print("Creating constraints...")
    session.execute_write(create_constraints)

    print("Loading Investors...")
    for _, row in investors.iterrows():
        session.execute_write(load_investors, row.to_dict())

    print("Loading Assets...")
    for _, row in assets.iterrows():
        session.execute_write(load_assets, row.to_dict())

    print("Creating INVESTS_IN edges from investor_asset_edges.csv ...")
    for _, row in edges.iterrows():
        session.execute_write(
            create_invest_edge,
            row["investor_id"],
            row["asset_symbol"],
            float(row["investment_amount"])
        )

    print("Creating CORRELATED_WITH edges for same-sector assets...")
    grouped = assets.groupby("sector")

    for _, group in grouped:
        syms = list(group["symbol"])
        for i in range(len(syms)):
            for j in range(i + 1, len(syms)):
                session.execute_write(correlate_assets, syms[i], syms[j])

driver.close()
print("Data successfully imported into Neo4j.")
