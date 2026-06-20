// ─────────────────────────────────────────────────────────────────────────────
// ORION · ESP32-S3 N16R8 — DHT22/AM2302 + BH1750 → MQTT
//
// Publica:
//   orion/zahir/esp_sensores/dht   → JSON {"temperatura":24.3,"humedad":55.1}
//   orion/zahir/esp_sensores/lux   → string crudo, ej. "382.50"
//
// Cableado (ESP32-S3 N16R8 dev module):
//   DHT22 / AM2302
//     VCC  → 3V3
//     GND  → GND
//     DATA → GPIO 15   (con resistencia pull-up 4.7k–10k a 3V3 si tu módulo
//                       no la trae integrada; los módulos de 3 pines ya la tienen)
//   BH1750 (I2C)
//     VCC  → 3V3
//     GND  → GND
//     SDA  → GPIO 8
//     SCL  → GPIO 9
//     ADDR → libre (deja flotando para 0x23) o a 3V3 para 0x5C
//
// Librerías a instalar desde el Library Manager del Arduino IDE:
//   • "DHT sensor library" by Adafruit  (+ Adafruit Unified Sensor)
//   • "BH1750" by Christopher Laws
//   • "PubSubClient" by Nick O'Leary
//
// Placa: "ESP32S3 Dev Module", Flash 16MB, PSRAM "OPI PSRAM".
// ─────────────────────────────────────────────────────────────────────────────
#include <WiFi.h>
#include <Wire.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <BH1750.h>

// ── Config WiFi ────────────────────────────────────────────────────────────
const char* WIFI_SSID = "TU_WIFI";
const char* WIFI_PASS = "TU_PASSWORD";

// ── Config MQTT ────────────────────────────────────────────────────────────
const char* MQTT_HOST    = "broker.hivemq.com";
const uint16_t MQTT_PORT = 1883;
const char* MQTT_CLIENT  = "orion-esp-sensores-zahir";

const char* TOPIC_DHT = "orion/zahir/esp_sensores/dht";
const char* TOPIC_LUX = "orion/zahir/esp_sensores/lux";

// ── Pines ──────────────────────────────────────────────────────────────────
#define DHT_PIN   15
#define DHT_TYPE  DHT22
#define I2C_SDA   8
#define I2C_SCL   9

// ── Periodo de envío ───────────────────────────────────────────────────────
const unsigned long ENVIO_MS = 5000;

DHT dht(DHT_PIN, DHT_TYPE);
BH1750 lightMeter;            // dirección por defecto 0x23
WiFiClient netClient;
PubSubClient mqtt(netClient);
unsigned long ultimoEnvio = 0;
bool bh1750_ok = false;

// ───────────────────────────────────────────────────────────────────────────
void conectarWiFi() {
  Serial.printf("[WiFi] conectando a %s ", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
    Serial.print(".");
    if (millis() - t0 > 20000) {     // reintenta si tarda demasiado
      Serial.println(" timeout, reintento");
      WiFi.disconnect();
      WiFi.begin(WIFI_SSID, WIFI_PASS);
      t0 = millis();
    }
  }
  Serial.printf(" OK  IP=%s\n", WiFi.localIP().toString().c_str());
}

void conectarMQTT() {
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  while (!mqtt.connected()) {
    Serial.printf("[MQTT] conectando a %s:%u ... ", MQTT_HOST, MQTT_PORT);
    // client_id único por chip para evitar choques en el broker público
    String cid = String(MQTT_CLIENT) + "-" + String((uint32_t)ESP.getEfuseMac(), HEX);
    if (mqtt.connect(cid.c_str())) {
      Serial.println("OK");
    } else {
      Serial.printf("falló rc=%d, reintento en 2s\n", mqtt.state());
      delay(2000);
    }
  }
}

// ───────────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\n# orion-esp32 sensores DHT22 + BH1750");

  dht.begin();

  Wire.begin(I2C_SDA, I2C_SCL);
  if (lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE)) {
    bh1750_ok = true;
    Serial.println("[BH1750] OK @ 0x23");
  } else {
    // Reintento en 0x5C por si ADDR está en alto
    if (lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE, 0x5C)) {
      bh1750_ok = true;
      Serial.println("[BH1750] OK @ 0x5C");
    } else {
      Serial.println("[BH1750] no responde — revisa SDA/SCL/VCC");
    }
  }

  conectarWiFi();
  conectarMQTT();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) conectarWiFi();
  if (!mqtt.connected()) conectarMQTT();
  mqtt.loop();

  unsigned long ahora = millis();
  if (ahora - ultimoEnvio < ENVIO_MS) return;
  ultimoEnvio = ahora;

  // ── DHT22 ────────────────────────────────────────────────────────────────
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  if (isnan(t) || isnan(h)) {
    Serial.println("[DHT] lectura inválida");
  } else {
    char payload[64];
    snprintf(payload, sizeof(payload),
             "{\"temperatura\":%.1f,\"humedad\":%.1f}", t, h);
    mqtt.publish(TOPIC_DHT, payload);
    Serial.printf("[PUB] %s = %s\n", TOPIC_DHT, payload);
  }

  // ── BH1750 ───────────────────────────────────────────────────────────────
  if (bh1750_ok) {
    float lux = lightMeter.readLightLevel();    // lx
    if (lux < 0) {
      Serial.println("[BH1750] lectura inválida");
    } else {
      char luxPayload[16];
      snprintf(luxPayload, sizeof(luxPayload), "%.2f", lux);
      mqtt.publish(TOPIC_LUX, luxPayload);
      Serial.printf("[PUB] %s = %s\n", TOPIC_LUX, luxPayload);
    }
  }
}
