"""
routes/agent.py — Conversational AI agent endpoint
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
import pandas as pd
import re
from datetime import datetime, timedelta

from backend.database import get_db
from backend.models.energy import EnergyReading, Anomaly, Alert
from backend.ai.budget_predictor import predict_budget
from backend.ai.recommendations import generate_recommendations, analyze_patterns

router = APIRouter(prefix="/api/agent", tags=["agent"])


class ChatRequest(BaseModel):
    device_id: str = "METER_001"
    message:   str


class ChatResponse(BaseModel):
    reply:   str
    data:    dict = {}
    intent:  str  = "unknown"


# ── Intent patterns ───────────────────────────────────────────────────────────
INTENTS = {
    "usage_today":    r"(how much|usage|used|consumption).*(today|day)",
    "usage_week":     r"(how much|usage|used|consumption).*(week|7 day)",
    "balance":        r"(balance|credit|remaining|left|money)",
    "expire":         r"(when|expir|run out|how long)",
    "why_high":       r"(why|reason|cause).*(high|spike|increase|more)",
    "anomaly":        r"(anomal|theft|unusu|alert|weird|strange)",
    "predict":        r"(predict|forecast|next|tomorrow|future)",
    "tips":           r"(tip|suggest|save|recommend|reduce|efficient)",
    "status":         r"(status|relay|power|on|off|connect)",
    "hello":          r"^(hi|hello|hey|good|howdy)",
}


def detect_intent(msg: str) -> str:
    msg_lower = msg.lower()
    for intent, pattern in INTENTS.items():
        if re.search(pattern, msg_lower):
            return intent
    return "general"


# ── Data fetchers ─────────────────────────────────────────────────────────────
async def fetch_recent(device_id: str, hours: int, db: AsyncSession) -> pd.DataFrame:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(EnergyReading)
        .where(EnergyReading.device_id == device_id,
               EnergyReading.timestamp >= cutoff)
        .order_by(EnergyReading.timestamp)
    )
    rows = result.scalars().all()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([{
        "timestamp": r.timestamp, "power": r.power,
        "energy_kwh": r.energy_kwh, "balance": r.balance,
        "voltage": r.voltage, "current": r.current,
    } for r in rows])


async def fetch_latest(device_id: str, db: AsyncSession):
    result = await db.execute(
        select(EnergyReading)
        .where(EnergyReading.device_id == device_id)
        .order_by(desc(EnergyReading.timestamp))
        .limit(1)
    )
    return result.scalars().first()


# ── Main chat endpoint ────────────────────────────────────────────────────────
@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    intent = detect_intent(req.message)
    device = req.device_id

    # ── today's usage ─────────────────────────────────────────────────────────
    if intent == "usage_today":
        df = await fetch_recent(device, 24, db)
        if df.empty:
            return ChatResponse(reply="I don't have any readings for today yet. Make sure the meter is connected.", intent=intent)
        kwh   = df["energy_kwh"].max() - df["energy_kwh"].min()
        cost  = kwh * 6.5
        avg_w = df["power"].mean()
        reply = (f"📊 **Today's Usage**\n"
                 f"- Energy consumed: **{kwh:.3f} kWh**\n"
                 f"- Estimated cost: **₹{cost:.2f}**\n"
                 f"- Average power: **{avg_w:.1f} W**")
        return ChatResponse(reply=reply, intent=intent,
                            data={"kwh": round(kwh, 3), "cost": round(cost, 2)})

    # ── weekly usage ──────────────────────────────────────────────────────────
    elif intent == "usage_week":
        df = await fetch_recent(device, 168, db)
        if df.empty:
            return ChatResponse(reply="Not enough data for weekly analysis.", intent=intent)
        kwh   = df["energy_kwh"].max() - df["energy_kwh"].min()
        cost  = kwh * 6.5
        reply = (f"📅 **Weekly Usage**\n"
                 f"- Total energy: **{kwh:.3f} kWh**\n"
                 f"- Total cost: **₹{cost:.2f}**\n"
                 f"- Daily average: **{kwh/7:.3f} kWh/day**")
        return ChatResponse(reply=reply, intent=intent)

    # ── balance ───────────────────────────────────────────────────────────────
    elif intent == "balance":
        latest = await fetch_latest(device, db)
        if not latest:
            return ChatResponse(reply="No balance data found.", intent=intent)
        df     = await fetch_recent(device, 24, db)
        fore   = predict_budget(df, latest.balance)
        reply  = (f"💰 **Balance Status**\n"
                  f"- Current balance: **₹{latest.balance:.2f}**\n"
                  f"- {fore['expiry_message']}\n"
                  f"- Recommended recharge: **₹{fore['recommended_recharge']}**")
        return ChatResponse(reply=reply, intent=intent,
                            data={"balance": latest.balance, "forecast": fore})

    # ── when will balance expire ───────────────────────────────────────────────
    elif intent == "expire":
        latest = await fetch_latest(device, db)
        if not latest:
            return ChatResponse(reply="No data available.", intent=intent)
        df   = await fetch_recent(device, 24, db)
        fore = predict_budget(df, latest.balance)
        hrs  = fore["hours_remaining"]
        if hrs == float("inf"):
            reply = "🔋 Balance will last indefinitely — no active load detected."
        elif hrs < 2:
            reply = f"⚠️ **CRITICAL:** Balance will run out in about **{hrs:.1f} hours!** Recharge immediately."
        else:
            reply = (f"🕐 Based on your current usage of **{fore['avg_power_w']:.0f}W**:\n"
                     f"- Balance lasts: **{fore['days_remaining']:.1f} days** ({hrs:.1f} hours)\n"
                     f"- Daily cost: **₹{fore['daily_cost_rs']:.2f}**\n"
                     f"- Suggested recharge: **₹{fore['recommended_recharge']}**")
        return ChatResponse(reply=reply, intent=intent, data=fore)

    # ── why is usage high ─────────────────────────────────────────────────────
    elif intent == "why_high":
        df = await fetch_recent(device, 48, db)
        if df.empty:
            return ChatResponse(reply="No recent data to analyse.", intent=intent)
        pat   = analyze_patterns(df)
        peak  = pat.get("peak_avg_w", 0)
        night = pat.get("night_avg_w", 0)
        reasons = []
        if peak > 800:
            reasons.append(f"🔴 High evening peak usage ({peak:.0f}W) — likely heavy appliances (AC/heater/oven) between 6–10 PM.")
        if night > 300:
            reasons.append(f"🌙 Significant night usage ({night:.0f}W) — possible always-on devices or security systems.")
        if pat.get("weekend_ratio", 1) > 1.4:
            reasons.append("📅 Weekend usage is 40%+ higher — occupancy-related load spike.")
        if not reasons:
            reasons.append("Usage appears within normal range. No specific high-usage pattern identified.")
        reply = "🔍 **Usage Analysis:**\n" + "\n".join(f"- {r}" for r in reasons)
        return ChatResponse(reply=reply, intent=intent, data=pat)

    # ── anomalies ─────────────────────────────────────────────────────────────
    elif intent == "anomaly":
        result = await db.execute(
            select(Anomaly)
            .where(Anomaly.device_id == device, Anomaly.resolved == False)
            .order_by(desc(Anomaly.detected_at))
            .limit(5)
        )
        anomalies = result.scalars().all()
        if not anomalies:
            return ChatResponse(reply="✅ No active anomalies detected. Your system looks healthy!", intent=intent)
        lines = [f"⚠️ **Active Anomalies ({len(anomalies)} found):**"]
        for a in anomalies:
            lines.append(f"- [{a.severity}] **{a.anomaly_type}** — {a.description}")
        return ChatResponse(reply="\n".join(lines), intent=intent)

    # ── tips ──────────────────────────────────────────────────────────────────
    elif intent == "tips":
        df     = await fetch_recent(device, 168, db)
        latest = await fetch_latest(device, db)
        bal    = latest.balance if latest else 0
        tips   = generate_recommendations(df, bal)
        lines  = ["💡 **Energy Saving Recommendations:**"]
        for t in tips[:4]:
            lines.append(f"- {t['message']}  *(Save: {t['potential_saving']})*")
        return ChatResponse(reply="\n".join(lines), intent=intent)

    # ── status ────────────────────────────────────────────────────────────────
    elif intent == "status":
        latest = await fetch_latest(device, db)
        if not latest:
            return ChatResponse(reply="No live data available.", intent=intent)
        relay  = "🟢 ON" if latest.relay_on else "🔴 OFF"
        theft  = "⚠️ THEFT DETECTED" if latest.theft else "✅ Normal"
        reply  = (f"📡 **Live Meter Status**\n"
                  f"- Voltage: **{latest.voltage:.1f} V**\n"
                  f"- Current: **{latest.current:.3f} A**\n"
                  f"- Power:   **{latest.power:.1f} W**\n"
                  f"- Relay:   **{relay}**\n"
                  f"- Balance: **₹{latest.balance:.2f}**\n"
                  f"- Security: **{theft}**")
        return ChatResponse(reply=reply, intent=intent)

    # ── greet ─────────────────────────────────────────────────────────────────
    elif intent == "hello":
        return ChatResponse(
            reply=("👋 Hello! I'm your **Smart Energy AI Assistant**.\n\n"
                   "You can ask me things like:\n"
                   "- *How much energy did I use today?*\n"
                   "- *When will my balance run out?*\n"
                   "- *Why is my usage high?*\n"
                   "- *Give me energy saving tips*\n"
                   "- *Show my meter status*"),
            intent="hello"
        )

    # ── general fallback ──────────────────────────────────────────────────────
    else:
        return ChatResponse(
            reply=("🤔 I'm not sure about that specific query. Try asking:\n"
                   "- 'How much energy today?' | 'When does balance expire?'\n"
                   "- 'Why is my usage high?' | 'Give me saving tips'"),
            intent="general"
        )
