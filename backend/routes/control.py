"""
routes/control.py — Relay control, recharge, anomaly management
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, update
from datetime import datetime

from backend.database import get_db
from backend.models.energy import EnergyReading, Anomaly, Alert, Recharge, User

router = APIRouter(prefix="/api", tags=["control"])


class RelayCmd(BaseModel):
    device_id: str = "METER_001"
    state:     bool   # True = ON, False = OFF


class RechargeCmd(BaseModel):
    device_id: str = "METER_001"
    amount:    float
    method:    str = "dashboard"


# ── POST /api/control/relay ───────────────────────────────────────────────────
@router.post("/control/relay")
async def control_relay(cmd: RelayCmd, db: AsyncSession = Depends(get_db)):
    """
    Stores the relay command as an alert; ESP32 polls /api/control/pending.
    """
    db.add(Alert(
        device_id=cmd.device_id,
        alert_type="RELAY_CMD",
        message=f"RELAY_{'ON' if cmd.state else 'OFF'}",
        channel="mqtt",
    ))
    await db.commit()
    return {"status": "queued", "relay": cmd.state}


# ── POST /api/recharge ────────────────────────────────────────────────────────
@router.post("/recharge")
async def recharge(cmd: RechargeCmd, db: AsyncSession = Depends(get_db)):
    if cmd.amount <= 0:
        raise HTTPException(400, "Amount must be > 0")

    # Get latest reading → update balance
    result = await db.execute(
        select(EnergyReading)
        .where(EnergyReading.device_id == cmd.device_id)
        .order_by(desc(EnergyReading.timestamp))
        .limit(1)
    )
    latest = result.scalars().first()
    new_balance = (latest.balance if latest else 0) + cmd.amount

    # Log recharge
    db.add(Recharge(device_id=cmd.device_id, amount=cmd.amount, method=cmd.method))
    db.add(Alert(
        device_id=cmd.device_id,
        alert_type="RECHARGE",
        message=f"Recharge of ₹{cmd.amount:.0f} credited. New balance: ₹{new_balance:.2f}",
        channel="dashboard",
    ))
    await db.commit()

    return {
        "status":      "success",
        "amount":      cmd.amount,
        "new_balance": round(new_balance, 2),
        "message":     f"₹{cmd.amount:.0f} recharged successfully",
    }


# ── GET /api/anomalies ────────────────────────────────────────────────────────
@router.get("/anomalies")
async def list_anomalies(device_id: str = "METER_001",
                         limit: int = 20,
                         db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Anomaly)
        .where(Anomaly.device_id == device_id)
        .order_by(desc(Anomaly.detected_at))
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "id": a.id, "type": a.anomaly_type, "severity": a.severity,
            "description": a.description,
            "detected_at": a.detected_at.isoformat(), "resolved": a.resolved,
        }
        for a in rows
    ]


# ── PATCH /api/anomalies/{id}/resolve ─────────────────────────────────────────
@router.patch("/anomalies/{anomaly_id}/resolve")
async def resolve_anomaly(anomaly_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Anomaly).where(Anomaly.id == anomaly_id))
    a = result.scalars().first()
    if not a:
        raise HTTPException(404, "Anomaly not found")
    a.resolved = True
    await db.commit()
    return {"status": "resolved", "id": anomaly_id}


# ── GET /api/alerts ───────────────────────────────────────────────────────────
@router.get("/alerts")
async def list_alerts(device_id: str = "METER_001",
                      limit: int = 20,
                      db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Alert)
        .where(Alert.device_id == device_id)
        .order_by(desc(Alert.sent_at))
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "id": a.id, "type": a.alert_type, "message": a.message,
            "sent_at": a.sent_at.isoformat(), "channel": a.channel,
        }
        for a in rows
    ]


# ── GET /api/recharges ────────────────────────────────────────────────────────
@router.get("/recharges")
async def list_recharges(device_id: str = "METER_001",
                         limit: int = 20,
                         db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Recharge)
        .where(Recharge.device_id == device_id)
        .order_by(desc(Recharge.timestamp))
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        {"id": r.id, "amount": r.amount,
         "timestamp": r.timestamp.isoformat(), "method": r.method}
        for r in rows
    ]
