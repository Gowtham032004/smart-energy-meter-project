"""
models/energy.py — ORM models for the Smart Energy Platform
"""
from datetime import datetime
from sqlalchemy import String, Float, Boolean, DateTime, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database import Base


class EnergyReading(Base):
    """Raw telemetry from ESP32 device."""
    __tablename__ = "energy_readings"

    id:         Mapped[int]   = mapped_column(Integer, primary_key=True, index=True)
    device_id:  Mapped[str]   = mapped_column(String(32), index=True)
    timestamp:  Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    voltage:    Mapped[float] = mapped_column(Float, default=0.0)
    current:    Mapped[float] = mapped_column(Float, default=0.0)
    power:      Mapped[float] = mapped_column(Float, default=0.0)       # Watts
    energy_kwh: Mapped[float] = mapped_column(Float, default=0.0)       # Cumulative kWh
    balance:    Mapped[float] = mapped_column(Float, default=0.0)       # ₹ remaining
    relay_on:   Mapped[bool]  = mapped_column(Boolean, default=True)
    theft:      Mapped[bool]  = mapped_column(Boolean, default=False)


class Prediction(Base):
    """AI model predictions (LSTM output)."""
    __tablename__ = "predictions"

    id:           Mapped[int]   = mapped_column(Integer, primary_key=True, index=True)
    device_id:    Mapped[str]   = mapped_column(String(32), index=True)
    created_at:   Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    horizon_hrs:  Mapped[int]   = mapped_column(Integer)          # 1, 24, or 168 (7d)
    predicted_kwh: Mapped[float] = mapped_column(Float)
    predicted_cost: Mapped[float] = mapped_column(Float)
    confidence:   Mapped[float] = mapped_column(Float, default=0.0)


class Anomaly(Base):
    """Anomalies detected by ML engine."""
    __tablename__ = "anomalies"

    id:           Mapped[int]   = mapped_column(Integer, primary_key=True, index=True)
    device_id:    Mapped[str]   = mapped_column(String(32), index=True)
    detected_at:  Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    anomaly_type: Mapped[str]   = mapped_column(String(50))   # THEFT | SPIKE | UNUSUAL
    severity:     Mapped[str]   = mapped_column(String(10))   # LOW | MEDIUM | HIGH
    description:  Mapped[str]   = mapped_column(Text)
    resolved:     Mapped[bool]  = mapped_column(Boolean, default=False)


class Alert(Base):
    """Alerts sent to user (SMS / Email)."""
    __tablename__ = "alerts"

    id:           Mapped[int]   = mapped_column(Integer, primary_key=True, index=True)
    device_id:    Mapped[str]   = mapped_column(String(32), index=True)
    alert_type:   Mapped[str]   = mapped_column(String(50))
    message:      Mapped[str]   = mapped_column(Text)
    sent_at:      Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    channel:      Mapped[str]   = mapped_column(String(10), default="dashboard")  # email|sms|dashboard


class User(Base):
    """User / device account."""
    __tablename__ = "users"

    id:           Mapped[int]   = mapped_column(Integer, primary_key=True, index=True)
    device_id:    Mapped[str]   = mapped_column(String(32), unique=True, index=True)
    name:         Mapped[str]   = mapped_column(String(100))
    email:        Mapped[str]   = mapped_column(String(150), nullable=True)
    phone:        Mapped[str]   = mapped_column(String(20), nullable=True)
    balance:      Mapped[float] = mapped_column(Float, default=0.0)
    rate_per_kwh: Mapped[float] = mapped_column(Float, default=6.50)
    user_type:    Mapped[str]   = mapped_column(String(10), default="medium")  # low|medium|high


class Recharge(Base):
    """Recharge transactions."""
    __tablename__ = "recharges"

    id:         Mapped[int]   = mapped_column(Integer, primary_key=True, index=True)
    device_id:  Mapped[str]   = mapped_column(String(32), index=True)
    amount:     Mapped[float] = mapped_column(Float)
    timestamp:  Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    method:     Mapped[str]   = mapped_column(String(20), default="manual")
