// ─────────────────────────────────────────────────────────────────────────────
// ORION · ESP32 — Control de acceso por huella (AS608) + reporte a Orion
//
// Flujo:
//   1. Loop esperando dedo en el sensor AS608.
//   2. Match → activa relé (cerradura/foco) + LED verde + buzzer corto.
//   3. POST JSON al endpoint /api/access/event de Orion (Tailscale o LAN).
//   4. Orion guarda en SQLite, calcula entrada/salida y manda Telegram.
//
// Endpoint esperado por Orion (ya está implementado en
// orion/server/routes/access.py):
//   POST http://<orion-host>:8765/api/access/event
//   {
//     "fingerprint_id": 1,      // slot 0-127; -1 si DENIED
//     "event_type": "GRANTED",  // "GRANTED" | "DENIED"
//     "esp_id": "esp-acceso-puerta",
//     "confidence": 142         // score del AS608
//   }
//
// Cableado típico (ESP32 dev kit):
//   AS608 fingerprint
//     VCC  → 3V3
//     GND  → GND
//     TX   → GPIO 16 (RX2 del ESP)
//     RX   → GPIO 17 (TX2 del ESP)
//   Relé activo-bajo (cerradura/foco)
//     IN   → GPIO 26
//   LED OK     → GPIO 25 (verde)
//   LED DENIED → GPIO 33 (rojo)
//   Buzzer    → GPIO 27
//
// Librerías:
//   • "Adafruit Fingerprint Sensor Library"
//   • "ArduinoJson"
// Placa: "ESP32 Dev Module" (o ESP32-S3, ajustar pines si hace falta).
// ─────────────────────────────────────────────────────────────────────────────
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Adafruit_Fingerprint.h>

// ── Config WiFi ────────────────────────────────────────────────────────────
const char* WIFI_SSID = "TU_WIFI";
const char* WIFI_PASS = "TU_PASSWORD";

// ── Config Orion ───────────────────────────────────────────────────────────
// Reemplazar con la IP local o Tailscale de la máquina que corre Orion.
const char* ORION_URL = "http://192.168.1.50:8765/api/access/event";
const char* ESP_ID    = "esp-acceso-puerta";

// Shared secret — DEBE coincidir con `shared_secret` en
// `config/access.json` del backend. Sin esto, el SharingMiddleware
// rechaza el POST con 403 porque el ESP32 vive en la LAN, no en
// loopback ni Tailscale. Rotalo cuando quieras (regenerá en la PC con
// `python -c "import secrets; print(secrets.token_urlsafe(32))"` y
// reflasheá este sketch + actualizá el JSON).
const char* ACCESS_TOKEN = "PEGA_AQUI_EL_VALOR_DE_config/access.json";

// ── Pines ──────────────────────────────────────────────────────────────────
#define FP_RX 16
#define FP_TX 17
#define PIN_RELE       26
#define PIN_LED_OK     25
#define PIN_LED_DENIED 33
#define PIN_BUZZER     27

// Relé "activo bajo" (la mayoría de módulos): LOW = abierto, HIGH = cerrado.
const bool RELE_ACTIVE_LOW = true;
const unsigned long PUERTA_ABIERTA_MS = 3000;     // tiempo que queda activado el relé
const unsigned long DEBOUNCE_MS       = 1500;     // ignora repeticiones del mismo dedo

HardwareSerial fpSerial(2);
Adafruit_Fingerprint finger = Adafruit_Fingerprint(&fpSerial);

unsigned long ultimoMatch = 0;
int ultimoSlot = -1;

// ── Helpers ────────────────────────────────────────────────────────────────
void releAbrir() {
  digitalWrite(PIN_RELE, RELE_ACTIVE_LOW ? LOW : HIGH);
}
void releCerrar() {
  digitalWrite(PIN_RELE, RELE_ACTIVE_LOW ? HIGH : LOW);
}

void beep(int ms, int veces = 1) {
  for (int i = 0; i < veces; i++) {
    digitalWrite(PIN_BUZZER, HIGH);
    delay(ms);
    digitalWrite(PIN_BUZZER, LOW);
    if (i + 1 < veces) delay(100);
  }
}

