/**
 * Cliente REST mínimo. Resuelve la URL del backend igual que ws.ts
 * (Vite dev → :8765 ; prod → mismo origen).
 */

import { inferBackendUrl } from "@/api/ws";

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const { http } = inferBackendUrl();
  const res = await fetch(`${http}${path}`, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail: string;
    try { detail = (await res.json())?.detail ?? res.statusText; }
    catch { detail = res.statusText; }
    throw new Error(`${method} ${path} → ${res.status} ${detail}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  // Notes
  listNotes:    () => request<Array<NoteApi>>("GET", "/api/notes"),
  createNote:   (text: string, pinned = false) =>
    request<NoteApi>("POST", "/api/notes", { text, pinned }),
  updateNote:   (id: string, patch: Partial<{ text: string; pinned: boolean; color: string }>) =>
    request<{ ok: true; id: string }>("PATCH", `/api/notes/${id}`, patch),
  deleteNote:   (id: string) => request<void>("DELETE", `/api/notes/${id}`),

  // Memory
  getMemory:    () => request<MemoryShape>("GET", "/api/memory"),
  putMemory:    (category: string, key: string, value: string) =>
    request<{ ok: true }>("PUT", `/api/memory/${category}/${key}`, { value }),
  deleteMemory: (category: string, key: string) =>
    request<void>("DELETE", `/api/memory/${category}/${key}`),

  // Conversations
  listConversations: () =>
    request<Array<ConversationSummary>>("GET", "/api/conversations"),
  getConversation:   (id: string) =>
    request<ConversationDetail>("GET", `/api/conversations/${id}`),
  deleteConversation: (id: string) =>
    request<void>("DELETE", `/api/conversations/${id}`),

  // Settings
  getTheme:   () => request<ThemeInfo>("GET", "/api/settings/theme"),
  setTheme:   (name: string) =>
    request<{ ok: true; name: string; theme: Record<string, unknown> }>(
      "PATCH", "/api/settings/theme", { name },
    ),
};

// ── Types ──────────────────────────────────────────────────────────────
export interface NoteApi {
  id:      string;
  text:    string;
  pinned:  boolean;
  color?:  string;
  created: string;
  updated: string;
}

export interface MemoryEntry {
  value:   string;
  updated?: string;
}

export type MemoryCategory =
  | "identity" | "preferences" | "projects"
  | "relationships" | "wishes" | "notes";

export type MemoryShape = Record<MemoryCategory, Record<string, MemoryEntry>>;

export interface ConversationSummary {
  id:       string;
  started:  string;
  title:    string;
  messages: number;
}

export interface ConversationDetail {
  id:       string;
  started:  string;
  title:    string;
  messages: Array<{ role: string; text: string; ts: string }>;
}

export interface ThemeInfo {
  name:      string;
  theme:     Record<string, unknown>;
  available: Array<{ id: string; name: string }>;
}
