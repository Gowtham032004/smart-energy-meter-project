"""
ai/budget_predictor.py — Balance forecasting & recharge suggestions
"""
import numpy as np
import pandas as pd
from typing import Dict


def predict_budget(df: pd.DataFrame, balance: float,
                   rate_per_kwh: float = 6.5) -> Dict:
    """
    Analyses recent usage trend and predicts:
    - hours / days remaining before balance hits zero
    - recommended recharge amount
    - daily cost estimate
    """
    if df.empty or balance <= 0:
        return {
            "hours_remaining": 0, "days_remaining": 0,
            "daily_cost_rs": 0, "recommended_recharge": 100,
            "expiry_message": "Balance exhausted or no data.",
        }

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp")

    # Use last 24 h for trend; fall back to all data if shorter
    cutoff = df["timestamp"].max() - pd.Timedelta(hours=24)
    recent = df[df["timestamp"] >= cutoff]
    if len(recent) < 5:
        recent = df

    # Average power (W) → kWh per hour → cost per hour
    avg_power_w   = recent["power"].mean()
    avg_power_kw  = avg_power_w / 1000.0
    cost_per_hour = avg_power_kw * rate_per_kwh        # ₹/h
    cost_per_day  = cost_per_hour * 24

    hours_remaining = (balance / cost_per_hour) if cost_per_hour > 0 else float("inf")
    days_remaining  = hours_remaining / 24

    # Trend: is usage increasing or decreasing?
    if len(recent) > 10:
        first_half = recent.iloc[:len(recent)//2]["power"].mean()
        second_half = recent.iloc[len(recent)//2:]["power"].mean()
        trend_factor = second_half / max(first_half, 1)
    else:
        trend_factor = 1.0

    # Adjust remaining with trend
    adjusted_hours = hours_remaining / max(trend_factor, 0.5)

    # Recommended recharge: cover next 7 days at current rate (rounded up to 50s)
    raw_rec = cost_per_day * 7
    recommended = int(np.ceil(raw_rec / 50)) * 50

    # Expiry label
    if adjusted_hours < 2:
        msg = "⚠️ Balance will expire in less than 2 hours!"
    elif adjusted_hours < 24:
        msg = f"Balance will last approximately {adjusted_hours:.1f} hours."
    else:
        msg = f"Balance will last approximately {days_remaining:.1f} days."

    return {
        "hours_remaining":    round(adjusted_hours, 1),
        "days_remaining":     round(adjusted_hours / 24, 2),
        "daily_cost_rs":      round(cost_per_day, 2),
        "avg_power_w":        round(avg_power_w, 1),
        "trend_factor":       round(trend_factor, 2),
        "recommended_recharge": max(recommended, 50),
        "expiry_message":     msg,
    }
