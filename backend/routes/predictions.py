"""
routes/predictions.py — AI prediction & insights endpoints
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
import pandas as pd
import numpy as np

from backend.database import get_db
from backend.models.energy import EnergyReading, Prediction
from backend.ai.data_preprocessing import EnergyPreprocessor, FEATURES, SEQUENCE_LEN
from backend.ai.budget_predictor import predict_budget
from backend.ai.recommendations import generate_recommendations, analyze_patterns

router = APIRouter(prefix="/api", tags=["predictions"])
_preprocessor = EnergyPreprocessor()


async def _fetch_df(device_id: str, limit: int, db: AsyncSession) -> pd.DataFrame:
    result = await db.execute(
        select(EnergyReading)
        .where(EnergyReading.device_id == device_id)
        .order_by(desc(EnergyReading.timestamp))
        .limit(limit)
    )
    rows = result.scalars().all()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([{
        "timestamp": r.timestamp, "voltage": r.voltage, "current": r.current,
        "power": r.power, "energy_kwh": r.energy_kwh, "balance": r.balance,
    } for r in reversed(rows)])


# ── GET /api/predictions ──────────────────────────────────────────────────────
@router.get("/predictions")
async def get_predictions(device_id: str = "METER_001",
                          horizon: int = 24,
                          db: AsyncSession = Depends(get_db)):
    """
    Returns AI-generated energy predictions.
    horizon: 1 | 24 | 168 (hours)
    Steps = horizon * 12  (12 readings per hour at 5-min interval)
    """
    df = await _fetch_df(device_id, 2000, db)
    if df.empty:
        return {"predictions": [], "summary": {}, "message": "Insufficient data"}

    # Build features
    feat_df = _preprocessor.build_features(df)
    feat_df = _preprocessor.fit_normalize(feat_df)

    # Try LSTM inference
    try:
        from backend.ai.lstm_model import load_model, predict_horizon, get_horizon_summary
        model = load_model()
        if model and len(feat_df) >= SEQUENCE_LEN:
            last_seq = feat_df[FEATURES].values[-SEQUENCE_LEN:].reshape(1, SEQUENCE_LEN, -1)
            mean_p = _preprocessor.scaler_params["mean"]["power"]
            std_p  = _preprocessor.scaler_params["std"]["power"]
            steps  = horizon * 12
            preds  = predict_horizon(last_seq, steps, model, mean_p, std_p)
            summary = get_horizon_summary(preds, rate_per_kwh=6.5)
            return {"predictions": preds, "summary": summary, "source": "LSTM"}
    except Exception as e:
        pass

    # Fallback: statistical (moving average extrapolation)
    avg_power = df["power"].rolling(12, min_periods=1).mean().iloc[-1]
    preds = []
    for step in range(horizon * 12):
        # Add slight sinusoidal daily pattern
        minute_offset = (step + 1) * 5
        hour_of_day   = (pd.Timestamp.utcnow().hour + minute_offset / 60) % 24
        factor = 1.0 + 0.25 * np.sin(np.pi * (hour_of_day - 6) / 12)
        watts = max(0.0, float(avg_power * factor))
        preds.append({
            "minutes_ahead":   minute_offset,
            "predicted_watts": round(watts, 2),
            "predicted_kwh":   round(watts / 1000 * 5 / 60, 5),
        })

    total_kwh  = sum(p["predicted_kwh"] for p in preds)
    return {
        "predictions": preds,
        "summary": {
            "total_kwh":   round(total_kwh, 4),
            "avg_watts":   round(avg_power, 2),
            "total_hours": horizon,
            "est_cost_rs": round(total_kwh * 6.5, 2),
        },
        "source": "statistical_fallback",
    }


# ── GET /api/balance ──────────────────────────────────────────────────────────
@router.get("/balance")
async def get_balance(device_id: str = "METER_001",
                      db: AsyncSession = Depends(get_db)):
    df = await _fetch_df(device_id, 500, db)
    result = await db.execute(
        select(EnergyReading)
        .where(EnergyReading.device_id == device_id)
        .order_by(desc(EnergyReading.timestamp))
        .limit(1)
    )
    latest = result.scalars().first()
    balance = latest.balance if latest else 0.0
    forecast = predict_budget(df, balance)
    return {"balance": balance, "forecast": forecast}


# ── GET /api/insights ─────────────────────────────────────────────────────────
@router.get("/insights")
async def get_insights(device_id: str = "METER_001",
                       db: AsyncSession = Depends(get_db)):
    df = await _fetch_df(device_id, 2016, db)
    result = await db.execute(
        select(EnergyReading)
        .where(EnergyReading.device_id == device_id)
        .order_by(desc(EnergyReading.timestamp))
        .limit(1)
    )
    latest = result.scalars().first()
    balance = latest.balance if latest else 0.0

    tips     = generate_recommendations(df, balance)
    patterns = analyze_patterns(df) if not df.empty else {}
    return {"recommendations": tips, "patterns": patterns}
