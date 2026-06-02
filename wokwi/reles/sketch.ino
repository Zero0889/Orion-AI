// ─────────────────────────────────────────────────────────────────────────────
// ORION · ESP32 de RELÉS (Wokwi / hardware real)
// Escucha comandos de ORION y enciende/apaga 2 focos vía relé.
//
// Topics:
//   orion/zahir/foco_1/set     ← ORION publica "ON" / "OFF"
//   orion/zahir/foco_1/state   → ESP32 publica estado real tras el cambio
//   orion/zahir/foco_2/set
//   orion/zahir/foco_2/state
//
// En Wokwi los relés se simulan con LEDs. En el ESP32 real cambia los pines
// a los IN1/IN2 del módulo relé (lógica típicamente INVERTIDA: LOW = ON).
// Si tu módulo es active-low, cambia RELAY_ACTIVE_LOW a true.
// ─────────────────────────────────────────────────────────────────────────────
#include <WiFi.h>
#include <PubSubClient.h>

const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASS = "";

const char* MQTT_HOST    = "broker.hivemq.com";
const uint16_t MQTT_PORT = 1883;
const char* MQTT_CLIENT  = "orion-esp-reles-zahir";

// ── Topics ─────────────────────────────────────────────────────────────────
const char* TOPIC_F1_SET   = "orion/zahir/foco_1/set";
const char* TOPIC_F1_STATE = "orion/zahir/foco_1/state";
const char* TOPIC_F2_SET   = "orion/zahir/foco_2/set";
const char* TOPIC_F2_STATE = "orion/zahir/foco_2/state";

// ── Pines (ESP32-S3) ───────────────────────────────────────────────────────
// En Wokwi son LEDs; en hardware real, IN1/IN2 del módulo relé.
// En S3 los GPIO 26/27 NO existen — usamos 5 y 6 (libres y seguros).
#define PIN_FOCO_1 5
#define PIN_FOCO_2 6

// Módulos relé baratos suelen activarse con LOW. En Wokwi (LED) lo dejamos
// en false para que LOW=apagado y HIGH=encendido (intuitivo visualmente).
const bool RELAY_ACTIVE_LOW = false;

WiFiClient netClient;
PubSubClient mqtt(netClient);

bool estadoFoco1 = false;
bool estadoFoco2 = false;

// ───────────────────────────────────────────────────────────────────────────
void aplicarFoco(int pin, bool encendido) {
  if (RELAY_ACTIVE_LOW) {
    digitalWrite(pin, encendido ? LOW : HIGH);
  } else {
    digitalWrite(pin, encendido ? HIGH : LOW);
  }
}

void publicarEstado(const char* topic, bool encendido) {
  mqtt.publish(topic, encendido ? "ON" : "OFF", true);  // retain=true
  Serial.printf("[PUB] %s = %s\n", topic, encendido ? "ON" : "OFF");
}

// ───────────────────────────────────────────────────────────────────────────
void onMensaje(char* topic, byte* payload, unsigned int len) {
  // Normaliza el payload a un string corto en mayúsculas
  char buf[16] = {0};
  size_t n = len < sizeof(buf) - 1 ? len : sizeof(buf) - 1;
  for (size_t i = 0; i < n; i++) buf[i] = toupper(payload[i]);
  Serial.printf("[SUB] %s = %s\n", topic, buf);

  bool on = (strcmp(buf, "ON") == 0 || strcmp(buf, "1") == 0 ||
             strcmp(buf, "TRUE") == 0);
  bool off = (strcmp(buf, "OFF") == 0 || strcmp(buf, "0") == 0 ||
              strcmp(buf, "FALSE") == 0);
  if (!on && !off) return;

  if (strcmp(topic, TOPIC_F1_SET) == 0) {
    estadoFoco1 = on;
    aplicarFoco(PIN_FOCO_1, estadoFoco1);
    publicarEstado(TOPIC_F1_STATE, estadoFoco1);
  } else if (strcmp(topic, TOPIC_F2_SET) == 0) {
    estadoFoco2 = on;
    aplicarFoco(PIN_FOCO_2, estadoFoco2);
    publicarEstado(TOPIC_F2_STATE, estadoFoco2);
  }
}

// ───────────────────────────────────────────────────────────────────────────
void conectarWiFi() {
  Serial.printf("[WiFi] conectando a %s ", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) { delay(250); Serial.print("."); }
  Serial.printf(" OK  IP=%s\n", WiFi.localIP().toString().c_str());
}

void conectarMQTT() {
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMensaje);
  while (!mqtt.connected()) {
    Serial.printf("[MQTT] conectando a %s:%u ... ", MQTT_HOST, MQTT_PORT);
    if (mqtt.connect(MQTT_CLIENT)) {
      Serial.println("OK");
      mqtt.subscribe(TOPIC_F1_SET);
      mqtt.subscribe(TOPIC_F2_SET);
      // Publica estado inicial para que ORION sepa cómo arrancamos
      publicarEstado(TOPIC_F1_STATE, estadoFoco1);
      publicarEstado(TOPIC_F2_STATE, estadoFoco2);
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
  pinMode(PIN_FOCO_1, OUTPUT);
  pinMode(PIN_FOCO_2, OUTPUT);
  aplicarFoco(PIN_FOCO_1, false);
  aplicarFoco(PIN_FOCO_2, false);
  conectarWiFi();
  conectarMQTT();
}

void loop() {
  if (!mqtt.connected()) conectarMQTT();
  mqtt.loop();
}
