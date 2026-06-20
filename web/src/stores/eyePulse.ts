/**
 * eyePulse — cola de "pulsos" que el Eye dispara como feedback ambiental.
 *
 * No es un estado conversacional (eso vive en useEyeState). Acá viven
 * eventos puntuales del mundo: llegó una lectura nueva relevante de un
 * sensor, llegó una notificación, una herramienta arrancó o terminó,
 * un sensor cayó en stale, etc.
 *
 * El componente EyeCore lee `active` y renderiza un anillo radial por
 * cada pulso. Cada pulso se auto-limpia tras `DURATION_MS` para evitar
 * que la lista crezca sin parar.
 *
 * Reglas del juego para los productores (ver useEventPulses):
 *   - El `iot.sensor` NO pulsa por cada lectura — sólo en transiciones
 *     significativas (conectó, se cayó, cambio relevante de valor).
 *   - notif/tool/error siempre pulsan porque son raros.
 */

import { create } from "zustand";

export type PulseKind = "sensor" | "notif" | "tool" | "error";

interface Pulse {
  id: number;
  kind: PulseKind;
}

// 1700ms cubre los 3 anillos escalonados (último arranca a los 300ms
// y dura ~1200ms). Si bajamos esto se cortan visualmente.
const DURATION_MS = 1700;

interface State {
  active: Pulse[];
  pulse: (kind: PulseKind) => void;
}

let nextId = 1;

export const useEyePulseStore = create<State>((set) => ({
  active: [],
  pulse(kind) {
    const id = nextId++;
    set((s) => ({ active: [...s.active, { id, kind }] }));
    setTimeout(() => {
      set((s) => ({ active: s.active.filter((p) => p.id !== id) }));
    }, DURATION_MS);
  },
}));
