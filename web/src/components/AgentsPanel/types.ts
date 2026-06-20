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
