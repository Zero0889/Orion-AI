/**
 * sensorPersonality — mapea el `capabilities.sensor` de un dispositivo
 * a un set de tokens visuales (icono, color de acento, unidad, rango).
 *
 * El objetivo es que cada tipo de sensor se "sienta" distinto en el
 * dashboard sin tocar la lógica de fetch/renderizado: la card pide la
 * personalidad y la aplica al borde, icono y readout.
 *
 * Las claves `kind` aceptadas vienen del backend tal como las definimos
 * en `iot_config.json` (`temperature`, `humidity`, `light`, `geo`, …).
 * Si llega una desconocida, devuelve el preset `default` — neutro.
 */

import type { IconName } from "@/ui/Icon";

export type SensorKind = "temperature" | "humidity" | "light" | "geo" | "count" | "default";

export interface SensorPersonality {
  /** Etiqueta humana, mostrada en chips y headers. */
  label: string;
  /** Icono Lucide-like del set local. */
  icon: IconName;
  /** Color de acento en CSS (hex). Usado en barra lateral, icono y unidad. */
  color: string;
  /** Sufijo de unidad (con el espacio incluido si corresponde). */
  unit: string;
  /** Rango esperado [min, max] para visualizaciones tipo "fill bar". */
  range?: [number, number];
  /** Cuántos decimales mostrar al renderizar el valor. */
  decimals: number;
  /** Hint corto para el footer de la card. */
  hint?: string;
}

const PRESETS: Record<SensorKind, SensorPersonality> = {
  temperature: {
    label: "Temperatura",
    icon: "thermometer",
    color: "#FF7A5C",
    unit: " °C",
    range: [0, 40],
    decimals: 1,
    hint: "ambiente",
  },
  humidity: {
    label: "Humedad",
    icon: "droplet",
    color: "#5BCBF5",
    unit: " %",
    range: [0, 100],
    decimals: 0,
    hint: "relativa",
  },
  light: {
    label: "Luz",
    icon: "sun",
    color: "#F5C04F",
    unit: " lx",
    range: [0, 1000],
    decimals: 0,
    hint: "lux",
  },
  geo: {
    label: "Posición",
    icon: "compass",
    color: "#A78BFA",
    unit: "",
    decimals: 4,
    hint: "GPS",
  },
  count: {
    label: "Cuenta",
    icon: "sigma",
    color: "#7EE7FF",
    unit: "",
    decimals: 0,
  },
  default: {
    label: "Sensor",
    icon: "sensors",
    color: "#7EE7FF",
    unit: "",
    decimals: 1,
  },
};

export function getSensorPersonality(raw: string | null | undefined): SensorPersonality {
  const key = (raw ?? "").toLowerCase().trim();
  if (key in PRESETS) return PRESETS[key as SensorKind];
  return PRESETS.default;
}

/** Formatea un valor crudo string a "26.3 °C" según la personalidad. */
export function formatSensorValue(raw: string | undefined, p: SensorPersonality): string {
  if (raw == null || raw === "") return "—";
  const n = Number(raw);
  if (Number.isNaN(n)) return raw;
  return `${n.toFixed(p.decimals)}${p.unit}`;
}

/** Devuelve un 0..1 indicando dónde cae el valor dentro de `range`.
 *  Clamped. Útil para barras tipo termostato. */
export function rangePercent(raw: string | undefined, p: SensorPersonality): number | null {
  if (!p.range) return null;
  const n = Number(raw);
  if (Number.isNaN(n)) return null;
  const [lo, hi] = p.range;
  const span = Math.max(hi - lo, 0.001);
  return Math.max(0, Math.min(1, (n - lo) / span));
}
