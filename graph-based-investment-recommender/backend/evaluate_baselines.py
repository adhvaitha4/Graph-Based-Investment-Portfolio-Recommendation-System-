# evaluate_metrics.py
"""
Evaluate 3 baselines:
 - Random
 - ContentGraph
 - ItemCF_Jaccard

Metrics:
 - Precision@5
 - Recall@5
 - NDCG@10
 - MAP

Outputs:
 - results/evaluation_table.csv
 - results/evaluation_metrics_barplot.png
 - results/evaluation_metrics_lineplot.png
"""

import json
import math
import os
from collections import defaultdict

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# -------------------------------
# CONFIG
# -------------------------------
RESULT_DIR = "results"
TEST_EDGES = "test_edges.csv"
K_P = 5
K_NDCG = 10

os.makedirs(RESULT_DIR, exist_ok=True)


# -------------------------------
# METRICS
# -------------------------------
def precision_at_k(recommended, relevant, k=5):
    recommended = recommended[:k]
    hits = len([a for a in recommended if a in relevant])
    return hits / k if k > 0 else 0.0


def recall_at_k(recommended, relevant, k=5):
    if not relevant:
        return 0.0
    recommended = recommended[:k]
    hits = len([a for a in recommended if a in relevant])
    return hits / len(relevant)


def dcg_at_k(recommended, relevant, k=10):
    dcg = 0
    for i, item in enumerate(recommended[:k]):
        if item in relevant:
            dcg += 1 / math.log2(i + 2)
    return dcg


def idcg_at_k(relevant, k=10):
    ideal = min(len(relevant), k)
    return sum(1 / math.log2(i + 2) for i in range(ideal))


def ndcg_at_k(recommended, relevant, k=10):
    ideal = idcg_at_k(relevant, k)
    if ideal == 0:
        return 0.0
    return dcg_at_k(recommended, relevant, k) / ideal


def average_precision(recommended, relevant):
    if not relevant:
        return 0.0
    score = 0.0
    hits = 0
    for i, item in enumerate(recommended):
        if item in relevant:
            hits += 1
            score += hits / (i + 1)
    return score / len(relevant)


# -------------------------------
# GROUND TRUTH
# -------------------------------
def load_ground_truth():
    te = pd.read_csv(TEST_EDGES)
    gt = defaultdict(set)
    for _, row in te.iterrows():
        gt[row["investor_id"]].add(row["asset_symbol"])
    return gt


# -------------------------------
# LOAD BASELINE JSON
# -------------------------------
def load_json(fname):
    path = os.path.join(RESULT_DIR, fname)
    with open(path) as f:
        return json.load(f)


# -------------------------------
# EVALUATE ONE BASELINE
# -------------------------------
def evaluate_baseline(rec_dict, ground_truth):
    precs, recs, ndcgs, maps = [], [], [], []

    for investor, relevant in ground_truth.items():
        recommended = rec_dict.get(str(investor), rec_dict.get(investor, []))

        precs.append(precision_at_k(recommended, relevant, K_P))
        recs.append(recall_at_k(recommended, relevant, K_P))
        ndcgs.append(ndcg_at_k(recommended, relevant, K_NDCG))
        maps.append(average_precision(recommended, relevant))

    return {
        "Precision@5": np.mean(precs),
        "Recall@5": np.mean(recs),
        "NDCG@10": np.mean(ndcgs),
        "MAP": np.mean(maps)
    }


# -------------------------------
# PLOTS
# -------------------------------
def plot_scores(df):
    # BAR
    ax = df.plot.bar(x="Model", figsize=(8, 5), rot=30)
    plt.title("Baseline Evaluation Metrics")
    plt.ylabel("Score")
    plt.tight_layout()
    bar_file = os.path.join(RESULT_DIR, "evaluation_metrics_barplot.png")
    plt.savefig(bar_file)
    plt.close()

    # LINE
    ax2 = df.set_index("Model").T.plot(figsize=(8, 5), marker="o")
    plt.title("Evaluation Metrics Trend")
    plt.ylabel("Score")
    plt.tight_layout()
    line_file = os.path.join(RESULT_DIR, "evaluation_metrics_lineplot.png")
    plt.savefig(line_file)
    plt.close()

    return bar_file, line_file


# -------------------------------
# MAIN
# -------------------------------
def main():

    print("Loading ground truth...")
    ground_truth = load_ground_truth()
    print(f"Loaded ground truth for {len(ground_truth)} investors.")

    baselines = {
    "Random": "random_baseline.json",
    "Popularity": "popularity_baseline.json",
    "OppositeDomain": "opposite_domain_baseline.json"
}


    results = []

    for model_name, fname in baselines.items():
        print(f"Evaluating {model_name}...")
        recs = load_json(fname)
        score = evaluate_baseline(recs, ground_truth)
        score["Model"] = model_name
        results.append(score)

    df = pd.DataFrame(results)[["Model", "Precision@5", "Recall@5", "NDCG@10", "MAP"]]

    print("\n===== FINAL METRIC SCORES =====\n")
    print(df.to_string(index=False))

    df.to_csv(os.path.join(RESULT_DIR, "evaluation_table.csv"), index=False)

    barfile, linefile = plot_scores(df)

    print("\nSaved plots:")
    print("-", barfile)
    print("-", linefile)


if __name__ == "__main__":
    main()
