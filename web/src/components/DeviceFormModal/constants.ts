/**
 * Constantes + tipos + helpers puros del DeviceFormModal.
 *
 * Lo que vive acá NO depende de React ni de useState — son datos
 * estáticos (catálogos de DEVICE_KINDS, SENSOR_PRESETS, TRANSPORT_KINDS)
 * y funciones puras (slugify, kindFromDevice, isObj). Las separamos
 * del index para que la sección "lógica de presentación" (el componente
 * de 900+ LOC con todo el state) quede aislada.
 */

import type { IconName } from "@/ui/Icon";
import type { IoTDevice } from "@/api/rest";
import type { DeviceConfig } from "@/hooks/useDeviceConfig";
import type { SensorKind } from "@/hooks/useDeviceConfig";

export type Mode = "create" | "edit-local" | "edit-backend";
export type TransportType = "mqtt" | "serial" | "custom";
export type DeviceKind = "light" | "switch" | "sensor" | "mixed";

/** Palabras que sugieren "esto es una luz/foco" cuando solo tenemos
 *  on/off y no podemos distinguir entre foco e interruptor por capabilities. */
export const LIGHT_HINTS = /\b(foco|luz|lampar|bombill|light|lamp|spot|led)\w*/i;

export const DEVICE_KINDS: { id: DeviceKind; label: string; icon: IconName; hint: string }[] = [
  { id: "light", label: "Foco / luz", icon: "lightbulb", hint: "Encendido, regulable, RGB" },
  { id: "switch", label: "Interruptor", icon: "bolt", hint: "Solo on/off" },
  { id: "sensor", label: "Sensor", icon: "gauge", hint: "Lecturas numéricas" },
  { id: "mixed", label: "Mixto / avanzado", icon: "cpu", hint: "Combinación libre" },
];

export const SENSOR_PRESETS: {
  id: SensorKind;
  label: string;
  icon: IconName;
  backendId: string;
}[] = [
  { id: "temperature", label: "Temperatura", icon: "thermometer", backendId: "temperature" },
  { id: "humidity", label: "Humedad", icon: "droplet", backendId: "humidity" },
  { id: "pressure", label: "Presión", icon: "gauge", backendId: "pressure" },
  { id: "light", label: "Luminosidad", icon: "sun", backendId: "light" },
  { id: "motion", label: "Movimiento", icon: "motion", backendId: "motion" },
  { id: "co2", label: "Calidad aire", icon: "wind", backendId: "co2" },
  { id: "custom", label: "Personalizado", icon: "tag", backendId: "" },
];

export const TRANSPORT_KINDS: {
  id: TransportType;
  label: string;
  icon: IconName;
  hint: string;
}[] = [
  { id: "mqtt", label: "ESP32 (MQTT)", icon: "wifi", hint: "WiFi, broker MQTT" },
  { id: "serial", label: "Arduino (Serial)", icon: "bolt", hint: "USB, puerto COM" },
  {
    id: "custom",
    label: "Otro / existente",
    icon: "cpu",
    hint: "Transport ya definido en el backend",
  },
];

/* ── helpers ──────────────────────────────────────────────────────── */

export function slugify(s: string): string {
  return s
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 32);
}

export function kindFromDevice(d?: IoTDevice, cfg?: DeviceConfig): DeviceKind {
  // Si el usuario ya eligió un kind manualmente, respétalo siempre.
  if (cfg?.kind) return cfg.kind;
  if (!d) return "light";
  const c = d.capabilities;
  if (c.sensor) return "sensor";
  if (c.rgb || c.dimmable) return "light";
  if (c.on_off && !c.dimmable && !c.rgb) {
    // Heurística por nombre/id: "foco", "luz", "lampara"... → light
    const hint = `${d.name ?? ""} ${d.id ?? ""}`;
    return LIGHT_HINTS.test(hint) ? "light" : "switch";
  }
  return "mixed";
}

export function isObj(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}
