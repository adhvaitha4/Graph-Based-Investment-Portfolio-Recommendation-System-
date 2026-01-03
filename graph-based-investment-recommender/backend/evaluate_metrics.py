import pandas as pd
import requests
import numpy as np
import matplotlib.pyplot as plt
from collections import defaultdict

# -------------------------------------------------------
# Load ground truth
# -------------------------------------------------------

test_df = pd.read_csv("test_edges.csv")
assets_df = pd.read_csv("assets.csv")
investors_df = pd.read_csv("investors.csv")

name_to_symbol = dict(zip(assets_df["name"], assets_df["symbol"]))
id_to_name = dict(zip(investors_df["investor_id"], investors_df["name"]))

ground_truth = defaultdict(set)
for _, row in test_df.iterrows():
    investor_name = id_to_name.get(row["investor_id"])
    if investor_name:
        ground_truth[investor_name].add(row["asset_symbol"])

print("Loaded ground truth for", len(ground_truth), "investors.")

# -------------------------------------------------------
# Metric functions
# -------------------------------------------------------

def precision_at_k(pred, truth, k=5):
    if not truth:
        return 0.0
    return len(set(pred[:k]) & set(truth)) / k

def recall_at_k(pred, truth, k=5):
    if not truth:
        return 0.0
    return len(set(pred[:k]) & set(truth)) / len(truth)

def dcg(relevances):
    return sum(rel / np.log2(i+2) for i, rel in enumerate(relevances))

def ndcg_at_k(pred, truth, k=10):
    if not truth:
        return 0.0
    pred_k = pred[:k]
    relevances = [1 if p in truth else 0 for p in pred_k]
    ideal = sorted(relevances, reverse=True)
    denom = dcg(ideal)
    return 0.0 if denom == 0 else dcg(relevances) / denom

def average_precision(pred, truth):
    if not truth:
        return 0.0
    score = 0.0
    hits = 0
    for i, p in enumerate(pred):
        if p in truth:
            hits += 1
            score += hits / (i+1)
    return score / len(truth)

# -------------------------------------------------------
# Evaluate all 4 models
# -------------------------------------------------------

MODELS = {
    "full": 5000,
    "no_jaccard": 5001,
    "no_popularity": 5002,
    "no_community": 5003
}

results = []

for model_name, port in MODELS.items():
    print(f"\nEvaluating model: {model_name} (port {port})")

    precs, recs, ndcgs, maps = [], [], [], []

    for investor_name, truth_symbols in ground_truth.items():

        url = f"http://127.0.0.1:{port}/recommendations/{investor_name}"
        
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code != 200:
                continue
            response = resp.json()
        except:
            continue

        # Safely extract predictions
        predicted_items = response.get("recommended_assets", [])
        predicted_symbols = []

        for item in predicted_items:

            # Case 1: API returns dict
            if isinstance(item, dict):
                sym = item.get("symbol")
                if sym:
                    predicted_symbols.append(sym)

            # Case 2: API returns asset name
            elif isinstance(item, str):
                sym = name_to_symbol.get(item)
                if sym:
                    predicted_symbols.append(sym)

        # Skip investors with no predictions
        if not predicted_symbols:
            continue

        # Append metrics
        precs.append(precision_at_k(predicted_symbols, truth_symbols))
        recs.append(recall_at_k(predicted_symbols, truth_symbols))
        ndcgs.append(ndcg_at_k(predicted_symbols, truth_symbols))
        maps.append(average_precision(predicted_symbols, truth_symbols))

    # Handle empty lists safely
    results.append({
        "model": model_name,
        "Precision@5": np.mean(precs) if precs else 0.0,
        "Recall@5": np.mean(recs) if recs else 0.0,
        "NDCG@10": np.mean(ndcgs) if ndcgs else 0.0,
        "MAP": np.mean(maps) if maps else 0.0
    })

# -------------------------------------------------------
# Output results
# -------------------------------------------------------

df = pd.DataFrame(results)
print("\n==== FINAL METRICS ====")
print(df)

df.to_csv("all_model_metrics.csv", index=False)

df.plot(x="model", y=["Precision@5", "Recall@5", "NDCG@10", "MAP"], marker="o")
plt.title("Ablation Study Metrics")
plt.savefig("ablation_metrics.png")
plt.close()

print("\nSaved results:")
print(" - all_model_metrics.csv")
print(" - ablation_metrics.png")
