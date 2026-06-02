// ─────────────────────────────────────────────────────────────────────────────
// ORION · ESP32 de SENSORES (Wokwi / hardware real)
// Publica temperatura + humedad (DHT22) y luz (LDR) por MQTT cada 5 s.
//
// Topics que publica:
//   orion/zahir/esp_sensores/dht   → JSON {"temperatura":24.3,"humedad":55.1}
//   orion/zahir/esp_sensores/ldr   → string crudo, ej. "742"
//
// Para pasar del simulador Wokwi al ESP32 real solo cambia:
//   - WIFI_SSID y WIFI_PASS  (en Wokwi se usa Wokwi-GUEST sin contraseña)
//   - MQTT_HOST              (cuando tengas Mosquitto local, pon su IP)
// ─────────────────────────────────────────────────────────────────────────────
#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>

// ── Config WiFi ────────────────────────────────────────────────────────────
const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASS = "";

// ── Config MQTT ────────────────────────────────────────────────────────────
const char* MQTT_HOST    = "broker.hivemq.com";
const uint16_t MQTT_PORT = 1883;
const char* MQTT_CLIENT  = "orion-esp-sensores-zahir";

const char* TOPIC_DHT = "orion/zahir/esp_sensores/dht";
const char* TOPIC_LDR = "orion/zahir/esp_sensores/ldr";

// ── Pines (ESP32-S3) ───────────────────────────────────────────────────────
// DHT22 en GPIO 15 (digital genérico, libre en S3).
// LDR  en GPIO 4 (ADC1_CH3 — seguro con WiFi activo, en S3 no existe el 34).
#define DHT_PIN  15
#define DHT_TYPE DHT22
#define LDR_PIN  4

// ── Periodo de envío ───────────────────────────────────────────────────────
const unsigned long ENVIO_MS = 5000;

DHT dht(DHT_PIN, DHT_TYPE);
WiFiClient netClient;
PubSubClient mqtt(netClient);
unsigned long ultimoEnvio = 0;

// ───────────────────────────────────────────────────────────────────────────
void conectarWiFi() {
  Serial.printf("[WiFi] conectando a %s ", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
    Serial.print(".");
  }
  Serial.printf(" OK  IP=%s\n", WiFi.localIP().toString().c_str());
}

void conectarMQTT() {
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  while (!mqtt.connected()) {
    Serial.printf("[MQTT] conectando a %s:%u ... ", MQTT_HOST, MQTT_PORT);
    if (mqtt.connect(MQTT_CLIENT)) {
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
  dht.begin();
  conectarWiFi();
  conectarMQTT();
}

void loop() {
  if (!mqtt.connected()) conectarMQTT();
  mqtt.loop();

  unsigned long ahora = millis();
  if (ahora - ultimoEnvio < ENVIO_MS) return;
  ultimoEnvio = ahora;

  // ── DHT22 ──────────────────────────────────────────────────────────────
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

  // ── LDR ────────────────────────────────────────────────────────────────
  int luz = analogRead(LDR_PIN);   // 0..4095
  char ldrPayload[8];
  snprintf(ldrPayload, sizeof(ldrPayload), "%d", luz);
  mqtt.publish(TOPIC_LDR, ldrPayload);
  Serial.printf("[PUB] %s = %s\n", TOPIC_LDR, ldrPayload);
}
