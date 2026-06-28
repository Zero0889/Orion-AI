/**
 * Store global de Orion (Zustand) — solo UI-state y WS-state.
 *
 * Concentra el estado que la UI necesita renderizar a partir de los
 * eventos del bus:
 *   - state:        "ESCUCHANDO" | "PENSANDO" | "HABLANDO"
 *   - muted:        bool
 *   - connected:    conexión WS activa
 *   - messages:     historial reciente del chat (cap defensivo)
 *   - currentFile:  archivo adjunto activo
 *   - unreadNotifs: contador para la campana
 *   - telemetry:    sparklines CPU/RAM/disk
 *   - iotSensors:   snapshots live de sensores (WS)
 *
 * El despachador `applyEvent` traduce cada evento del bus a una mutación
 * del store. Además, **funciona como bridge a TanStack Query**: cada
 * `case` que afecta server-state cacheado (notes, memory, conversations,
 * iot, orchestra, notifications, settings.theme) llama
 * `queryClient.invalidateQueries(...)` con la queryKey correspondiente,
 * y los paneles que usan `useQuery` refetchean automáticamente.
 *
 * Antes de la migración a TanStack Query había un objeto `rev` con
 * contadores por dominio que los paneles observaban como tripwire para
 * sus `useEffect` de fetch. Se borró cuando todos los paneles pasaron a
 * useQuery — la invalidación ahora es declarativa en una sola línea.
 */

import { create } from "zustand";

import { queryClient } from "@/query/client";
import { QUERY_KEYS } from "@/query/keys";
import { useAskUserStore } from "@/stores/askUser";
import { useInteractionStore } from "@/stores/interaction";
import type { ChatMessage, LogRole, OrionState, ServerEvent } from "@/types";

const MAX_MESSAGES = 300;

// Throttle por dispositivo para `iot.sensor` (ver case del switch).
// 250 ms = máx ~4 Hz por device — suficiente para sparklines fluidos
// sin que ESP32 con loops rápidos saturen el render tree.
const SENSOR_THROTTLE_MS = 250;
const _sensorThrottle = new Map<string, number>();

interface State {
  // Estado expuesto a los componentes
  state: OrionState;
  muted: boolean;
  connected: boolean;
  messages: ChatMessage[];
  currentFile: string | null;

  /** Conteo de notificaciones no leídas (Gmail + Classroom + …). Se
   *  actualiza por evento `notification.new`/`notification.read` y al
   *  hacer GET inicial al panel. */
  unreadNotifs: number;

  // Telemetría: últimos puntos para sparklines (CPU/RAM/disk en 0..1).
  telemetry: {
    cpu: number[];
    ram: number[];
    disk: number[];
    last: { cpu: number; ram: number; disk: number; ts: number } | null;
  };

  // Sensores IoT (snapshot del último valor recibido por WS).
  iotSensors: Record<string, { value: string; ts: number }>;

  // Estado del wizard de API key.
  apiKeyConfigured: boolean;

  // Acciones
  applyEvent: (evt: ServerEvent) => void;
  setConnected: (v: boolean) => void;
  setMuted: (v: boolean) => void;
  setApiKeyConfigured: (v: boolean) => void;
  pushLocalUserText: (text: string) => void;
  clear: () => void;
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
    return { role: "ai", body: t.split(":").slice(1).join(":").trim() };
  }
  if (tl.startsWith("sistema:") || tl.startsWith("sys:")) {
    return { role: "sys", body: t.split(":").slice(1).join(":").trim() };
  }
  if (tl.startsWith("error")) {
    return { role: "err", body: t };
  }
  if (tl.startsWith("archivo:")) {
    return { role: "file", body: t.split(":").slice(1).join(":").trim() };
  }
  return { role: "sys", body: t };
}

// IDs únicos para mensajes — crypto.randomUUID es nativo en todos los
// browsers modernos. Fallback determinístico (timestamp + counter) por si
// el contexto no es secure (Tauri webview con esquema custom, por ej.).
let _counter = 0;
const nextId = (): string => {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `m${Date.now().toString(36)}-${++_counter}`;
};

