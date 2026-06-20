// ─────────────────────────────────────────────────────────────────────────────
// ORION · ESP32-S3 N16R8 — Escáner de redes WiFi
//
// Escanea todas las redes 2.4 GHz al alcance y las imprime por USB Serial
// ordenadas por intensidad (RSSI). Útil para:
//   • Confirmar que tu router está visible antes de configurar otro sketch.
//   • Saber el canal y el tipo de cifrado de cada red.
//   • Medir cobertura caminando con la placa por la casa.
//
// Salida (cada ~5 s):
//   # | RSSI |  Ch | Cifrado     | BSSID             | SSID
//   1 |  -42 |   6 | WPA2-PSK    | A4:2B:B0:11:22:33 | MiWiFi
//   2 |  -67 |  11 | WPA2/WPA3   | 70:F1:1C:44:55:66 | TotalPlay-1234
//   …
//
// Placa: "ESP32S3 Dev Module". No requiere librerías extra (sólo WiFi.h del core).
// ─────────────────────────────────────────────────────────────────────────────
#include <WiFi.h>

const unsigned long INTERVALO_MS = 5000;   // pausa entre escaneos
const bool MOSTRAR_OCULTAS       = true;   // incluir redes con SSID vacío
const bool ESCANEO_ACTIVO        = false;  // false = pasivo (más limpio)

const char* cifradoStr(wifi_auth_mode_t m) {
  switch (m) {
    case WIFI_AUTH_OPEN:            return "Abierta";
    case WIFI_AUTH_WEP:             return "WEP";
    case WIFI_AUTH_WPA_PSK:         return "WPA-PSK";
    case WIFI_AUTH_WPA2_PSK:        return "WPA2-PSK";
    case WIFI_AUTH_WPA_WPA2_PSK:    return "WPA/WPA2";
    case WIFI_AUTH_WPA2_ENTERPRISE: return "WPA2-Ent";
    case WIFI_AUTH_WPA3_PSK:        return "WPA3-PSK";
    case WIFI_AUTH_WPA2_WPA3_PSK:   return "WPA2/WPA3";
    default:                        return "Desconocido";
  }
}

// Barra visual rápida del nivel de señal (0 = muerto, 4 = lleno).
int barrasRSSI(int rssi) {
  if (rssi >= -55) return 4;
  if (rssi >= -65) return 3;
  if (rssi >= -75) return 2;
  if (rssi >= -85) return 1;
  return 0;
}

void imprimirCabecera(int total) {
  Serial.printf("\n=== %d redes encontradas ===\n", total);
  Serial.println(" # | RSSI |  Ch | Cifrado     | BSSID             | SSID");
  Serial.println("---+------+-----+-------------+-------------------+----------------------");
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\n# orion-wifi-scanner listo");

  // Modo STA sin conectarse a nada — necesario para escanear.
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true, true);
  delay(100);
}

void loop() {
  Serial.println("\n[scan] buscando redes...");
  // scanNetworks(async, show_hidden, passive, max_ms_per_chan)
  int n = WiFi.scanNetworks(false, MOSTRAR_OCULTAS, !ESCANEO_ACTIVO, 300);

  if (n <= 0) {
    Serial.println("[scan] sin resultados");
  } else {
    // scanNetworks ya devuelve ordenado por RSSI descendente en el core actual,
    // pero lo dejamos explícito por si cambia.
    imprimirCabecera(n);
    for (int i = 0; i < n; i++) {
      String ssid = WiFi.SSID(i);
      if (ssid.length() == 0) ssid = "<oculta>";
      int rssi = WiFi.RSSI(i);
      int barras = barrasRSSI(rssi);
      char barraTxt[6] = "....";
      for (int b = 0; b < barras && b < 4; b++) barraTxt[b] = '#';

      Serial.printf("%2d | %4d | %3d | %-11s | %s | %s  [%s]\n",
                    i + 1,
                    rssi,
                    WiFi.channel(i),
                    cifradoStr(WiFi.encryptionType(i)),
                    WiFi.BSSIDstr(i).c_str(),
                    ssid.c_str(),
                    barraTxt);
    }
  }

  WiFi.scanDelete();   // libera memoria de los resultados
  delay(INTERVALO_MS);
}
