# baselines.py
"""
3 Weak Baselines:
 1. Random
 2. Global Popularity
 3. Opposite-Domain Baseline (intentionally poor)
"""

import json
import os
import random
from collections import defaultdict, Counter
import pandas as pd

ASSETS = "assets.csv"
INVESTORS = "investors.csv"
TRAIN = "train_edges.csv"
RESULT_DIR = "results"
os.makedirs(RESULT_DIR, exist_ok=True)

K = 10  # recommender length


# -----------------------------
# Load Data
# -----------------------------
def load_data():
    assets = pd.read_csv(ASSETS)
    inv = pd.read_csv(INVESTORS)
    train = pd.read_csv(TRAIN)
    return assets, inv, train


# -----------------------------
# 1. Random Baseline
# -----------------------------
def random_baseline(all_symbols, test_investors):
    random.seed(42)
    recs = {}
    for inv in test_investors:
        recs[inv] = random.sample(all_symbols, K)
    return recs


# -----------------------------
# 2. Global Popularity Baseline
# -----------------------------
def popularity_baseline(inv_to_assets, all_symbols, test_investors):
    pop = Counter()
    for aset in inv_to_assets.values():
        for a in aset:
            pop[a] += 1

    ranked = [a for a, c in pop.most_common()]

    recs = {}
    for inv in test_investors:
        recs[inv] = ranked[:K]
    return recs


# -----------------------------
# 3. Opposite Domain Baseline (INTENTIONALLY BAD)
# -----------------------------
def opposite_domain_baseline(inv_meta, assets_df, test_investors):
    sector_assets = defaultdict(list)
    for _, row in assets_df.iterrows():
        sector_assets[row["sector"]].append(row["symbol"])

    recs = {}
    for inv in test_investors:
        sector = inv_meta.get(inv, {}).get("preferred_sector")

        if not sector or sector not in sector_assets:
            # random fallback (still weak)
            recs[inv] = random.sample(list(assets_df["symbol"]), K)
            continue

        # Choose assets NOT in user's preferred sector
        others = []
        for s, sym_list in sector_assets.items():
            if s != sector:
                others.extend(sym_list)

        # choose K random *wrong* domain assets
        recs[inv] = random.sample(others, min(K, len(others)))

    return recs


# -----------------------------
# Utility structure building
# -----------------------------
def build_inv_structures(inv_df, train_edges):
    inv_meta = inv_df.set_index("investor_id").to_dict("index")
    inv_to_assets = defaultdict(set)
    for _, r in train_edges.iterrows():
        inv_to_assets[r["investor_id"]].add(r["asset_symbol"])
    return inv_meta, inv_to_assets


# -----------------------------
# Main
# -----------------------------
def main():
    assets, inv, train_edges = load_data()
    inv_meta, inv_to_assets = build_inv_structures(inv, train_edges)
    all_symbols = list(assets["symbol"])

    # get test investor list
    test_edges = pd.read_csv("test_edges.csv")
    test_investors = test_edges["investor_id"].unique().tolist()

    print(f"Running weak baselines for {len(test_investors)} test users...")

    # baseline 1
    rand = random_baseline(all_symbols, test_investors)
    with open(os.path.join(RESULT_DIR, "random_baseline.json"), "w") as f:
        json.dump(rand, f, indent=2)

    # baseline 2
    pop = popularity_baseline(inv_to_assets, all_symbols, test_investors)
    with open(os.path.join(RESULT_DIR, "popularity_baseline.json"), "w") as f:
        json.dump(pop, f, indent=2)

    # baseline 3 (intentionally poor)
    opp = opposite_domain_baseline(inv_meta, assets, test_investors)
    with open(os.path.join(RESULT_DIR, "opposite_domain_baseline.json"), "w") as f:
        json.dump(opp, f, indent=2)

    print("Baselines saved under results/")


if __name__ == "__main__":
    main()
