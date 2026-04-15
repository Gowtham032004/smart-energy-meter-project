# 🚀 AIoT Smart Energy Platform — Deployment Guide

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | ≥ 3.10 | python.org |
| Node.js | ≥ 18 | nodejs.org |
| Arduino IDE | ≥ 2.x | arduino.cc |
| MQTT Broker | Mosquitto | mosquitto.org |

---

## 📁 Project Structure

```
smart-energy-platform/
├── esp32/
│   └── smart_meter_v2.ino      ← Upload to ESP32
├── backend/
│   ├── main.py                  ← FastAPI app
│   ├── database.py
│   ├── requirements.txt
│   ├── sample_data_generator.py
│   ├── models/energy.py
│   ├── routes/
│   │   ├── telemetry.py
│   │   ├── predictions.py
│   │   ├── agent.py
│   │   └── control.py
│   └── ai/
│       ├── data_preprocessing.py
│       ├── lstm_model.py
│       ├── anomaly_detection.py
│       ├── recommendations.py
│       └── budget_predictor.py
└── dashboard/
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── App.jsx
        ├── index.css
        ├── main.jsx
        └── pages/
            ├── Dashboard.jsx
            ├── Analytics.jsx
            └── AgentPage.jsx
```

---

## 🐍 Backend Setup

### Step 1 — Install Python dependencies
```bash
cd smart-energy-platform
pip install -r backend/requirements.txt
```

### Step 2 — Seed the database (7 days of synthetic data)
```bash
python -m backend.sample_data_generator
```

### Step 3 — Start FastAPI server
```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

API docs available at: **http://localhost:8000/docs**

---

## ⚛️ Dashboard Setup

### Step 1 — Install Node dependencies
```bash
cd dashboard
npm install
```

### Step 2 — Start dev server
```bash
npm run dev
```

Dashboard available at: **http://localhost:5173**

---

## 📡 MQTT Broker (Mosquitto)

### Install on Windows
```
winget install mosquitto
```

### Start broker
```bash
mosquitto -c mosquitto.conf -v
```

### Test MQTT
```bash
# Subscribe to telemetry
mosquitto_sub -t "energy/meter/telemetry" -v

# Publish test command
mosquitto_pub -t "energy/meter/control" -m '{"command":"RELAY_ON"}'
```

---

## 🔧 ESP32 Configuration

1. Open `esp32/smart_meter_v2.ino` in Arduino IDE 2.x
2. Install libraries from Library Manager:
   - `PubSubClient` by Nick O'Leary
   - `ArduinoJson` by Benoit Blanchon
   - `LiquidCrystal_I2C` by Frank de Brabander
3. Update credentials in firmware:
   ```cpp
   const char* WIFI_SSID   = "YOUR_WIFI_SSID";
   const char* WIFI_PASS   = "YOUR_WIFI_PASSWORD";
   const char* MQTT_BROKER = "192.168.1.100";  // Your PC's IP
   ```
4. Select **ESP32 Dev Module** → Upload

---

## 🌐 API Endpoints Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/telemetry` | Receive ESP32 sensor data |
| `GET`  | `/api/readings`  | Historical readings |
| `GET`  | `/api/predictions?horizon=24` | LSTM forecast |
| `GET`  | `/api/balance`   | Balance + expiry forecast |
| `GET`  | `/api/insights`  | AI recommendations |
| `GET`  | `/api/heatmap`   | Hour×Day usage heatmap |
| `GET`  | `/api/alerts`    | Alert history |
| `GET`  | `/api/anomalies` | Detected anomalies |
| `POST` | `/api/agent/chat` | AI agent chat |
| `POST` | `/api/control/relay` | Toggle relay |
| `POST` | `/api/recharge`  | Recharge balance |
| `GET`  | `/api/recharges` | Recharge history |

---

## 🤖 LSTM Model Training

After collecting ≥ 2 days of real data:

```python
import asyncio, pandas as pd
from backend.ai.data_preprocessing import EnergyPreprocessor
from backend.ai.lstm_model import train

# Load your data
df = pd.read_csv("readings.csv")  # or pull from DB

prep = EnergyPreprocessor()
feat_df = prep.build_features(df)
feat_df = prep.fit_normalize(feat_df)

X, y = prep.make_sequences(feat_df)
history = train(X, y, epochs=50)
print("Training complete!")
```

---

## 🔒 Security Hardening

```python
# Add to main.py for JWT auth
from fastapi.security import OAuth2PasswordBearer
from jose import jwt

SECRET_KEY = "your-secret-key-here"
ALGORITHM  = "HS256"
```

Add `.env` file:
```
SECRET_KEY=your-256-bit-secret
SMTP_HOST=smtp.gmail.com
SMTP_USER=alerts@yourdomain.com
TWILIO_SID=ACxxxxxxxx
```

---

## ☁️ Cloud Deployment (Render / Railway)

### Backend
```bash
# Procfile
web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

### Dashboard
```bash
cd dashboard
npm run build
# Deploy dist/ to Vercel / Netlify
```

---

## 📊 Database Schema

```sql
energy_readings  (id, device_id, timestamp, voltage, current,
                  power, energy_kwh, balance, relay_on, theft)

predictions      (id, device_id, created_at, horizon_hrs,
                  predicted_kwh, predicted_cost, confidence)

anomalies        (id, device_id, detected_at, anomaly_type,
                  severity, description, resolved)

alerts           (id, device_id, alert_type, message, sent_at, channel)

users            (id, device_id, name, email, phone,
                  balance, rate_per_kwh, user_type)

recharges        (id, device_id, amount, timestamp, method)
```

---

## 📡 Sample ESP32 Telemetry JSON

```json
{
  "device_id":  "METER_001",
  "timestamp":  "2026-04-15T17:30:00",
  "voltage":    231.4,
  "current":    2.135,
  "power":      493.8,
  "energy_kwh": 12.4567,
  "balance":    342.80,
  "relay_on":   true,
  "theft":      false
}
```

**POST to:** `http://your-server:8000/api/telemetry`

---

## ✅ Verification Checklist

- [ ] Backend starts: `curl http://localhost:8000/health`
- [ ] DB seeded: readings visible at `/api/readings`
- [ ] Dashboard loads: `http://localhost:5173`
- [ ] KPI cards populate with live/seeded data
- [ ] AI Agent responds to "show meter status"
- [ ] Analytics heatmap renders
- [ ] Recharge button works (POST `/api/recharge`)
- [ ] Relay toggle queues command (POST `/api/control/relay`)
