/**
 * useSensorHistory — capped numeric series for a single IoT sensor.
 *
 * The backend pushes `iot.sensor` events to the bus; the store keeps
 * only the *last* value per device. This hook subscribes to that slice
 * and locally accumulates the last `capacity` numeric readings so the
 * panel can render an inline sparkline that mirrors how Telemetry draws
 * its area chart.
 */

import { useEffect, useRef, useState } from "react";

import { useOrionStore } from "@/stores/orion";

export interface SensorPoint {
  value: number;
  ts: number;
}

/**
 * Parse the first numeric run from a string value ("23.4 °C" -> 23.4).
 * Returns null when no number can be extracted.
 */
function parseNumeric(raw: string | undefined): number | null {
  if (raw === undefined || raw === null) return null;
  const m = String(raw).match(/-?\d+(\.\d+)?/);
  if (!m) return null;
  const n = parseFloat(m[0]);
  return Number.isFinite(n) ? n : null;
}

export function useSensorHistory(deviceId: string, capacity = 40): SensorPoint[] {
  const sample = useOrionStore((s) => s.iotSensors[deviceId]);
  const [series, setSeries] = useState<SensorPoint[]>([]);
  const lastTs = useRef<number | null>(null);

  useEffect(() => {
    if (!sample) return;
    if (sample.ts === lastTs.current) return;
    lastTs.current = sample.ts;
    const num = parseNumeric(sample.value);
    if (num === null) return;
    setSeries((prev) => {
      const next = [...prev, { value: num, ts: sample.ts }];
      return next.length > capacity ? next.slice(next.length - capacity) : next;
    });
  }, [sample, capacity]);

  return series;
}
