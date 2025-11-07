from neo4j import GraphDatabase
import pandas as pd
import random

# -----------------------------
# Connect to Neo4j
# -----------------------------
uri = "bolt://localhost:7687"
username = "neo4j"
password = "testpassword"   # use the same password as your Docker setup

driver = GraphDatabase.driver(uri, auth=(username, password))

# -----------------------------
# Load CSVs
# -----------------------------
investors = pd.read_csv("investors.csv")
assets = pd.read_csv("assets.csv")

# -----------------------------
# Create Schema (Indexes)
# -----------------------------
def create_constraints(tx):
    tx.run("CREATE CONSTRAINT IF NOT EXISTS FOR (i:Investor) REQUIRE i.investor_id IS UNIQUE")
    tx.run("CREATE CONSTRAINT IF NOT EXISTS FOR (a:Asset) REQUIRE a.symbol IS UNIQUE")

# -----------------------------
# Create Nodes
# -----------------------------
def load_investors(tx, row):
    tx.run("""
        MERGE (i:Investor {investor_id: $investor_id})
        SET i.name = $name,
            i.risk_tolerance = $risk_tolerance,
            i.preferred_sector = $preferred_sector,
            i.investment_goal = $investment_goal
    """, **row)

def load_assets(tx, row):
    tx.run("""
        MERGE (a:Asset {symbol: $symbol})
        SET a.name = $name,
            a.sector = $sector,
            a.volatility = $volatility,
            a.avg_return = $avg_return
    """, **row)

# -----------------------------
# Create Relationships
# -----------------------------
def create_relationships(tx, investor_id, asset_symbol):
    tx.run("""
        MATCH (i:Investor {investor_id: $investor_id})
        MATCH (a:Asset {symbol: $symbol})
        MERGE (i)-[:INVESTS_IN]->(a)
    """, investor_id=investor_id, symbol=asset_symbol)

def correlate_assets(tx, symbol1, symbol2):
    tx.run("""
        MATCH (a1:Asset {symbol: $s1}), (a2:Asset {symbol: $s2})
        MERGE (a1)-[:CORRELATED_WITH]->(a2)
    """, s1=symbol1, s2=symbol2)

# -----------------------------
# Ingest Data into Neo4j
# -----------------------------
with driver.session() as session:
    print("Creating constraints...")
    session.execute_write(create_constraints)

    print("Loading investors...")
    for _, row in investors.iterrows():
        session.execute_write(load_investors, row.to_dict())

    print("Loading assets...")
    for _, row in assets.iterrows():
        session.execute_write(load_assets, row.to_dict())

    print("Creating INVESTS_IN relationships...")
    for _, inv in investors.iterrows():
        # randomly assign 3–5 assets per investor
        picks = random.sample(list(assets["symbol"]), k=random.randint(3, 5))
        for p in picks:
            session.execute_write(create_relationships, inv["investor_id"], p)

    print("Creating CORRELATED_WITH relationships between assets of same sector...")
    sectors = assets.groupby("sector")
    for _, group in sectors:
        syms = list(group["symbol"])
        for i in range(len(syms)):
            for j in range(i + 1, len(syms)):
                session.execute_write(correlate_assets, syms[i], syms[j])

driver.close()
print("Data successfully imported into Neo4j")
