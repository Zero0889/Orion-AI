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
  getApiKeyStatus: () => request<ApiKeyStatus>("GET", "/api/settings/api_key"),
  setApiKey:       (key: string) =>
    request<{ ok: true; configured: true }>("POST", "/api/settings/api_key", { key }),

  // Agent / TaskQueue
  listTasks:   () => request<Array<AgentTask>>("GET", "/api/agent/tasks"),
  submitTask:  (goal: string, priority: "low" | "normal" | "high" = "normal") =>
    request<{ task_id: string; status: string; goal: string }>(
      "POST", "/api/agent/tasks", { goal, priority },
    ),
  cancelTask:  (id: string) =>
    request<{ ok: true; id: string; status: string }>(
      "POST", `/api/agent/tasks/${id}/cancel`,
    ),

  // Files / drop-zone
  uploadFile: async (file: File): Promise<FileUploadResult> => {
    const { http } = inferBackendUrl();
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${http}/api/files/upload`, { method: "POST", body: form });
    if (!res.ok) {
      let detail: string;
      try { detail = (await res.json())?.detail ?? res.statusText; }
      catch { detail = res.statusText; }
      throw new Error(`Upload failed: ${res.status} ${detail}`);
    }
    return (await res.json()) as FileUploadResult;
  },
  getCurrentFile:   () => request<{ current: CurrentFile | null }>("GET", "/api/files/current"),
  clearCurrentFile: () => request<void>("DELETE", "/api/files/current"),

  // IoT
  iotDevices:  () => request<Array<IoTDevice>>("GET", "/api/iot/devices"),
  iotScenes:   () => request<Array<IoTScene>>("GET",  "/api/iot/scenes"),
  iotSensors:  () => request<Record<string, IoTSensor>>("GET", "/api/iot/sensors"),
  iotAction:   (
    deviceId: string,
    body: { action: string; value?: number; color?: string; duration?: number },
  ) =>
    request<{ ok: true; device: string; action: string; result: string }>(
      "POST", `/api/iot/devices/${deviceId}/action`, body,
    ),
  iotRunScene: (sceneId: string) =>
    request<{ ok: true; scene: string; result: string }>(
      "POST", `/api/iot/scenes/${sceneId}/run`,
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

export interface ApiKeyStatus {
  configured: boolean;
  source:     "env" | "file" | null;
  path:       string | null;
}

export interface AgentTask {
  task_id: string;
  goal:    string;
  status:  "pending" | "running" | "completed" | "failed" | "cancelled";
  result?: unknown;
  error?:  string;
}

export interface IoTCapabilities {
  on_off:   boolean;
  dimmable: boolean;
  rgb:      boolean;
  sensor:   string | null;
}

export interface IoTDevice {
  id:           string;
  name:         string;
  transport:    string;
  capabilities: IoTCapabilities;
}

export interface IoTScene {
  id:    string;
  name:  string;
  steps: number;
}

export interface IoTSensor {
  value:   string;
  numeric: number | null;
  age_s:   number;
}

export interface FileUploadResult {
  ok:       true;
  path:     string;
  name:     string;
  original: string;
  size:     number;
}

export interface CurrentFile {
  path:   string;
  name:   string;
  size:   number | null;
  exists: boolean;
}
