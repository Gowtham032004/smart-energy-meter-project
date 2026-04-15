"""
sample_data_generator.py
========================
Generates 7 days of realistic synthetic energy meter data and seeds the database.
Run once before the dashboard to have something to visualise.

Usage:
    python -m backend.sample_data_generator
"""
import asyncio
import random
import math
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from backend.models.energy import EnergyReading, Anomaly, Alert, User, Recharge, Base

DATABASE_URL = "sqlite+aiosqlite:///./energy_meter.db"

DEVICE_ID    = "METER_001"
RATE         = 6.5          # ₹ per kWh
START_BAL    = 500.0
SAMPLE_MIN   = 5            # 5-minute interval
DAYS         = 7


def simulate_power(hour: float, dow: int) -> float:
    """
    Realistic household power profile (Watts):
    - Low overnight (0–5h)
    - Morning ramp (5–9h)
    - Midday moderate (9–17h)
    - Evening peak (17–22h)
    - Night taper
    Weekend is ~20% higher
    """
    # Base sinusoidal profile
    base = 200 + 500 * (
        0.3 * math.sin(math.pi * (hour - 6) / 12)
      + 0.5 * math.sin(math.pi * (hour - 18) / 6)
    )
    base = max(base, 80)

    # Weekend bump
    if dow >= 5:
        base *= 1.2

    # Random noise ±10%
    base *= random.uniform(0.90, 1.10)
    return round(base, 2)


async def seed():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        # ── Create user ────────────────────────────────────────────────────────
        db.add(User(
            device_id=DEVICE_ID, name="Demo User",
            email="demo@smartmeter.io", phone="+919876543210",
            balance=START_BAL, rate_per_kwh=RATE, user_type="medium",
        ))

        # ── Generate readings ──────────────────────────────────────────────────
        now     = datetime.utcnow()
        start   = now - timedelta(days=DAYS)
        balance = START_BAL
        cumulative_kwh = 0.0
        ts      = start
        interval_h = SAMPLE_MIN / 60.0

        print(f"Seeding {DAYS * 24 * 60 // SAMPLE_MIN} readings…")
        batch = []

        while ts <= now:
            hour = ts.hour + ts.minute / 60
            dow  = ts.weekday()

            voltage = round(random.uniform(218, 242), 1)
            power   = simulate_power(hour, dow)
            current = round(power / max(voltage, 1), 3)
            delta_kwh = power / 1000 * interval_h
            cumulative_kwh += delta_kwh
            balance -= delta_kwh * RATE
            balance  = max(balance, 0.0)

            # Inject occasional theft / spike anomaly
            theft  = False
            if random.random() < 0.002:   # 0.2% chance
                theft = True
            if random.random() < 0.001:
                power *= 3    # spike

            batch.append(EnergyReading(
                device_id=DEVICE_ID, timestamp=ts,
                voltage=voltage, current=current, power=round(power, 2),
                energy_kwh=round(cumulative_kwh, 4),
                balance=round(balance, 2),
                relay_on=balance > 0,
                theft=theft,
            ))

            if theft:
                db.add(Anomaly(
                    device_id=DEVICE_ID, detected_at=ts,
                    anomaly_type="THEFT", severity="HIGH",
                    description=f"Power bypass detected at {ts.strftime('%Y-%m-%d %H:%M')}."
                ))

            ts += timedelta(minutes=SAMPLE_MIN)

        db.add_all(batch)

        # ── Recharge midway ────────────────────────────────────────────────────
        db.add(Recharge(device_id=DEVICE_ID, amount=200.0,
                        timestamp=start + timedelta(days=3), method="online"))

        # ── Sample alert ───────────────────────────────────────────────────────
        db.add(Alert(device_id=DEVICE_ID, alert_type="LOW_BALANCE",
                     message="Balance below ₹50. Recharge recommended.",
                     channel="dashboard"))

        await db.commit()
        print(f"Database seeded successfully with {len(batch)} readings.")
        print(f"    Final balance: ₹{balance:.2f}  |  Total kWh: {cumulative_kwh:.3f}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
