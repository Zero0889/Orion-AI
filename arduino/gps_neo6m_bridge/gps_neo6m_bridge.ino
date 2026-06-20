// ─────────────────────────────────────────────────────────────────────────────
// ORION · ESP32-S3 (N16R8) ↔ GPS NEO-6M  —  puente NMEA por USB
//
// Cableado (ESP32-S3 lado izquierdo del módulo NEO-6M):
//   NEO-6M VCC → 5V   (el módulo con regulador acepta 5V; si el tuyo es bare
//                      poneo a 3V3 — confírmalo mirando si trae LDO)
//   NEO-6M GND → GND
//   NEO-6M TX  → GPIO 18  (RX1 del ESP32)
//   NEO-6M RX  → GPIO 17  (TX1 del ESP32)   ← opcional, sólo si vas a mandar UBX
//
// USB:  Selecciona la placa "ESP32S3 Dev Module" en Arduino IDE y sube.
//       Luego ejecuta:  python tools/gps_test.py --port COM6
//
// Protocolo:
//   - Todo lo que entra por Serial1 (9600 baud, NMEA) se reenvía tal cual a
//     USB Serial (115200 baud).
//   - Cada 5 s emite un latido "ORION_GPS_BRIDGE:alive" para que el script
//     Python confirme que el firmware corre, aunque el GPS aún no tenga fix.
// ─────────────────────────────────────────────────────────────────────────────

constexpr int PIN_GPS_RX = 18;   // ESP32 RX1  ← TX del NEO-6M
constexpr int PIN_GPS_TX = 17;   // ESP32 TX1  → RX del NEO-6M
constexpr uint32_t BAUD_USB = 115200;
constexpr uint32_t HEARTBEAT_MS = 5000;

// Probaremos en este orden hasta detectar datos. Los clones recientes del
// NEO-6M suelen venir a 38400; los originales a 9600.
const uint32_t BAUD_CANDIDATES[] = {9600, 38400, 19200, 4800, 57600, 115200};
constexpr size_t N_BAUDS = sizeof(BAUD_CANDIDATES) / sizeof(BAUD_CANDIDATES[0]);
constexpr uint32_t SCAN_DWELL_MS = 3500;   // tiempo en cada baud antes de saltar

size_t baudIdx = 0;
uint32_t currentBaud = 0;
uint32_t baudStartedAt = 0;
bool baudLocked = false;
uint32_t bytesIn = 0;
uint32_t bytesAtScanStart = 0;
uint32_t lastBeat = 0;

static void applyBaud(size_t idx) {
  Serial1.end();
  delay(40);
  currentBaud = BAUD_CANDIDATES[idx];
  Serial1.begin(currentBaud, SERIAL_8N1, PIN_GPS_RX, PIN_GPS_TX);
  baudStartedAt = millis();
  bytesAtScanStart = bytesIn;
  Serial.printf("ORION_GPS_BRIDGE:scan trying baud=%lu (%u/%u)\n",
                (unsigned long)currentBaud,
                (unsigned)(idx + 1), (unsigned)N_BAUDS);
}

void setup() {
  Serial.begin(BAUD_USB);
  delay(400);
  Serial.println("ORION_GPS_BRIDGE:boot");
  Serial.printf("ORION_GPS_BRIDGE:cfg rx=%d tx=%d (autobaud)\n",
                PIN_GPS_RX, PIN_GPS_TX);
  applyBaud(baudIdx);
}

void loop() {
  // GPS → USB
  while (Serial1.available()) {
    int c = Serial1.read();
    Serial.write(c);
    bytesIn++;
  }

  // USB → GPS (por si quieres enviar comandos UBX/PUBX a mano)
  while (Serial.available()) {
    Serial1.write(Serial.read());
  }

  uint32_t now = millis();

  // Autodetección de baudrate: si en SCAN_DWELL_MS no entra ningún byte,
  // probamos el siguiente. En cuanto entran datos, fijamos ese baudrate.
  if (!baudLocked) {
    if (bytesIn > bytesAtScanStart) {
      baudLocked = true;
      Serial.printf("ORION_GPS_BRIDGE:locked baud=%lu\n",
                    (unsigned long)currentBaud);
    } else if (now - baudStartedAt >= SCAN_DWELL_MS) {
      baudIdx = (baudIdx + 1) % N_BAUDS;
      applyBaud(baudIdx);
    }
  }

  // Heartbeat: sirve para detectar "firmware ok, pero NEO-6M sin señal".
  if (now - lastBeat >= HEARTBEAT_MS) {
    lastBeat = now;
    Serial.printf("ORION_GPS_BRIDGE:alive bytes_in=%lu baud=%lu locked=%d\n",
                  (unsigned long)bytesIn,
                  (unsigned long)currentBaud,
                  baudLocked ? 1 : 0);
  }
}
