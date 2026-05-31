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

  // Contadores por tipo de evento — los paneles los observan para
  // refrescar sus datos cuando algo cambia en el backend.
  rev: {
    notes:    number;
    memory:   number;
    convs:    number;
    theme:    number;
    agent:    number;
    iot:      number;
  };

  // Telemetría: últimos puntos para sparklines (CPU/RAM/disk en 0..1).
  telemetry: {
    cpu:  number[];
    ram:  number[];
    disk: number[];
    last: { cpu: number; ram: number; disk: number; ts: number } | null;
  };

  // Sensores IoT (snapshot del último valor recibido por WS).
  iotSensors: Record<string, { value: string; ts: number }>;

  // Estado del wizard de API key.
  apiKeyConfigured: boolean;

  // Acciones
  applyEvent:  (evt: ServerEvent) => void;
  setConnected: (v: boolean) => void;
  setMuted:    (v: boolean) => void;
  setApiKeyConfigured: (v: boolean) => void;
  pushLocalUserText: (text: string) => void;
  clear:        () => void;
}

function appendCapped(arr: number[], v: number, max: number): number[] {
  const next = [...arr, v];
  if (next.length > max) next.splice(0, next.length - max);
  return next;
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
  rev: { notes: 0, memory: 0, convs: 0, theme: 0, agent: 0, iot: 0 },
  telemetry:    { cpu: [], ram: [], disk: [], last: null },
  iotSensors:   {},
  apiKeyConfigured: true,  // se inicializa con GET /api/settings/api_key

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
      case "note.changed":
      case "note.created":
      case "note.updated":
      case "note.deleted": {
        set((s) => ({ rev: { ...s.rev, notes: s.rev.notes + 1 } }));
        break;
      }
      case "memory.updated":
      case "memory.deleted": {
        set((s) => ({ rev: { ...s.rev, memory: s.rev.memory + 1 } }));
        break;
      }
      case "conversation.deleted":
      case "conversation.load": {
        set((s) => ({ rev: { ...s.rev, convs: s.rev.convs + 1 } }));
        break;
      }
      case "settings.theme": {
        set((s) => ({ rev: { ...s.rev, theme: s.rev.theme + 1 } }));
        break;
      }
      case "agent.task": {
        set((s) => ({ rev: { ...s.rev, agent: s.rev.agent + 1 } }));
        break;
      }
      case "iot.action": {
        set((s) => ({ rev: { ...s.rev, iot: s.rev.iot + 1 } }));
        break;
      }
      case "iot.sensor": {
        const device = String(payload?.device ?? "");
        const value  = String(payload?.value  ?? "");
        if (!device) break;
        set((s) => ({
          iotSensors: { ...s.iotSensors, [device]: { value, ts: Date.now() / 1000 } },
        }));
        break;
      }
      case "telemetry": {
        const cpu  = Number(payload?.cpu  ?? 0);
        const ram  = Number(payload?.ram  ?? 0);
        const disk = Number(payload?.disk ?? 0);
        const ts   = Number(payload?.ts   ?? Date.now() / 1000);
        const MAX = 60;
        set((s) => ({
          telemetry: {
            cpu:  appendCapped(s.telemetry.cpu,  cpu,  MAX),
            ram:  appendCapped(s.telemetry.ram,  ram,  MAX),
            disk: appendCapped(s.telemetry.disk, disk, MAX),
            last: { cpu, ram, disk, ts },
          },
        }));
        break;
      }
      case "system.ready": {
        set({ apiKeyConfigured: true });
        break;
      }
      default:
        break;
    }
  },

  setConnected(v) { set({ connected: v }); },
  setMuted(v)    { set({ muted: v }); },
  setApiKeyConfigured(v: boolean) { set({ apiKeyConfigured: v }); },

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
