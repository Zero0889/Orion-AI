/**
 * Store global de Orion (Zustand).
 *
 * Concentra el estado que la UI necesita renderizar a partir de los
 * eventos del bus:
 *   - state:      "ESCUCHANDO" | "PENSANDO" | "HABLANDO"
 *   - muted:      bool
 *   - connected:  conexión WS activa
 *   - messages:   historial reciente (cap defensivo)
 *
 * El despachador ``applyEvent`` traduce cada evento del bus a una
 * mutación del store. Diseñado para ser invocado desde el WS handler.
 */

import { create } from "zustand";

import type {
  ChatMessage, LogRole, OrionState, ServerEvent,
} from "@/types";

const MAX_MESSAGES = 300;

interface State {
  // Estado expuesto a los componentes
  state:     OrionState;
  muted:     boolean;
  connected: boolean;
  messages:  ChatMessage[];
  currentFile: string | null;

  // Acciones
  applyEvent:  (evt: ServerEvent) => void;
  setConnected: (v: boolean) => void;
  setMuted:    (v: boolean) => void;
  pushLocalUserText: (text: string) => void;
  clear:        () => void;
}

function parseLogRole(text: string): { role: LogRole; body: string } {
  const t = text.trim();
  const tl = t.toLowerCase();
  if (tl.startsWith("tú:") || tl.startsWith("tu:")) {
    return { role: "user", body: t.split(":").slice(1).join(":").trim() };
  }
  if (tl.startsWith("orion:") || tl.startsWith("o.r.i.o.n:")) {
    return { role: "ai",   body: t.split(":").slice(1).join(":").trim() };
  }
  if (tl.startsWith("sistema:") || tl.startsWith("sys:")) {
    return { role: "sys",  body: t.split(":").slice(1).join(":").trim() };
  }
  if (tl.startsWith("error")) {
    return { role: "err",  body: t };
  }
  if (tl.startsWith("archivo:")) {
    return { role: "file", body: t.split(":").slice(1).join(":").trim() };
  }
  return { role: "sys", body: t };
}

let _id = 0;
const nextId = () => `m${++_id}`;

export const useOrionStore = create<State>((set, get) => ({
  state:        "ESCUCHANDO",
  muted:        false,
  connected:    false,
  messages:     [],
  currentFile:  null,

  applyEvent(evt) {
    const { type, payload } = evt;
    switch (type) {
      case "state": {
        const value = (payload?.value as OrionState) ?? "ESCUCHANDO";
        set({ state: value });
        break;
      }
      case "mute": {
        set({ muted: Boolean(payload?.value) });
        break;
      }
      case "log": {
        const text = String(payload?.text ?? "").trim();
        if (!text) break;
        const { role, body } = parseLogRole(text);
        if (!body) break;
        const ts = Number(payload?.ts ?? Date.now() / 1000);
        const msg: ChatMessage = { id: nextId(), role, text: body, ts };
        const msgs = [...get().messages, msg];
        if (msgs.length > MAX_MESSAGES) msgs.splice(0, msgs.length - MAX_MESSAGES);
        set({ messages: msgs });
        break;
      }
      case "file.attached": {
        const path = (payload?.path as string) ?? null;
        set({ currentFile: path });
        break;
      }
      default:
        // Otros eventos (telemetry, iot.sensor, etc.) se manejarán en
        // siguientes fases cuando lleguen sus paneles.
        break;
    }
  },

  setConnected(v) { set({ connected: v }); },
  setMuted(v)    { set({ muted: v }); },

  pushLocalUserText(text) {
    const t = text.trim();
    if (!t) return;
    const msg: ChatMessage = {
      id: nextId(),
      role: "user",
      text: t,
      ts: Date.now() / 1000,
    };
    set({ messages: [...get().messages, msg] });
  },

  clear() {
    set({ messages: [] });
  },
}));
