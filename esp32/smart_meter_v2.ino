/**
 * ============================================================
 * AIoT Smart Prepaid Energy Meter - ESP32 Firmware v2.0
 * ============================================================
 * Upgrades over v1:
 *  - MQTT publish instead of HTTP polling
 *  - NTP time sync for timestamped readings
 *  - Calibrated ACS712 current sensor reading
 *  - kWh energy accumulation
 *  - Power theft detection with configurable threshold
 *  - JSON telemetry every 5 seconds
 *  - Receives relay/recharge commands via MQTT subscription
 * ============================================================
 */

#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <time.h>

// ─── Pin Configuration ──────────────────────────────────────
#define VOLTAGE_PIN     34    // ADC1_CH6 – voltage sensor
#define CURRENT_PIN     35    // ADC1_CH7 – ACS712 current sensor
#define RELAY_PIN        2    // Relay control (active LOW)
#define THEFT_PIN       32    // Secondary voltage (bypass detect)

// ─── Network Configuration ──────────────────────────────────
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASS     = "YOUR_WIFI_PASSWORD";
const char* MQTT_BROKER   = "YOUR_SERVER_IP";   // e.g. 192.168.1.100
const int   MQTT_PORT     = 1883;
const char* MQTT_USER     = "energymeter";
const char* MQTT_PASS     = "meter2024";
const char* DEVICE_ID     = "METER_001";

// ─── MQTT Topics ────────────────────────────────────────────
const char* TOPIC_TELEMETRY  = "energy/meter/telemetry";
const char* TOPIC_ALERTS     = "energy/meter/alerts";
const char* TOPIC_CONTROL    = "energy/meter/control";   // Subscribe

// ─── Calibration Constants ──────────────────────────────────
// Voltage divider: Vin (0-250V AC) scaled to 0-3.3V via resistor divider
// Adjust VOLTAGE_SCALE based on your divider ratio
const float VOLTAGE_SCALE   = 93.75f;   // 250V / (3.3V * ADC_MAX/4095)
const float CURRENT_ZERO    = 2048.0f;  // ACS712 mid-point (2.5V on 12-bit)
const float CURRENT_SCALE   = 66.0f;   // ACS712-05B: 185 mV/A → 66 for 20A
const float RATE_PER_KWH    = 6.50f;   // ₹ per kWh

// ─── Thresholds ─────────────────────────────────────────────
const float THEFT_VOLTAGE_THRESHOLD = 1.5f;  // Volts difference for theft
const float LOW_BALANCE_THRESHOLD   = 50.0f; // ₹
const int   SEND_INTERVAL_MS        = 5000;  // 5 seconds

// ─── Global State ───────────────────────────────────────────
LiquidCrystal_I2C lcd(0x27, 16, 2);
WiFiClient        wifiClient;
PubSubClient      mqtt(wifiClient);

float   voltage   = 0.0f;
float   current   = 0.0f;
float   power     = 0.0f;       // Watts
float   energyKWh = 0.0f;       // Accumulated kWh
float   balance   = 100.0f;     // ₹ starting balance
bool    relayOn   = false;
bool    theftDetected = false;

unsigned long lastSendTime    = 0;
unsigned long lastEnergyTime  = 0;
unsigned long lastLcdUpdate   = 0;
int           lcdPage         = 0;

// ─── NTP ────────────────────────────────────────────────────
const char* NTP_SERVER  = "pool.ntp.org";
const long  GMT_OFFSET  = 19800;  // IST = UTC+5:30
const int   DAYLIGHT    = 0;

// ═══════════════════════════════════════════════════════════
// MQTT Callback – receive relay/recharge commands
// ═══════════════════════════════════════════════════════════
void onMqttMessage(char* topic, byte* payload, unsigned int len) {
  String msg;
  for (unsigned int i = 0; i < len; i++) msg += (char)payload[i];

  StaticJsonDocument<128> doc;
  if (deserializeJson(doc, msg) != DeserializationError::Ok) return;

  const char* cmd = doc["command"];
  if (!cmd) return;

  if (strcmp(cmd, "RELAY_ON") == 0 && balance > 0) {
    setRelay(true);
  } else if (strcmp(cmd, "RELAY_OFF") == 0) {
    setRelay(false);
  } else if (strcmp(cmd, "RECHARGE") == 0) {
    float amount = doc["amount"] | 0.0f;
    if (amount > 0) {
      balance += amount;
      lcd.clear();
      lcd.setCursor(0, 0); lcd.print("RECHARGE +" + String((int)amount));
      lcd.setCursor(0, 1); lcd.print("BAL: Rs." + String(balance, 0));
      delay(2000);
    }
  }
}

