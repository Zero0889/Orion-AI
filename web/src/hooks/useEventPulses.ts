/**
 * useEventPulses — bisagra entre el mundo (sensores, notifs, herramientas)
 * y el `eyePulseStore`. Vive una sola vez en App.tsx.
 *
 * Filtra para que el Eye sólo pulse cuando hay algo que valga la pena
 * mirar. La regla central: pulso ≠ tick. Una lectura rutinaria del DHT
 * no es un evento — un cambio brusco sí lo es.
 *
 * Disparadores actuales:
 *   - iot.sensor primera vez: pulso cian (ESP32 reportó por primera vez).
 *   - iot.sensor cambio significativo: pulso cian (>10% relativo y >1 abs).
 *   - iot.sensor stale (>60s sin reportar): pulso rojo (una sola vez).
 *   - notification.new: pulso violeta por cada incremento del contador.
 *   - tool.call.start / .end: pulso magenta al empezar y al terminar.
 */

import { useEffect, useRef } from "react";

import { useEyePulseStore } from "@/stores/eyePulse";
import { useInteractionStore } from "@/stores/interaction";
import { useOrionStore } from "@/stores/orion";

const STALE_AFTER_S      = 60;
const STALE_CHECK_MS     = 10_000;
const REL_DELTA_THRESHOLD = 0.10;
const ABS_DELTA_THRESHOLD = 1;

export function useEventPulses() {
  const pulse        = useEyePulseStore((s) => s.pulse);
  const iotSensors   = useOrionStore((s) => s.iotSensors);
  const unreadNotifs = useOrionStore((s) => s.unreadNotifs);
  const activeTool   = useInteractionStore((s) => s.tool);

  const seenSensors   = useRef<Set<string>>(new Set());
  const lastValueOf   = useRef<Record<string, number>>({});
  const lastTsOf      = useRef<Record<string, number>>({});
  const staleNotified = useRef<Set<string>>(new Set());
  const prevUnread    = useRef(unreadNotifs);
  const prevToolName  = useRef<string | null>(null);

  // ── Sensores: primera lectura + cambios significativos ────────────
  useEffect(() => {
    Object.entries(iotSensors).forEach(([id, { value, ts }]) => {
      lastTsOf.current[id] = ts;
      staleNotified.current.delete(id);  // llegó dato fresco, reset

      const num = Number(value);
      if (!seenSensors.current.has(id)) {
        seenSensors.current.add(id);
        pulse("sensor");
        if (!Number.isNaN(num)) lastValueOf.current[id] = num;
        return;
      }

      const prev = lastValueOf.current[id];
      if (!Number.isNaN(num) && prev !== undefined) {
        const absDelta = Math.abs(num - prev);
        const relDelta = Math.abs(absDelta / (Math.abs(prev) || 1));
        if (absDelta > ABS_DELTA_THRESHOLD && relDelta > REL_DELTA_THRESHOLD) {
          pulse("sensor");
        }
      }
      if (!Number.isNaN(num)) lastValueOf.current[id] = num;
    });
  }, [iotSensors, pulse]);

  // ── Watchdog de stale: cada 10s revisa si alguno se cayó ──────────
  useEffect(() => {
    const tid = window.setInterval(() => {
      const now = Date.now() / 1000;
      Object.entries(lastTsOf.current).forEach(([id, ts]) => {
        if (now - ts > STALE_AFTER_S && !staleNotified.current.has(id)) {
          staleNotified.current.add(id);
          pulse("error");
        }
      });
    }, STALE_CHECK_MS);
    return () => window.clearInterval(tid);
  }, [pulse]);

  // ── Notificaciones nuevas ─────────────────────────────────────────
  useEffect(() => {
    if (unreadNotifs > prevUnread.current) pulse("notif");
    prevUnread.current = unreadNotifs;
  }, [unreadNotifs, pulse]);

  // ── Tools: pulso al iniciar y al terminar ─────────────────────────
  useEffect(() => {
    const before = prevToolName.current;
    const after  = activeTool?.name ?? null;
    if (before !== after) {
      if (before === null && after !== null) pulse("tool");
      else if (before !== null && after === null) pulse("tool");
      else if (before !== null && after !== null) pulse("tool");
    }
    prevToolName.current = after;
  }, [activeTool, pulse]);
}
