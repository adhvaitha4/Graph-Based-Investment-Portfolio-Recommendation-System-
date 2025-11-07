import pandas as pd
import yfinance as yf
from faker import Faker
import random

# Initialize faker for synthetic data
fake = Faker()

# -----------------------------
# Generate Investor Profiles
# -----------------------------
def generate_investors(n=10):
    risk_levels = ["Low", "Moderate", "High"]
    sectors = ["FinTech", "HealthTech", "EnergyTech", "GreenTech", "EduTech"]

    investors = []
    for _ in range(n):
        sector = random.choice(sectors)
        investors.append({
            "investor_id": fake.uuid4(),
            "name": fake.name(),
            "risk_tolerance": random.choice(risk_levels),
            "preferred_sector": sector,
            "domain": sector,  # ✅ Added domain
            "investment_goal": random.choice(["Retirement", "Wealth Growth", "Education", "Short-term Gain"])
        })
    return pd.DataFrame(investors)


# -----------------------------
# Fetch Financial Assets Data
# -----------------------------
def fetch_assets(tickers=["AAPL", "GOOGL", "MSFT", "JNJ", "XOM", "JPM", "V", "PG", "NVDA", "TSLA",
                    "AMZN", "META", "NFLX", "DIS", "PFE", "INTC", "CSCO", "KO", "PEP", "WMT"]):
    data = []
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info
            data.append({
                "symbol": ticker,
                "name": info.get("longName", ticker),
                "sector": info.get("sector", "Unknown"),
                "volatility": round(random.uniform(0.05, 0.35), 2),
                "avg_return": round(random.uniform(-0.1, 0.2), 3)
            })
        except Exception:
            data.append({
                "symbol": ticker,
                "name": ticker,
                "sector": "Unknown",
                "volatility": round(random.uniform(0.05, 0.35), 2),
                "avg_return": round(random.uniform(-0.1, 0.2), 3)
            })
    return pd.DataFrame(data)

# Generate data
investors_df = generate_investors(60)
assets_df = fetch_assets()

# Save locally for review
investors_df.to_csv("investors.csv", index=False)
assets_df.to_csv("assets.csv", index=False)

print("Synthetic investors and financial assets generated successfully")