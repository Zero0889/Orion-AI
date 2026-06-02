// ─────────────────────────────────────────────────────────────────────────────
// ORION · Arduino con 2 relés (focos) + LM35 (temperatura)
// Conexiones:
//   D2 → IN1 módulo relé (foco 1) — relé ACTIVO EN LOW
//   D3 → IN2 módulo relé (foco 2) — relé ACTIVO EN LOW
//   A0 → salida del LM35
//
// Protocolo serial @ 9600 baud (newline-terminated):
//   IN  ← ORION publica:  "FOCO1_ON"|"FOCO1_OFF"|"FOCO2_ON"|"FOCO2_OFF"
//                         "TODOS_ON"|"TODOS_OFF"
//   OUT → Arduino publica: "TEMPERATURA:23.45"   (cada 1 s, no bloquea comandos)
//
// Mejoras vs. versión anterior:
//   ✓ Sin delay(1000) bloqueante: comandos atendidos al instante.
//   ✓ Sin prints redundantes del setup (que ORION leería como ruido).
//   ✓ Comparación con un único if/else encadenado y limpio.
//   ✓ Buffer fijo para evitar fragmentación de heap del String.
// ─────────────────────────────────────────────────────────────────────────────

const int PIN_FOCO_1 = 2;
const int PIN_FOCO_2 = 3;
const int PIN_LM35   = A0;

// Relé activo en LOW (los baratos chinos): HIGH = apagado, LOW = encendido.
// Si tu módulo es active-high cambia estas dos constantes:
const int RELAY_ON  = LOW;
const int RELAY_OFF = HIGH;

// Cada cuánto se publica la lectura de temperatura
const unsigned long INTERVALO_TEMP_MS = 1000;

unsigned long ultimaTemp = 0;

// Buffer para construir comandos byte a byte (más eficiente que String)
char  cmdBuf[24];
uint8_t cmdLen = 0;

// ─────────────────────────────────────────────────────────────────────────────
void aplicarFoco(int pin, bool encender) {
  digitalWrite(pin, encender ? RELAY_ON : RELAY_OFF);
}

void ejecutarComando(const char* cmd) {
  if      (!strcmp(cmd, "FOCO1_ON"))  aplicarFoco(PIN_FOCO_1, true);
  else if (!strcmp(cmd, "FOCO1_OFF")) aplicarFoco(PIN_FOCO_1, false);
  else if (!strcmp(cmd, "FOCO2_ON"))  aplicarFoco(PIN_FOCO_2, true);
  else if (!strcmp(cmd, "FOCO2_OFF")) aplicarFoco(PIN_FOCO_2, false);
  else if (!strcmp(cmd, "TODOS_ON"))  { aplicarFoco(PIN_FOCO_1, true);  aplicarFoco(PIN_FOCO_2, true);  }
  else if (!strcmp(cmd, "TODOS_OFF")) { aplicarFoco(PIN_FOCO_1, false); aplicarFoco(PIN_FOCO_2, false); }
  // Comandos desconocidos se ignoran silenciosamente — no contaminar el bus.
}

void leerSerialNoBloqueante() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;                     // ignora CR de Windows
    if (c == '\n') {                             // fin de línea → procesar
      cmdBuf[cmdLen] = '\0';
      if (cmdLen > 0) ejecutarComando(cmdBuf);
      cmdLen = 0;
    } else if (cmdLen < sizeof(cmdBuf) - 1) {
      cmdBuf[cmdLen++] = c;
    } else {
      // Overflow defensivo: descarta y reinicia el buffer
      cmdLen = 0;
    }
  }
}

void publicarTemperatura() {
  int   lectura     = analogRead(PIN_LM35);
  float voltaje     = lectura * (5.0f / 1023.0f);
  float temperatura = voltaje * 100.0f;          // LM35: 10 mV/°C
  Serial.print(F("TEMPERATURA:"));
  Serial.println(temperatura, 2);                // 2 decimales
}

// ─────────────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(9600);

  pinMode(PIN_FOCO_1, OUTPUT);
  pinMode(PIN_FOCO_2, OUTPUT);
  aplicarFoco(PIN_FOCO_1, false);                // apagados al arrancar
  aplicarFoco(PIN_FOCO_2, false);

  // Una sola línea de banner: útil para diagnosticar pero no se confunde con
  // un dato de sensor (no contiene ":" en formato PREFIX:value reconocible).
  Serial.println(F("# orion-arduino ready"));
}

void loop() {
  // 1) Atender comandos entrantes al instante (sin bloquear).
  leerSerialNoBloqueante();

  // 2) Publicar temperatura cada INTERVALO_TEMP_MS, sin parar de leer comandos.
  unsigned long ahora = millis();
  if (ahora - ultimaTemp >= INTERVALO_TEMP_MS) {
    ultimaTemp = ahora;
    publicarTemperatura();
  }
}