// ═══════════════════════════════════════════════════════════
// Relay helper
// ═══════════════════════════════════════════════════════════
void setRelay(bool state) {
  relayOn = state;
  digitalWrite(RELAY_PIN, state ? LOW : HIGH);  // Active LOW relay
}

// ═══════════════════════════════════════════════════════════
// MQTT reconnect
// ═══════════════════════════════════════════════════════════
void mqttReconnect() {
  int attempts = 0;
  while (!mqtt.connected() && attempts < 5) {
    lcd.setCursor(0, 1); lcd.print("MQTT connecting..");
    if (mqtt.connect(DEVICE_ID, MQTT_USER, MQTT_PASS)) {
      mqtt.subscribe(TOPIC_CONTROL);
    }
    attempts++;
    delay(1000);
  }
}

// ═══════════════════════════════════════════════════════════
// Read sensors (averaged over 20 samples)
// ═══════════════════════════════════════════════════════════
void readSensors() {
  long vSum = 0, iSum = 0, tSum = 0;
  const int N = 20;
  for (int s = 0; s < N; s++) {
    vSum += analogRead(VOLTAGE_PIN);
    iSum += analogRead(CURRENT_PIN);
    tSum += analogRead(THEFT_PIN);
    delayMicroseconds(500);
  }
  float vRaw = vSum / (float)N;
  float iRaw = iSum / (float)N;
  float tRaw = tSum / (float)N;

  // Convert to physical units
  voltage  = (vRaw / 4095.0f) * 3.3f * VOLTAGE_SCALE;
  current  = ((iRaw - CURRENT_ZERO) / 4095.0f) * 3.3f * CURRENT_SCALE;
  if (current < 0) current = 0;

  power    = voltage * current;  // Watts

  // Power theft: secondary voltage present but relay is OFF
  float theftV = (tRaw / 4095.0f) * 3.3f * VOLTAGE_SCALE;
  theftDetected = (!relayOn && theftV > THEFT_VOLTAGE_THRESHOLD);
}

// ═══════════════════════════════════════════════════════════
// Accumulate energy & deduct balance
// ═══════════════════════════════════════════════════════════
void updateEnergy() {
  unsigned long now = millis();
  float dtHours = (now - lastEnergyTime) / 3600000.0f;
  lastEnergyTime = now;

  if (relayOn && current > 0.01f) {
    float deltaKWh = (power / 1000.0f) * dtHours;
    energyKWh += deltaKWh;
    balance   -= deltaKWh * RATE_PER_KWH;
    if (balance < 0) balance = 0;
  }

  // Auto cut-off when balance exhausted
  if (balance <= 0 && relayOn) {
    setRelay(false);
    publishAlert("BALANCE_ZERO", "Balance exhausted. Power cut-off.");
  }

  if (balance < LOW_BALANCE_THRESHOLD && balance > 0) {
    publishAlert("LOW_BALANCE", "Balance below Rs.50. Recharge soon.");
  }
}

// ═══════════════════════════════════════════════════════════
// Publish alert via MQTT
// ═══════════════════════════════════════════════════════════
void publishAlert(const char* type, const char* msg) {
  StaticJsonDocument<128> doc;
  doc["device_id"] = DEVICE_ID;
  doc["alert_type"] = type;
  doc["message"]    = msg;
  char buf[160];
  serializeJson(doc, buf);
  mqtt.publish(TOPIC_ALERTS, buf);
}

