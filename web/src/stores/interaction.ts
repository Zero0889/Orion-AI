/**
 * Store de actividad en curso del backend.
 *
 * Trackea qué está haciendo Orion AHORA MISMO a nivel granular:
 *   - tool call activa (web_search, file_controller, ...)
 *   - tarea de agente background (registry-based: researcher, coder, ...)
 *
 * Lo consume:
 *   - <OrbHUD> para entrar en mode="tool" o mode="agent" automáticamente.
 *   - <ToolBanner> que aparece arriba del chat con la tool activa.
 *
 * Eventos del bus que lo alimentan (ver server/event_bus.py):
 *   - "tool.call.start"  → setActiveTool({...})
 *   - "tool.call.end"    → clearActiveTool()
 *   - "agent.task"       → trackeo de tarea (pending/running/completed)
 *   - "agent.speech"     → último mensaje del agente activo
 *
 * Diseño defensivo: el `start` no llega siempre acompañado de su `end`
 * (timeouts, crashes). Por eso guardamos `startedAt` y autoexpiramos a
 * los 90s — el banner desaparece solo en lugar de quedarse pegado.
 */

import { create } from "zustand";

const AUTO_CLEAR_MS = 90_000;

interface ActiveTool {
  name:      string;
  args:      Record<string, string>;
  startedAt: number;
}

interface ActiveAgent {
  taskId:    string | null;
  status:    "pending" | "running" | "completed" | "cancelled";
  goal:      string;
  lastSpeech: string | null;
  updatedAt: number;
}

interface State {
  tool:  ActiveTool  | null;
  agent: ActiveAgent | null;

  setActiveTool:   (name: string, args: Record<string, string>) => void;
  clearActiveTool: () => void;

  upsertAgentTask: (taskId: string, status: ActiveAgent["status"], goal?: string) => void;
  setAgentSpeech:  (taskId: string | null, text: string) => void;
  clearAgent:      () => void;
}

let autoClearTimer: number | null = null;

export const useInteractionStore = create<State>((set, get) => ({
  tool:  null,
  agent: null,

  setActiveTool(name, args) {
    if (autoClearTimer !== null) window.clearTimeout(autoClearTimer);
    autoClearTimer = window.setTimeout(() => {
      // Failsafe: si el `end` nunca llegó, limpiamos solos.
      if (get().tool?.name === name) set({ tool: null });
    }, AUTO_CLEAR_MS);
    set({ tool: { name, args, startedAt: Date.now() } });
  },

  clearActiveTool() {
    if (autoClearTimer !== null) {
      window.clearTimeout(autoClearTimer);
      autoClearTimer = null;
    }
    set({ tool: null });
  },

  upsertAgentTask(taskId, status, goal = "") {
    const current = get().agent;
    if (status === "completed" || status === "cancelled") {
      // Al terminar, mantenemos brevemente el estado y luego limpiamos
      set({
        agent: {
          taskId,
          status,
          goal: current?.taskId === taskId ? current.goal : goal,
          lastSpeech: current?.taskId === taskId ? current.lastSpeech : null,
          updatedAt: Date.now(),
        },
      });
      window.setTimeout(() => {
        if (get().agent?.taskId === taskId) set({ agent: null });
      }, 4000);
      return;
    }
    set({
      agent: {
        taskId,
        status,
        goal: goal || current?.goal || "",
        lastSpeech: current?.taskId === taskId ? current.lastSpeech : null,
        updatedAt: Date.now(),
      },
    });
  },

  setAgentSpeech(taskId, text) {
    const current = get().agent;
    if (!current) return;
    // Solo guardamos si el speech viene del taskId activo (o sin taskId).
    if (taskId && current.taskId !== taskId) return;
    set({
      agent: { ...current, lastSpeech: text, updatedAt: Date.now() },
    });
  },

  clearAgent() {
    set({ agent: null });
  },
}));
