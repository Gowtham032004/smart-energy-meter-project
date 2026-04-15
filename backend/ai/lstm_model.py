"""
ai/lstm_model.py
================
Bidirectional LSTM model for time-series energy consumption forecasting.
Predicts next 1h / 24h / 7d energy usage.

Architecture
────────────
Input  → BiLSTM(128) → Dropout(0.3)
       → BiLSTM(64)  → Dropout(0.2)
       → Dense(32, relu)
       → Dense(1)     [power in Watts]
"""
import os
import json
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Tuple, Optional

# ── Lazy TensorFlow import (avoids slow startup) ──────────────────────────────
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

MODEL_DIR   = Path(__file__).parent / "saved_models"
MODEL_PATH  = MODEL_DIR / "lstm_energy.h5"
SCALER_PATH = MODEL_DIR / "scaler_params.json"

SEQUENCE_LEN = 48    # 4 h history (5-min samples)
N_FEATURES   = 11   # must match FEATURES list in data_preprocessing.py


# ─── Build model ──────────────────────────────────────────────────────────────
def build_model(sequence_len: int = SEQUENCE_LEN,
                n_features: int = N_FEATURES) -> "tf.keras.Model":
    import tensorflow as tf
    from tensorflow import keras

    inp = keras.Input(shape=(sequence_len, n_features), name="input")

    x = keras.layers.Bidirectional(
        keras.layers.LSTM(128, return_sequences=True, name="bilstm_1"),
        name="bi_1"
    )(inp)
    x = keras.layers.Dropout(0.3)(x)

    x = keras.layers.Bidirectional(
        keras.layers.LSTM(64, return_sequences=False, name="bilstm_2"),
        name="bi_2"
    )(x)
    x = keras.layers.Dropout(0.2)(x)

    x = keras.layers.Dense(32, activation="relu", name="dense_1")(x)
    x = keras.layers.Dense(16, activation="relu", name="dense_2")(x)
    out = keras.layers.Dense(1, name="output")(x)

    model = keras.Model(inputs=inp, outputs=out, name="EnergyLSTM")
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=1e-3),
        loss="huber",
        metrics=["mae"]
    )
    return model


# ─── Training ─────────────────────────────────────────────────────────────────
def train(X: np.ndarray, y: np.ndarray,
          epochs: int = 50,
          batch_size: int = 64,
          validation_split: float = 0.15) -> dict:
    """
    Train the LSTM model. Returns training history dict.
    X shape: (N, SEQUENCE_LEN, N_FEATURES)
    y shape: (N,)
    """
    import tensorflow as tf
    from tensorflow import keras

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model = build_model()

    callbacks = [
        keras.callbacks.EarlyStopping(patience=8, restore_best_weights=True,
                                      monitor="val_loss"),
        keras.callbacks.ReduceLROnPlateau(factor=0.5, patience=4,
                                          min_lr=1e-6),
        keras.callbacks.ModelCheckpoint(str(MODEL_PATH), save_best_only=True,
                                        monitor="val_loss"),
    ]

    hist = model.fit(
        X, y,
        epochs=epochs,
        batch_size=batch_size,
        validation_split=validation_split,
        callbacks=callbacks,
        verbose=1,
    )
    return hist.history


# ─── Inference ────────────────────────────────────────────────────────────────
def load_model():
    import tensorflow as tf
    if not MODEL_PATH.exists():
        return None
    return tf.keras.models.load_model(str(MODEL_PATH))


def predict_next(X_seq: np.ndarray,
                 model=None,
                 scaler_mean: float = 0.0,
                 scaler_std: float = 1.0) -> float:
    """
    Predict next step power (W) from a single sequence.
    X_seq shape: (1, SEQUENCE_LEN, N_FEATURES)
    Returns denormalised power in Watts.
    """
    if model is None:
        model = load_model()
    if model is None:
        raise RuntimeError("No trained model found. Run training first.")
    norm_pred = float(model.predict(X_seq, verbose=0)[0][0])
    return max(0.0, norm_pred * scaler_std + scaler_mean)


def predict_horizon(last_sequence: np.ndarray,
                    horizon_steps: int,
                    model=None,
                    scaler_mean: float = 0.0,
                    scaler_std: float = 1.0,
                    step_minutes: int = 5) -> list:
    """
    Multi-step autoregressive forecast.
    Returns list of (minutes_ahead, predicted_watts) tuples.
    """
    if model is None:
        model = load_model()

    results = []
    seq = last_sequence.copy()   # shape (1, SEQUENCE_LEN, N_FEATURES)

    for step in range(horizon_steps):
        norm_pred = float(model.predict(seq, verbose=0)[0][0])
        watts = max(0.0, norm_pred * scaler_std + scaler_mean)
        results.append({
            "minutes_ahead": (step + 1) * step_minutes,
            "predicted_watts": round(watts, 2),
            "predicted_kwh":   round(watts / 1000 * (step_minutes / 60), 5),
        })
        # Shift window: drop oldest, append new
        new_step = seq[0, -1, :].copy()
        new_step[0] = norm_pred   # update 'power' feature (index 0)
        seq = np.roll(seq, -1, axis=1)
        seq[0, -1, :] = new_step

    return results


# ─── Summary helper ───────────────────────────────────────────────────────────
def get_horizon_summary(predictions: list, rate_per_kwh: float = 6.5) -> dict:
    """Aggregate step predictions into 1h / 24h / 7d summaries."""
    total_kwh  = sum(p["predicted_kwh"] for p in predictions)
    n_steps    = len(predictions)
    hours      = n_steps * 5 / 60
    avg_watts  = sum(p["predicted_watts"] for p in predictions) / max(n_steps, 1)
    cost       = total_kwh * rate_per_kwh

    return {
        "total_kwh":   round(total_kwh, 4),
        "avg_watts":   round(avg_watts, 2),
        "total_hours": round(hours, 2),
        "est_cost_rs": round(cost, 2),
    }