// ═══════════════════════════════════════════════════════════
// Publish telemetry
// ═══════════════════════════════════════════════════════════
void publishTelemetry() {
  // Get current time
  struct tm timeinfo;
  char timestamp[32] = "0000-00-00T00:00:00";
  if (getLocalTime(&timeinfo)) {
    strftime(timestamp, sizeof(timestamp), "%Y-%m-%dT%H:%M:%S", &timeinfo);
  }

  StaticJsonDocument<256> doc;
  doc["device_id"]  = DEVICE_ID;
  doc["timestamp"]  = timestamp;
  doc["voltage"]    = serialized(String(voltage, 2));
  doc["current"]    = serialized(String(current, 3));
  doc["power"]      = serialized(String(power, 2));
  doc["energy_kwh"] = serialized(String(energyKWh, 4));
  doc["balance"]    = serialized(String(balance, 2));
  doc["relay"]      = relayOn;
  doc["theft"]      = theftDetected;

  char buf[300];
  serializeJson(doc, buf);
  mqtt.publish(TOPIC_TELEMETRY, buf);

  if (theftDetected) {
    publishAlert("THEFT", "Power theft detected! Bypass on secondary line.");
  }
}

// ═══════════════════════════════════════════════════════════
// LCD display (rotating pages)
// ═══════════════════════════════════════════════════════════
void updateLCD() {
  lcd.clear();
  switch (lcdPage) {
    case 0:
      lcd.setCursor(0, 0); lcd.print("V:" + String(voltage, 1) + "V I:" + String(current, 2) + "A");
      lcd.setCursor(0, 1); lcd.print("P:" + String(power, 1) + "W");
      break;
    case 1:
      lcd.setCursor(0, 0); lcd.print("Energy:");
      lcd.setCursor(0, 1); lcd.print(String(energyKWh, 4) + " kWh");
      break;
    case 2:
      lcd.setCursor(0, 0); lcd.print("BAL: Rs." + String(balance, 0));
      lcd.setCursor(0, 1); lcd.print(relayOn ? "RELAY:ON " : "RELAY:OFF");
      break;
    case 3:
      if (theftDetected) {
        lcd.setCursor(0, 0); lcd.print("!! THEFT !!");
        lcd.setCursor(0, 1); lcd.print("ALERT SENT");
      } else {
        lcd.setCursor(0, 0); lcd.print("SMART ENERGY");
        lcd.setCursor(0, 1); lcd.print("METER v2.0");
      }
      break;
  }
  lcdPage = (lcdPage + 1) % 4;
}

// ═══════════════════════════════════════════════════════════
// SETUP
// ═══════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);
  pinMode(RELAY_PIN, OUTPUT);
  setRelay(false);  // Start with relay OFF

  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0); lcd.print("Smart Energy");
  lcd.setCursor(0, 1); lcd.print("Meter v2.0 AI");
  delay(2000);

  // WiFi
  lcd.clear();
  lcd.setCursor(0, 0); lcd.print("Connecting WiFi");
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  int wifiTries = 0;
  while (WiFi.status() != WL_CONNECTED && wifiTries < 20) {
    delay(500);
    wifiTries++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    lcd.setCursor(0, 1); lcd.print("WiFi OK!");
  } else {
    lcd.setCursor(0, 1); lcd.print("WiFi FAILED");
  }
  delay(1000);

  // NTP
  configTime(GMT_OFFSET, DAYLIGHT, NTP_SERVER);

  // MQTT
  mqtt.setServer(MQTT_BROKER, MQTT_PORT);
  mqtt.setCallback(onMqttMessage);
  mqttReconnect();

  lastEnergyTime = millis();
  lastSendTime   = millis();
  lastLcdUpdate  = millis();

  lcd.clear();
}

// ═══════════════════════════════════════════════════════════
// LOOP
// ═══════════════════════════════════════════════════════════
void loop() {
  if (!mqtt.connected()) mqttReconnect();
  mqtt.loop();

  readSensors();
  updateEnergy();

  unsigned long now = millis();

  if (now - lastSendTime >= SEND_INTERVAL_MS) {
    publishTelemetry();
    lastSendTime = now;
  }

  if (now - lastLcdUpdate >= 3000) {
    updateLCD();
    lastLcdUpdate = now;
  }

  delay(100);
}
