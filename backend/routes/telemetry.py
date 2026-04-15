"""
routes/telemetry.py — Receive ESP32 data & run real-time AI checks
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import pandas as pd

from backend.database import get_db
from backend.models.energy import EnergyReading, Anomaly, Alert, User
from backend.ai.anomaly_detection import AnomalyEngine

router = APIRouter(prefix="/api", tags=["telemetry"])
_anomaly_engine = AnomalyEngine()


# ── Schemas ───────────────────────────────────────────────────────────────────
class TelemetryIn(BaseModel):
    device_id:  str
    timestamp:  Optional[str] = None
    voltage:    float
    current:    float
    power:      float
    energy_kwh: float
    balance:    float
    relay_on:   bool = True
    theft:      bool = False


class TelemetryOut(BaseModel):
    id:         int
    device_id:  str
    timestamp:  datetime
    voltage:    float
    current:    float
    power:      float
    energy_kwh: float
    balance:    float
    relay_on:   bool
    theft:      bool
    class Config:
        from_attributes = True


# ── POST /api/telemetry ────────────────────────────────────────────────────────
@router.post("/telemetry", response_model=TelemetryOut)
async def ingest_telemetry(data: TelemetryIn, db: AsyncSession = Depends(get_db)):
    ts = datetime.utcnow()
    if data.timestamp:
        try:
            ts = datetime.fromisoformat(data.timestamp.replace("Z", ""))
        except ValueError:
            pass

    reading = EnergyReading(
        device_id=data.device_id, timestamp=ts,
        voltage=data.voltage, current=data.current,
        power=data.power, energy_kwh=data.energy_kwh,
        balance=data.balance, relay_on=data.relay_on, theft=data.theft,
    )
    db.add(reading)
    await db.commit()
    await db.refresh(reading)

    # Rule-based anomaly check (instant, no model needed)
    raw_dict = data.model_dump()
    anomalies = _anomaly_engine.analyse(pd.DataFrame(), raw_dict)
    for a in anomalies:
        db.add(Anomaly(
            device_id=data.device_id,
            anomaly_type=a["anomaly_type"],
            severity=a["severity"],
            description=a["description"],
        ))
        db.add(Alert(
            device_id=data.device_id,
            alert_type=a["anomaly_type"],
            message=a["description"],
            channel="dashboard",
        ))
    if anomalies:
        await db.commit()

    return reading


# ── GET /api/readings ─────────────────────────────────────────────────────────
@router.get("/readings")
async def get_readings(device_id: str = "METER_001",
                       limit: int = 288,
                       db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EnergyReading)
        .where(EnergyReading.device_id == device_id)
        .order_by(desc(EnergyReading.timestamp))
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id, "timestamp": r.timestamp.isoformat(),
            "voltage": r.voltage, "current": r.current,
            "power": r.power, "energy_kwh": r.energy_kwh,
            "balance": r.balance, "relay_on": r.relay_on, "theft": r.theft,
        }
        for r in reversed(rows)
    ]


# ── GET /api/heatmap ──────────────────────────────────────────────────────────
@router.get("/heatmap")
async def get_heatmap(device_id: str = "METER_001",
                      db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EnergyReading)
        .where(EnergyReading.device_id == device_id)
        .order_by(desc(EnergyReading.timestamp))
        .limit(2016)   # 7 days × 288 readings/day
    )
    rows = result.scalars().all()
    if not rows:
        return {"data": []}

    from backend.ai.data_preprocessing import EnergyPreprocessor
    df = pd.DataFrame([{"timestamp": r.timestamp, "power": r.power} for r in rows])
    pivot = EnergyPreprocessor.build_heatmap(df)

    # Serialise pivot to list of {hour, dow, value}
    data = []
    for hour in range(24):
        for dow in range(7):
            val = float(pivot.loc[hour, dow]) if (hour in pivot.index and dow in pivot.columns) else 0.0
            data.append({"hour": hour, "dow": dow, "value": round(val, 1)})
    return {"data": data}
