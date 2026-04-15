"""
ai/recommendations.py
=====================
Rule-based + pattern-driven recommendation engine.
Generates personalised energy-saving tips and optimal usage suggestions.
"""
import pandas as pd
import numpy as np
from typing import List, Dict


# ─── Tip library ──────────────────────────────────────────────────────────────
TIPS = {
    "high_night":   "You're using significant energy at night. "
                    "Consider scheduling heavy loads (washing machine, water heater) during off-peak hours (11 PM–6 AM) for better efficiency.",
    "peak_hours":   "Your peak usage falls between 6–10 PM — this is grid peak time. "
                    "Shifting usage to 10 AM–4 PM can reduce effective tariff costs.",
    "hvac":         "High baseline power detected even when active loads are off. "
                    "This may indicate inefficient HVAC or standby power. "
                    "Try unplugging idle appliances.",
    "low_pf":       "Voltage-current ratio suggests possible low power factor. "
                    "Consider PF correction capacitors to improve efficiency.",
    "weekend_spike": "Usage spikes occur on weekends. "
                     "Plan heavy appliance use across the week for a smoother load profile.",
    "constant_load": "Load appears nearly constant 24/7. "
                     "Consider installing timers on non-critical loads.",
    "solar":        "Your usage pattern peaks during midday — an ideal match for solar generation. "
                    "A 1 kW rooftop solar panel could offset 30–40% of your daily consumption.",
    "low_balance":  "Balance is critically low. Recharge ₹200+ to avoid interruption.",
    "appliance_tip": "Switching to 5-star rated appliances can reduce energy use by up to 40%.",
    "normal":       "Your energy consumption is within normal range. Keep it up!",
}

USER_CLASS_TIPS = {
    "low":    ["You are a low-consumption user. Well done! Consider solar micro-inverters to further reduce bills."],
    "medium": ["You are an average-consumption user. Small changes — LED lights, smart plugs — can save ₹200–400/month."],
    "high":   ["You are a high-consumption user. A full home energy audit is recommended. Consider time-of-use tariff plans."],
}


# ─── Classifier ───────────────────────────────────────────────────────────────
def classify_user(daily_kwh: float) -> str:
    """Classify user consumption tier."""
    if daily_kwh < 3:
        return "low"
    elif daily_kwh < 10:
        return "medium"
    return "high"


def analyze_patterns(df: pd.DataFrame) -> Dict:
    """Derive pattern flags from historical data."""
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["hour"] = df["timestamp"].dt.hour
    df["dow"]  = df["timestamp"].dt.dayofweek

    night = df[df["hour"].between(22, 23) | df["hour"].between(0, 5)]["power"].mean()
    peak  = df[df["hour"].between(18, 22)]["power"].mean()
    day   = df[df["hour"].between(10, 16)]["power"].mean()
    wkend = df[df["dow"] >= 5]["power"].mean()
    wkday = df[df["dow"] < 5]["power"].mean()

    daily_kwh = df.groupby(df["timestamp"].dt.date)["power"].mean().mean() * 24 / 1000

    return {
        "night_avg_w":  round(float(night or 0), 1),
        "peak_avg_w":   round(float(peak or 0), 1),
        "day_avg_w":    round(float(day or 0), 1),
        "weekend_ratio": round(float((wkend or 0) / max(wkday or 1, 1)), 2),
        "daily_kwh":    round(float(daily_kwh), 3),
        "user_type":    classify_user(float(daily_kwh)),
    }


# ─── Main recommendation function ─────────────────────────────────────────────
def generate_recommendations(df: pd.DataFrame,
                              balance: float,
                              rate_per_kwh: float = 6.5) -> List[Dict]:
    """
    Returns a ranked list of recommendation dicts:
      { priority, category, message, potential_saving }
    """
    recs   = []
    if df.empty:
        return [{"priority": 1, "category": "info",
                 "message": TIPS["normal"], "potential_saving": "₹0"}]

    pat = analyze_patterns(df)

    # Balance warning
    if balance < 50:
        recs.append({
            "priority":        1,
            "category":        "alert",
            "message":         TIPS["low_balance"],
            "potential_saving": "—"
        })

    # Night usage
    if pat["night_avg_w"] > 300:
        recs.append({
            "priority":        2,
            "category":        "schedule",
            "message":         TIPS["high_night"],
            "potential_saving": f"~₹{int(pat['night_avg_w'] * 0.3 / 1000 * 6 * rate_per_kwh)}/month"
        })

    # Peak hour usage
    if pat["peak_avg_w"] > pat["day_avg_w"] * 1.5:
        recs.append({
            "priority":        3,
            "category":        "schedule",
            "message":         TIPS["peak_hours"],
            "potential_saving": "~15% bill reduction"
        })

    # Weekend spike
    if pat["weekend_ratio"] > 1.4:
        recs.append({
            "priority":        4,
            "category":        "pattern",
            "message":         TIPS["weekend_spike"],
            "potential_saving": "~10% load balancing"
        })

    # Solar suggestion (midday load)
    if pat["day_avg_w"] > 500:
        recs.append({
            "priority":        5,
            "category":        "green",
            "message":         TIPS["solar"],
            "potential_saving": f"~₹{int(pat['daily_kwh'] * 0.35 * 30 * rate_per_kwh)}/month"
        })

    # Appliance upgrade
    if pat["daily_kwh"] > 8:
        recs.append({
            "priority":        6,
            "category":        "efficiency",
            "message":         TIPS["appliance_tip"],
            "potential_saving": "~40% on appliance costs"
        })

    # User class tip
    user_tips = USER_CLASS_TIPS.get(pat["user_type"], [])
    for tip in user_tips:
        recs.append({
            "priority":        7,
            "category":        "general",
            "message":         tip,
            "potential_saving": "varies"
        })

    if not recs:
        recs.append({
            "priority":        8,
            "category":        "general",
            "message":         TIPS["normal"],
            "potential_saving": "—"
        })

    return sorted(recs, key=lambda r: r["priority"])