export const useOrionStore = create<State>((set, get) => ({
  state: "ESCUCHANDO",
  muted: false,
  connected: false,
  messages: [],
  currentFile: null,
  unreadNotifs: 0,
  telemetry: { cpu: [], ram: [], disk: [], last: null },
  iotSensors: {},
  apiKeyConfigured: true, // se inicializa con GET /api/settings/api_key

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

        // Deduplicación con streaming: busca el último mensaje del MISMO
        // role que vino de chat.stream (tiene turnId) y que aún no fue
        // confirmado por un `log` previo (`confirmedByLog` falso).
        //
        // Bug anterior: solo se chequeaba el último mensaje. En un turno
        // típico el orden es:
        //    chat.stream user → chat.stream orion → log user → log orion
        // Cuando llegaba `log user`, el último mensaje era orion → no
        // matcheaba → se pusheaba duplicado. Ídem para orion. Resultado:
        // cada turno aparecía dos veces.
        //
        // Hoy el backend usa `persist_log_only` para turnos streameados,
        // así que este path solo dispara para logs que NO vinieron de
        // streaming (errores, mensajes de sistema, "ORION en línea", etc).
        // Igual mantenemos el dedup como defense-in-depth.
        const existing = [...get().messages];
        let matchedIdx = -1;
        for (let i = existing.length - 1; i >= 0; i--) {
          const m = existing[i];
          if (m.role === role && m.turnId && !m.confirmedByLog) {
            matchedIdx = i;
            break;
          }
        }
        if (matchedIdx >= 0) {
          const arr = [...existing];
          arr[matchedIdx] = {
            ...arr[matchedIdx],
            text: body,
            streaming: false,
            confirmedByLog: true,
          };
          set({ messages: arr });
          break;
        }

        // Dedup de mensajes repetidos: si el último mensaje del mismo rol
        // tiene EXACTAMENTE el mismo texto, no lo duplicamos.  Esto evita
        // que errores de modelo en bucle inunden el timeline.
        if (existing.length > 0) {
          const last = existing[existing.length - 1];
          if (last.role === role && last.text === body) {
            break;
          }
        }

        const msg: ChatMessage = { id: nextId(), role, text: body, ts };
        const msgs = [...existing, msg];
        if (msgs.length > MAX_MESSAGES) msgs.splice(0, msgs.length - MAX_MESSAGES);
        set({ messages: msgs });
        break;
      }
      case "chat.stream": {
        // Streaming palabra-por-palabra desde Gemini Live. El backend manda
        // chunks parciales con un turn_id estable; acá los anexamos al
        // mensaje correspondiente para que el texto aparezca en sync con
        // la voz que está sonando.
        const rawRole = String(payload?.role ?? "");
        const role: LogRole = rawRole === "user" ? "user" : "ai";
        const turnId = String(payload?.turn_id ?? "");
        const delta = String(payload?.delta ?? "");
        const final = Boolean(payload?.final);
        if (!turnId) break;

        const ts = Number(payload?.ts ?? Date.now() / 1000);
        const msgs = [...get().messages];
        const idx = msgs.findIndex((m) => m.turnId === turnId);

        if (idx >= 0) {
          const prev = msgs[idx];
          const nextText = delta ? prev.text + (prev.text ? " " : "") + delta : prev.text;
          msgs[idx] = { ...prev, text: nextText, streaming: !final };
        } else if (delta) {
          msgs.push({
            id: nextId(),
            role,
            text: delta,
            ts,
            turnId,
            streaming: !final,
          });
          if (msgs.length > MAX_MESSAGES) msgs.splice(0, msgs.length - MAX_MESSAGES);
        }
        set({ messages: msgs });
        break;
      }
      case "file.attached": {
        const path = (payload?.path as string) ?? null;
        set({ currentFile: path });
        break;
      }
      case "file.cleared": {
        set({ currentFile: null });
        break;
      }
      case "note.changed":
      case "note.created":
      case "note.updated":
      case "note.deleted": {
        // Bridge WS → TanStack Query. Cada `case` invalida la queryKey
        // que cubre ese dominio; los paneles que usan useQuery refetchean
        // automáticamente. Los contadores `rev.X` se quitaron tras
        // migrar todos los consumidores a useQuery (Fase 4).
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notes });
        break;
      }
      case "memory.updated":
      case "memory.deleted": {
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.memory });
        break;
      }
      case "access.event":
      case "access.user_changed": {
        // Prefix-match: ["access"] invalida también ["access","events",...]
        // y ["access","daily",...]. Los 2 tabs del panel se refrescan
        // automáticamente cuando llega un nuevo evento del ESP32.
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.access.all });
        break;
      }
      case "conversation.deleted":
      case "conversation.load": {
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.conversations });
        break;
      }
      case "settings.theme": {
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.settingsTheme });
        break;
      }
      case "settings.brain":
      case "settings.brain.provider_key": {
        // Cambio de cerebro o key de provider — refrescamos el estado
        // completo para que la sección Cerebro re-renderee con badges
        // actualizados (available / configured / is_live).
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.settingsBrain });
        break;
      }
      case "agent.task": {
        const id = String(payload?.id ?? "");
        const status = String(payload?.status ?? "") as
          | "pending"
          | "running"
          | "completed"
          | "cancelled";
        const goal = String(payload?.goal ?? "");
        if (id && status) {
          useInteractionStore.getState().upsertAgentTask(id, status, goal);
        }
        break;
      }
      case "agent.speech": {
        const taskId = payload?.task_id == null ? null : String(payload.task_id);
        const text = String(payload?.text ?? "");
        if (text) useInteractionStore.getState().setAgentSpeech(taskId, text);
        break;
      }
      case "tool.call.start": {
        const name = String(payload?.name ?? "");
        const args = (payload?.args ?? {}) as Record<string, string>;
        if (name) useInteractionStore.getState().setActiveTool(name, args);
        break;
      }
      case "tool.call.end": {
        useInteractionStore.getState().clearActiveTool();
        break;
      }
      case "ask_user.start": {
        // Un agente está pidiendo una clarificación con menú. Lo
        // empujamos al askUser store; el componente AskUserPrompt
        // (montado en ChatPanel) lo renderiza arriba del composer.
        const qid = String(payload?.question_id ?? "");
        const q = String(payload?.question ?? "");
        const opts = (payload?.options ?? []) as Array<{ label?: unknown; description?: unknown }>;
        const allowO = Boolean(payload?.allow_other ?? true);
        if (!qid || !q || !Array.isArray(opts)) break;
        const cleanOpts = opts
          .map((o) => ({
            label: String((o as { label?: unknown }).label ?? "").trim(),
            description:
              String((o as { description?: unknown }).description ?? "").trim() || undefined,
          }))
          .filter((o) => o.label);
        if (cleanOpts.length === 0) break;
        useAskUserStore.getState().setPending({
          questionId: qid,
          question: q,
          options: cleanOpts,
          allowOther: allowO,
          receivedAt: Date.now(),
        });
        break;
      }
      case "orchestra.update": {
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.orchestra });
        break;
      }
      case "iot.action": {
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.iot.all });
        break;
      }
      case "notification.new": {
        const count = Number(payload?.count ?? 0);
        set((s) => ({
          unreadNotifs: s.unreadNotifs + (count > 0 ? count : 0),
        }));
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notifications });
        break;
      }
      case "notification.read": {
        // El backend ya marcó como leídas en el store; el panel hará
        // refetch via invalidateQueries. Acá sólo bajamos el contador
        // para que la campana se actualice instantánea.
        const c = Number(payload?.count ?? 0);
        set((s) => ({
          unreadNotifs: Math.max(0, s.unreadNotifs - c),
        }));
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notifications });
        break;
      }
      case "iot.sensor": {
        const device = String(payload?.device ?? "");
        const value = String(payload?.value ?? "");
        if (!device) break;
        // Throttle defensivo: si un ESP32 reporta a >4 Hz, cada write
        // cascadea por HomePanel, IoTPanel y useEventPulses. 250ms por
        // device sigue siendo más rápido que el ojo humano para sparklines
        // y el DeviceCard, pero acota el costo en escenarios de stress.
        const now = Date.now();
        const last = _sensorThrottle.get(device) ?? 0;
        if (now - last < SENSOR_THROTTLE_MS) break;
        _sensorThrottle.set(device, now);
        set((s) => ({
          iotSensors: { ...s.iotSensors, [device]: { value, ts: now / 1000 } },
        }));
        break;
      }
      case "audio.chunk": {
        // Stream de audio remoto: el backend manda PCM 16-bit mono base64
        // por cada chunk de Gemini Live. En el desktop la PC ya lo
        // reproduce por sounddevice, así que no lo tocamos (sonaría
        // doble). En móvil/tablet/watch es el único camino para oír a
        // Orion — vía Web Audio API.
        if (typeof window === "undefined") break;
        // detectDevice() no se importa estáticamente para no inflar el
        // bundle inicial con la lógica de audio cuando el usuario nunca
        // habla con voz.
        import("@/api/ws").then(({ detectDevice }) => {
          const device = detectDevice();
          if (device === "desktop") return; // PC: el sounddevice local manda.
          const b64 = String(payload?.pcm_b64 ?? "");
          const sr = Number(payload?.sr ?? 24000);
          if (!b64) return;
          import("@/audio/audioPlayer").then((m) => m.playPcmChunk(b64, sr));
        });
        break;
      }
      case "audio.end": {
        // El backend cerró el turno de audio. Por ahora no-op (los
        // chunks pendientes están agendados y se drenan solos).
        if (typeof window === "undefined") break;
        import("@/audio/audioPlayer").then((m) => m.markAudioTurnEnd());
        break;
      }
      case "telemetry": {
        const cpu = Number(payload?.cpu ?? 0);
        const ram = Number(payload?.ram ?? 0);
        const disk = Number(payload?.disk ?? 0);
        const ts = Number(payload?.ts ?? Date.now() / 1000);
        const MAX = 60;
        set((s) => ({
          telemetry: {
            cpu: appendCapped(s.telemetry.cpu, cpu, MAX),
            ram: appendCapped(s.telemetry.ram, ram, MAX),
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

  setConnected(v) {
    set({ connected: v });
  },
  setMuted(v) {
    set({ muted: v });
  },
  setApiKeyConfigured(v: boolean) {
    set({ apiKeyConfigured: v });
  },

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
