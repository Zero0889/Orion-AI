/**
 * Tipos + helpers compartidos entre los componentes del AgentsPanel.
 */

import type { IconName } from "@/ui/Icon";

/* ─── Chat types ───────────────────────────────────────────────────── */

export interface ChatMsg {
  role: "user" | "agent";
  text: string;
  ts: number;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMsg[];
  createdAt: number;
}

/** All sessions across all agents: agentId → sessions[] */
export type AgentSessions = Record<string, ChatSession[]>;

/* ─── Icon tones ───────────────────────────────────────────────────── */

const ICON_TONES: Record<string, string> = {
  compass: "text-amber-400",
  search: "text-sky-400",
  code: "text-emerald-400",
  sigma: "text-violet-400",
  feather: "text-rose-400",
  chart: "text-orange-400",
  folder: "text-cyan-400",
  sensors: "text-lime-400",
  sparkles: "text-pink-400",
  orbit: "text-pri",
  cpu: "text-blue-400",
  memory: "text-fuchsia-400",
  chat: "text-teal-400",
  bolt: "text-yellow-400",
};

export function agentIconTone(icon: string): string {
  return ICON_TONES[icon as IconName] ?? "text-pri";
}

/* ─── Agent identity color (BRIEF · Agentes) ──────────────────────── */

/**
 * Mapea un agente a su token de identidad (`--agent-*`). Cada rol
 * autónomo conserva su hue para leerse de un vistazo en la grilla y
 * en notificaciones cross-panel.
 *
 * Resolución (en orden):
 *   1. Match por `role`/`id` semántico (researcher, coder, writer, analyst).
 *   2. Match por icono (compass/search → researcher, cpu/code → coder, ...).
 *   3. Fallback al primary del tema.
 *
 * Devuelve el NOMBRE del token CSS (`--agent-researcher`, etc.) — los
 * consumidores componen alpha con `rgb(var(...) / 0.X)`.
 */
const ROLE_IDENTITY: Record<string, string> = {
  researcher: "--agent-researcher",
  investigador: "--agent-researcher",
  research: "--agent-researcher",
  coder: "--agent-coder",
  programador: "--agent-coder",
  developer: "--agent-coder",
  dev: "--agent-coder",
  writer: "--agent-writer",
  redactor: "--agent-writer",
  scribe: "--agent-writer",
  analyst: "--agent-analyst",
  analista: "--agent-analyst",
  data: "--agent-analyst",
};

const ICON_IDENTITY: Record<string, string> = {
  compass: "--agent-researcher",
  search: "--agent-researcher",
  cpu: "--agent-coder",
  code: "--agent-coder",
  feather: "--agent-writer",
  chart: "--agent-analyst",
  sigma: "--agent-analyst",
};

export function agentIdentityVar(role: string, icon?: string): string {
  const key = role.toLowerCase().trim();
  if (key in ROLE_IDENTITY) return ROLE_IDENTITY[key];
  if (icon && icon in ICON_IDENTITY) return ICON_IDENTITY[icon];
  return "--agent-default";
}

/* ─── Provider label ───────────────────────────────────────────────── */

const PROVIDER_LABELS: Record<string, string> = {
  gemini: "Gemini",
  openrouter: "OpenRouter",
  groq: "Groq",
  openai: "OpenAI",
  mistral: "Mistral",
  anthropic: "Claude",
  ollama: "Ollama",
  ollama_cloud: "Ollama Cloud",
  deepseek: "DeepSeek",
};

export function useProviderLabel(provider: string): string {
  return PROVIDER_LABELS[provider] ?? provider;
}

/* ─── Role translation (BRIEF G4) ──────────────────────────────────── */

/**
 * El backend devuelve `role` con mezcla EN/ES (RESEARCHER, CODER, etc).
 * BRIEF G4 obliga UI 100% en español: este mapa pasa cada rol conocido
 * a su versión castellana, dejando intacto cualquier rol custom (los
 * agentes definidos por el usuario ya son arbitrarios).
 */
const ROLE_LABELS: Record<string, string> = {
  researcher: "Investigador",
  research: "Investigador",
  coder: "Programador",
  developer: "Programador",
  writer: "Redactor",
  scribe: "Redactor",
  analyst: "Analista",
  data: "Analista",
  assistant: "Asistente",
  planner: "Planificador",
  reviewer: "Revisor",
  translator: "Traductor",
};

export function translateRole(role: string): string {
  const key = role.toLowerCase().trim();
  if (key in ROLE_LABELS) return ROLE_LABELS[key];
  // Si el rol original ya tiene capitalización propia (custom), respetarla.
  if (/^[A-Z]/.test(role)) return role;
  // Si vino en MAYÚSCULAS o snake_case, normalizar a Capitalizado.
  return role
    .replace(/[_-]+/g, " ")
    .toLowerCase()
    .replace(/^\w/, (c) => c.toUpperCase());
}

/* ─── Model label compactor (BRIEF · Agentes) ──────────────────────── */

/**
 * "gemini-2.5-flash" → "Flash 2.5"
 * "gemini-1.5-pro"   → "Pro 1.5"
 * "deepseek-chat"    → "Chat"
 * "claude-opus-4-8"  → "Opus 4.8"
 *
 * Si la familia no es conocida cae al tail del nombre.
 */
export function compactModelLabel(model: string): string {
  if (!model) return "—";
  const m = model.toLowerCase();
  // gemini-X.Y-(flash|pro)
  const gemini = m.match(/gemini[-_]?(\d+(?:\.\d+)?)[-_]?(flash|pro|nano)/);
  if (gemini) return `${capitalize(gemini[2])} ${gemini[1]}`;
  // claude-(sonnet|opus|haiku|fable)-X-Y
  const claude = m.match(/claude[-_]?(opus|sonnet|haiku|fable)[-_]?(\d+)[-_]?(\d+)?/);
  if (claude) {
    const version = claude[3] ? `${claude[2]}.${claude[3]}` : claude[2];
    return `${capitalize(claude[1])} ${version}`;
  }
  // deepseek-(chat|coder|reasoner)
  const deepseek = m.match(/deepseek[-_]?(\w+)/);
  if (deepseek) return capitalize(deepseek[1]);
  // mistral-(large|small|nemo)-XYZ
  const mistral = m.match(/mistral[-_]?(large|small|medium|nemo|codestral)/);
  if (mistral) return capitalize(mistral[1]);
  // Último recurso: último segmento legible.
  const tail = model.split(/[-_/]/u).filter(Boolean).pop() ?? model;
  return capitalize(tail);
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/* ─── Session persistence (localStorage) ──────────────────────────── */

const SESSIONS_KEY = "orion.agent.sessions";

export function createSession(title: string): ChatSession {
  return {
    id: `s_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    title,
    messages: [],
    createdAt: Date.now(),
  };
}

export function loadSessions(): AgentSessions {
  try {
    const raw = window.localStorage.getItem(SESSIONS_KEY);
    if (!raw) return {};
    return JSON.parse(raw) as AgentSessions;
  } catch {
    return {};
  }
}

export function saveSessions(data: AgentSessions) {
  try {
    const clean: AgentSessions = {};
    for (const [agentId, sessList] of Object.entries(data)) {
      if (sessList.length === 0) continue;
      clean[agentId] = sessList.map((s) => ({
        ...s,
        messages: s.messages.slice(-80), // keep last 80 msgs per session
      }));
    }
    window.localStorage.setItem(SESSIONS_KEY, JSON.stringify(clean));
  } catch {
    // silently ignore
  }
}
