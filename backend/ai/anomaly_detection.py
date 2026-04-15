"""
ai/anomaly_detection.py
=======================
Dual-engine anomaly detection:
  1. Isolation Forest  – unsupervised statistical outlier detection
  2. Autoencoder       – deep reconstruction-error based detection
  3. Rule-based        – instant theft / spike checks (no model needed)
"""
import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from typing import List, Dict

MODEL_DIR       = Path(__file__).parent / "saved_models"
ISO_PATH        = MODEL_DIR / "isolation_forest.pkl"
AUTOENC_PATH    = MODEL_DIR / "autoencoder.h5"

FEATURES = ["power", "voltage", "current", "rolling_mean_1h", "rolling_std_1h"]

# ─── Isolation Forest ─────────────────────────────────────────────────────────
class IsolationForestDetector:
    def __init__(self, contamination: float = 0.05):
        from sklearn.ensemble import IsolationForest
        self.model = IsolationForest(
            n_estimators=200,
            contamination=contamination,
            random_state=42,
            n_jobs=-1,
        )
        self.fitted = False

    def fit(self, df: pd.DataFrame):
        X = df[FEATURES].fillna(0).values
        self.model.fit(X)
        self.fitted = True
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, ISO_PATH)

    def load(self):
        if ISO_PATH.exists():
            self.model = joblib.load(ISO_PATH)
            self.fitted = True
        return self

    def score(self, df: pd.DataFrame) -> np.ndarray:
        """Returns anomaly scores (more negative = more anomalous)."""
        if not self.fitted:
            self.load()
        X = df[FEATURES].fillna(0).values
        return self.model.score_samples(X)

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Returns -1 for anomaly, 1 for normal."""
        if not self.fitted:
            self.load()
        X = df[FEATURES].fillna(0).values
        return self.model.predict(X)


# ─── Autoencoder ─────────────────────────────────────────────────────────────
def build_autoencoder(n_features: int = len(FEATURES)):
    import tensorflow as tf
    from tensorflow import keras
    inp  = keras.Input(shape=(n_features,))
    enc  = keras.layers.Dense(16, activation="relu")(inp)
    enc  = keras.layers.Dense(8,  activation="relu")(enc)
    lat  = keras.layers.Dense(4,  activation="relu")(enc)
    dec  = keras.layers.Dense(8,  activation="relu")(lat)
    dec  = keras.layers.Dense(16, activation="relu")(dec)
    out  = keras.layers.Dense(n_features)(dec)
    ae   = keras.Model(inputs=inp, outputs=out, name="Autoencoder")
    ae.compile(optimizer="adam", loss="mse")
    return ae


class AutoencoderDetector:
    def __init__(self, threshold_percentile: float = 95):
        self.model     = None
        self.threshold = None
        self.pct       = threshold_percentile

    def fit(self, df: pd.DataFrame, epochs: int = 30):
        import tensorflow as tf
        X = df[FEATURES].fillna(0).values.astype(np.float32)
        self.model = build_autoencoder(X.shape[1])
        self.model.fit(X, X, epochs=epochs, batch_size=64,
                       validation_split=0.1, verbose=0)
        recon_err  = np.mean((X - self.model.predict(X, verbose=0))**2, axis=1)
        self.threshold = np.percentile(recon_err, self.pct)
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        self.model.save(str(AUTOENC_PATH))

    def load(self):
        import tensorflow as tf
        if AUTOENC_PATH.exists():
            self.model = tf.keras.models.load_model(str(AUTOENC_PATH))
        return self

    def reconstruction_error(self, df: pd.DataFrame) -> np.ndarray:
        X = df[FEATURES].fillna(0).values.astype(np.float32)
        preds = self.model.predict(X, verbose=0)
        return np.mean((X - preds)**2, axis=1)

    def is_anomaly(self, df: pd.DataFrame) -> np.ndarray:
        err = self.reconstruction_error(df)
        return err > (self.threshold or np.inf)


# ─── Rule-based (instant, no model needed) ────────────────────────────────────
def rule_based_check(reading: dict) -> List[Dict]:
    """
    Fast threshold checks on a single reading dict.
    Returns list of anomaly dicts (may be empty).
    """
    alerts = []

    voltage = reading.get("voltage", 0)
    current = reading.get("current", 0)
    power   = reading.get("power", 0)
    relay   = reading.get("relay_on", True)
    theft   = reading.get("theft", False)

    # Power theft: device reports bypass
    if theft:
        alerts.append({
            "anomaly_type": "THEFT",
            "severity":     "HIGH",
            "description":  f"Power bypass detected on secondary line. "
                            f"Current: {current:.2f}A, Voltage: {voltage:.1f}V"
        })

    # Current spike (> 20A assumed max)
    if current > 20:
        alerts.append({
            "anomaly_type": "SPIKE",
            "severity":     "HIGH",
            "description":  f"Dangerously high current detected: {current:.2f}A"
        })

    # Relay OFF but power still flowing
    if not relay and power > 50:
        alerts.append({
            "anomaly_type": "THEFT",
            "severity":     "MEDIUM",
            "description":  f"Power flowing ({power:.0f}W) while relay is OFF."
        })

    # Over voltage
    if voltage > 260:
        alerts.append({
            "anomaly_type": "OVERVOLTAGE",
            "severity":     "MEDIUM",
            "description":  f"Over-voltage detected: {voltage:.1f}V"
        })

    # Under voltage
    if 0 < voltage < 170:
        alerts.append({
            "anomaly_type": "UNDERVOLTAGE",
            "severity":     "LOW",
            "description":  f"Under-voltage detected: {voltage:.1f}V"
        })

    return alerts


# ─── Combined detector facade ─────────────────────────────────────────────────
class AnomalyEngine:
    """
    Unified facade combining rule-based + Isolation Forest detection.
    """
    def __init__(self):
        self.iso = IsolationForestDetector()

    def analyse(self, df: pd.DataFrame, latest_reading: dict) -> List[Dict]:
        """
        Full analysis:
        1. Rule-based instant check on latest reading
        2. Isolation Forest on recent window
        Returns combined list of anomaly dicts.
        """
        results = []

        # 1. Rule-based
        results.extend(rule_based_check(latest_reading))

        # 2. ISO Forest (if model available)
        try:
            self.iso.load()
            if self.iso.fitted and len(df) >= 10:
                labels = self.iso.predict(df)
                scores = self.iso.score(df)
                anomaly_rows = df[labels == -1]
                for idx, row in anomaly_rows.iterrows():
                    if scores[idx] < -0.3:   # confidence threshold
                        results.append({
                            "anomaly_type": "UNUSUAL",
                            "severity":     "MEDIUM",
                            "description":  (
                                f"Unusual usage pattern at "
                                f"{row.get('timestamp','?')} — "
                                f"Power: {row.get('power',0):.0f}W, "
                                f"Score: {scores[idx]:.3f}"
                            )
                        })
        except Exception:
            pass

        return results