void conectarWiFi() {
  Serial.printf("[wifi] conectando a %s...\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) {
    delay(250);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[wifi] OK, IP=%s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("[wifi] timeout — seguimos sin red, reintenta en el loop");
  }
}

// Envía el evento a Orion. Si no hay WiFi, intenta reconectar antes.
void enviarEventoOrion(int slot, const char* tipo, int confidence) {
  if (WiFi.status() != WL_CONNECTED) {
    conectarWiFi();
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("[http] sin WiFi — evento se pierde");
      return;
    }
  }

  HTTPClient http;
  http.begin(ORION_URL);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Orion-Access-Token", ACCESS_TOKEN);
  http.setTimeout(4000);

  StaticJsonDocument<200> doc;
  doc["fingerprint_id"] = slot;
  doc["event_type"]     = tipo;
  doc["esp_id"]         = ESP_ID;
  doc["confidence"]     = confidence;

  String payload;
  serializeJson(doc, payload);

  int code = http.POST(payload);
  Serial.printf("[http] POST %s → %d\n", tipo, code);
  http.end();
}

// ── Setup ──────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(PIN_RELE, OUTPUT);
  pinMode(PIN_LED_OK, OUTPUT);
  pinMode(PIN_LED_DENIED, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  releCerrar();
  digitalWrite(PIN_LED_OK, LOW);
  digitalWrite(PIN_LED_DENIED, LOW);
  digitalWrite(PIN_BUZZER, LOW);

  // AS608 — baud por defecto 57600.
  fpSerial.begin(57600, SERIAL_8N1, FP_RX, FP_TX);
  delay(100);
  if (finger.verifyPassword()) {
    Serial.println("[fp] sensor AS608 OK");
  } else {
    Serial.println("[fp] NO encuentro el AS608 — chequear cableado");
    while (true) {
      digitalWrite(PIN_LED_DENIED, HIGH);
      delay(200);
      digitalWrite(PIN_LED_DENIED, LOW);
      delay(200);
    }
  }
  finger.getTemplateCount();
  Serial.printf("[fp] huellas registradas en el sensor: %d\n", finger.templateCount);

  conectarWiFi();

  // Heartbeat de arranque: dos beeps cortos + LED OK 200ms.
  beep(60, 2);
  digitalWrite(PIN_LED_OK, HIGH);
  delay(200);
  digitalWrite(PIN_LED_OK, LOW);
}

// ── Lectura de huella ─────────────────────────────────────────────────────
// Devuelve slot (>=0) si hubo match, -1 si no había dedo o falló.
int leerHuella(int &confidence) {
  uint8_t p = finger.getImage();
  if (p == FINGERPRINT_NOFINGER) return -1;
  if (p != FINGERPRINT_OK) return -1;

  p = finger.image2Tz();
  if (p != FINGERPRINT_OK) return -1;

  p = finger.fingerSearch();
  if (p != FINGERPRINT_OK) {
    confidence = 0;
    return -2;  // dedo detectado pero no matchea (DENIED)
  }
  confidence = finger.confidence;
  return finger.fingerID;
}

// ── Loop ───────────────────────────────────────────────────────────────────
void loop() {
  int confidence = 0;
  int slot = leerHuella(confidence);

  if (slot >= 0) {
    // Debounce: si es el mismo slot dentro de DEBOUNCE_MS, lo ignoramos.
    if (slot == ultimoSlot && millis() - ultimoMatch < DEBOUNCE_MS) {
      delay(50);
      return;
    }
    ultimoSlot  = slot;
    ultimoMatch = millis();

    Serial.printf("[fp] GRANTED slot=%d conf=%d\n", slot, confidence);
    digitalWrite(PIN_LED_OK, HIGH);
    beep(80, 1);
    releAbrir();
    enviarEventoOrion(slot, "GRANTED", confidence);
    delay(PUERTA_ABIERTA_MS);
    releCerrar();
    digitalWrite(PIN_LED_OK, LOW);
  } else if (slot == -2) {
    Serial.println("[fp] DENIED — sin match");
    digitalWrite(PIN_LED_DENIED, HIGH);
    beep(300, 1);
    enviarEventoOrion(-1, "DENIED", 0);
    delay(800);
    digitalWrite(PIN_LED_DENIED, LOW);
  }

  delay(40);
}
