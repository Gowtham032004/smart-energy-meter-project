"""
ai/data_preprocessing.py
========================
Feature engineering pipeline for the Smart Energy Platform.
Converts raw energy_readings rows into ML-ready feature matrices.
"""
import numpy as np
import pandas as pd
from typing import Optional


# ─── Constants ────────────────────────────────────────────────────────────────
SEQUENCE_LEN = 48   # 48 × 5-min intervals = 4 hours of history for LSTM input
FEATURES = ["power", "voltage", "current", "hour_sin", "hour_cos",
            "day_sin", "day_cos", "is_weekend", "rolling_mean_1h",
            "rolling_std_1h", "rolling_mean_6h"]


# ─── Main preprocessing class ─────────────────────────────────────────────────
class EnergyPreprocessor:
    """
    Transforms raw DataFrame (from DB) into feature matrices for LSTM/anomaly models.
    """

    def __init__(self, sequence_len: int = SEQUENCE_LEN):
        self.sequence_len = sequence_len
        self.scaler_params: Optional[dict] = None   # {mean, std} per feature

    # ── Raw → Feature DataFrame ────────────────────────────────────────────────
    def build_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Expects df with columns: timestamp, voltage, current, power, energy_kwh, balance
        Returns enriched DataFrame with temporal + rolling features.
        """
        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").reset_index(drop=True)

        # ── Temporal features (cyclic encoding) ────────────────────────────────
        df["hour"]      = df["timestamp"].dt.hour + df["timestamp"].dt.minute / 60
        df["dayofweek"] = df["timestamp"].dt.dayofweek
        df["hour_sin"]  = np.sin(2 * np.pi * df["hour"] / 24)
        df["hour_cos"]  = np.cos(2 * np.pi * df["hour"] / 24)
        df["day_sin"]   = np.sin(2 * np.pi * df["dayofweek"] / 7)
        df["day_cos"]   = np.cos(2 * np.pi * df["dayofweek"] / 7)
        df["is_weekend"] = (df["dayofweek"] >= 5).astype(float)

        # ── Rolling statistics ──────────────────────────────────────────────────
        df["rolling_mean_1h"]  = df["power"].rolling(window=12, min_periods=1).mean()
        df["rolling_std_1h"]   = df["power"].rolling(window=12, min_periods=1).std().fillna(0)
        df["rolling_mean_6h"]  = df["power"].rolling(window=72, min_periods=1).mean()

        return df[["timestamp"] + FEATURES]

    # ── Normalise ──────────────────────────────────────────────────────────────
    def fit_normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Fit mean/std on training data and normalise."""
        feat_df = df[FEATURES]
        self.scaler_params = {
            "mean": feat_df.mean().to_dict(),
            "std":  feat_df.std().replace(0, 1).to_dict(),
        }
        return self._apply_norm(df)

    def transform_normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply previously fitted normalisation."""
        if self.scaler_params is None:
            raise RuntimeError("Call fit_normalize first.")
        return self._apply_norm(df)

    def _apply_norm(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        for feat in FEATURES:
            mean = self.scaler_params["mean"][feat]
            std  = self.scaler_params["std"][feat]
            df[feat] = (df[feat] - mean) / std
        return df

    def inverse_power(self, val: float) -> float:
        """Inverse normalise a power prediction."""
        mean = self.scaler_params["mean"]["power"]
        std  = self.scaler_params["std"]["power"]
        return val * std + mean

    # ── Sequence builder ───────────────────────────────────────────────────────
    def make_sequences(self, df: pd.DataFrame, target: str = "power"):
        """
        Build (X, y) pairs for LSTM training.
        X shape: (N, sequence_len, n_features)
        y shape: (N,)
        """
        data   = df[FEATURES].values
        labels = df[target].values
        X, y   = [], []
        for i in range(self.sequence_len, len(data)):
            X.append(data[i - self.sequence_len:i])
            y.append(labels[i])
        return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)

    # ── Heatmap builder ────────────────────────────────────────────────────────
    @staticmethod
    def build_heatmap(df: pd.DataFrame) -> pd.DataFrame:
        """
        Returns pivot: rows = hour of day (0-23), cols = day of week (0-6),
        values = mean power (W).
        """
        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["hour"]      = df["timestamp"].dt.hour
        df["dow"]       = df["timestamp"].dt.dayofweek
        pivot = df.groupby(["hour", "dow"])["power"].mean().unstack(fill_value=0)
        return pivot

    # ── Budget predictor helper ────────────────────────────────────────────────
    @staticmethod
    def estimate_hours_remaining(balance: float, recent_df: pd.DataFrame,
                                 rate_per_kwh: float = 6.5) -> float:
        """
        Given current balance and recent readings, estimate hours of usage remaining.
        """
        if len(recent_df) == 0 or balance <= 0:
            return 0.0
        avg_power_w = recent_df["power"].mean()
        if avg_power_w < 1:
            return float("inf")
        avg_power_kw = avg_power_w / 1000.0
        cost_per_hour = avg_power_kw * rate_per_kwh
        return balance / cost_per_hour
