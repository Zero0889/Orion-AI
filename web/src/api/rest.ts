/**
 * Cliente REST mínimo. Resuelve la URL del backend igual que ws.ts
 * (Vite dev → :8765 ; prod → mismo origen).
 *
 * Tipos auto-generados (Fase 3D): `src/api/generated.ts` se regenera con
 * `npm run gen:api` desde el OpenAPI del backend. Usalo así para que TS
 * marque cualquier drift al instante:
 *
 *   import type { Schemas } from "@/api/rest";
 *   type NoteBody = Schemas["NoteCreate"];
 *
 * Los `export interface` manuales más abajo se mantienen por
 * compatibilidad — migrarlos a `Schemas[...]` cuando se toque cada
 * panel (Fase 3C: god-files frontend).
 */

import type { components, paths } from "@/api/generated";
import { inferBackendUrl } from "@/api/ws";

/** Diccionario de schemas Pydantic del backend, tipado. */
export type Schemas = components["schemas"];

/** Diccionario de paths/endpoints, tipado. Útil para extraer request/response. */
export type ApiPaths = paths;

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const { http } = inferBackendUrl();
  const res = await fetch(`${http}${path}`, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail: string;
    try {
      detail = (await res.json())?.detail ?? res.statusText;
    } catch {
      detail = res.statusText;
    }
    throw new Error(`${method} ${path} → ${res.status} ${detail}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  // Notes
  listNotes: () => request<Array<NoteApi>>("GET", "/api/notes"),
  createNote: (text: string, pinned = false) =>
    request<NoteApi>("POST", "/api/notes", { text, pinned }),
  updateNote: (id: string, patch: Partial<{ text: string; pinned: boolean; color: string }>) =>
    request<{ ok: true; id: string }>("PATCH", `/api/notes/${id}`, patch),
  deleteNote: (id: string) => request<void>("DELETE", `/api/notes/${id}`),

  // Memory
  getMemory: () => request<MemoryShape>("GET", "/api/memory"),
  putMemory: (category: string, key: string, value: string) =>
    request<{ ok: true }>("PUT", `/api/memory/${category}/${key}`, { value }),
  deleteMemory: (category: string, key: string) =>
    request<void>("DELETE", `/api/memory/${category}/${key}`),

  // Conversations
  listConversations: () => request<Array<ConversationSummary>>("GET", "/api/conversations"),
  getConversation: (id: string) => request<ConversationDetail>("GET", `/api/conversations/${id}`),
  deleteConversation: (id: string) => request<void>("DELETE", `/api/conversations/${id}`),
  bulkDeleteConversations: (ids: string[]) =>
    request<{ deleted: number }>("POST", "/api/conversations/bulk_delete", {
      ids,
    }),
  deleteAllConversations: () => request<{ deleted: number }>("DELETE", "/api/conversations"),

  // NotebookLM auth
  notebookLMStatus: () => request<NotebookLMStatus>("GET", "/api/notebooklm/status"),
  notebookLMLogin: () =>
    request<{ ok: boolean; pid?: number; message: string }>("POST", "/api/notebooklm/login"),
  notebookLMCancel: () =>
    request<{ ok: boolean; message: string }>("POST", "/api/notebooklm/cancel"),

  // Settings
  getTheme: () => request<ThemeInfo>("GET", "/api/settings/theme"),
  setTheme: (name: string) =>
    request<{ ok: true; name: string; theme: Record<string, unknown> }>(
      "PATCH",
      "/api/settings/theme",
      { name },
    ),
  getApiKeyStatus: () => request<ApiKeyStatus>("GET", "/api/settings/api_key"),
  setApiKey: (key: string) =>
    request<{ ok: true; configured: true }>("POST", "/api/settings/api_key", {
      key,
    }),
  getSharing: () => request<SharingState>("GET", "/api/settings/sharing"),
  setSharing: (enabled: boolean) =>
    request<SharingState & { ok: true }>("POST", "/api/settings/sharing", {
      enabled,
    }),

  // Brain (LLM provider del chat principal). El switch se aplica en caliente.
  getBrain: () => request<BrainState>("GET", "/api/settings/brain"),
  setBrain: (provider: string, model: string) =>
    request<{ ok: true; active: BrainActive }>("PUT", "/api/settings/brain", {
      provider,
      model,
    }),
  setBrainProviderKey: (provider: string, key: string) =>
    request<{ ok: true; provider: string; configured: boolean; available: boolean }>(
      "PUT",
      `/api/settings/brain/providers/${provider}/key`,
      { key },
    ),
  getBrainOllamaStatus: () =>
    request<{ running: boolean; base_url: string; models: BrainOllamaModel[] }>(
      "GET",
      "/api/settings/brain/ollama",
    ),
  testBrain: (provider: string, model: string, prompt?: string) =>
    request<BrainTestResult>("POST", "/api/settings/brain/test", {
      provider,
      model,
      ...(prompt ? { prompt } : {}),
    }),

  // Telegram bridge (mensajería bidireccional)
  getTelegram: () => request<TelegramState>("GET", "/api/settings/telegram"),
  setTelegram: (patch: Partial<TelegramConfigPatch>) =>
    request<TelegramState>("PUT", "/api/settings/telegram", patch),
  testTelegram: (message?: string) =>
    request<{ ok: boolean; result?: Record<string, unknown> }>(
      "POST",
      "/api/settings/telegram/test",
      message ? { message } : {},
    ),

  // Agent — chat directo + orquesta CRUD
  listOrchestra: () => request<Array<OrchestraAgent>>("GET", "/api/agent/orchestra"),
  listProviders: () => request<Array<ProviderCatalog>>("GET", "/api/agent/providers"),
  createAgent: (spec: AgentSpec) => request<OrchestraAgent>("POST", "/api/agent/orchestra", spec),
  updateAgent: (id: string, patch: Partial<AgentSpec>) =>
    request<OrchestraAgent>("PUT", `/api/agent/orchestra/${id}`, patch),
  deleteAgent: (id: string) =>
    request<{ ok: true; id: string }>("DELETE", `/api/agent/orchestra/${id}`),
  agentChat: (agentId: string, message: string, history?: Array<{ role: string; text: string }>) =>
    request<{ agent_id: string; message: string; response: string }>(
      "POST",
      `/api/agent/${agentId}/chat`,
      { message, history: history ?? [] },
    ),

  // Files / drop-zone
  uploadFile: async (file: File): Promise<FileUploadResult> => {
    const { http } = inferBackendUrl();
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${http}/api/files/upload`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      let detail: string;
      try {
        detail = (await res.json())?.detail ?? res.statusText;
      } catch {
        detail = res.statusText;
      }
      throw new Error(`Upload failed: ${res.status} ${detail}`);
    }
    return (await res.json()) as FileUploadResult;
  },
  getCurrentFile: () => request<{ current: CurrentFile | null }>("GET", "/api/files/current"),
  clearCurrentFile: () => request<void>("DELETE", "/api/files/current"),

  // IoT
  iotDevices: () => request<Array<IoTDevice>>("GET", "/api/iot/devices"),
  iotScenes: () => request<Array<IoTScene>>("GET", "/api/iot/scenes"),
  iotSensors: () => request<Record<string, IoTSensor>>("GET", "/api/iot/sensors"),
  iotAction: (
    deviceId: string,
    body: { action: string; value?: number; color?: string; duration?: number },
  ) =>
    request<{ ok: true; device: string; action: string; result: string }>(
      "POST",
      `/api/iot/devices/${deviceId}/action`,
      body,
    ),
  iotRunScene: (sceneId: string) =>
    request<{ ok: true; scene: string; result: string }>("POST", `/api/iot/scenes/${sceneId}/run`),

  // ── IoT admin (mutaciones de iot_config.json) ─────────────────────
  iotConfig: () => request<IoTFullConfig>("GET", "/api/iot/config"),
  iotCreateDevice: (body: IoTDeviceBody) =>
    request<{ ok: true; id: string }>("POST", "/api/iot/admin/devices", body),
  iotUpdateDevice: (id: string, body: IoTDeviceBody) =>
    request<{ ok: true; id: string }>("PUT", `/api/iot/admin/devices/${id}`, body),
  iotDeleteDevice: (id: string) =>
    request<{ ok: true; id: string }>("DELETE", `/api/iot/admin/devices/${id}`),
  iotUpsertTransport: (id: string, body: IoTTransportBody) =>
    request<{ ok: true; id: string }>("PUT", `/api/iot/admin/transports/${id}`, body),
  iotDeleteTransport: (id: string) =>
    request<{ ok: true; id: string }>("DELETE", `/api/iot/admin/transports/${id}`),
  iotReload: () => request<{ ok: true }>("POST", "/api/iot/admin/reload"),
  iotPausedStatus: () => request<{ paused: boolean }>("GET", "/api/iot/admin/paused"),
  iotDisconnect: () => request<{ ok: true; paused: true }>("POST", "/api/iot/admin/disconnect"),
  iotConnect: () => request<{ ok: true; paused: false }>("POST", "/api/iot/admin/connect"),

  // ── Google Sheets sync ────────────────────────────────────────────
  iotSheetsStatus: () => request<IoTSheetsState>("GET", "/api/iot/sheets/status"),
  iotSheetsConnect: (body: { account: string; title?: string }) =>
    request<IoTSheetsState>("POST", "/api/iot/sheets/connect", body),
  iotSheetsDisconnect: () => request<IoTSheetsState>("POST", "/api/iot/sheets/disconnect"),
  iotSheetsSyncNow: () => request<{ ok: true }>("POST", "/api/iot/sheets/sync_now"),
  iotSheetsReformat: () => request<{ ok: true }>("POST", "/api/iot/sheets/reformat"),
  iotSheetsSetInterval: (sync_interval_s: number) =>
    request<IoTSheetsState>("PUT", "/api/iot/sheets/interval", {
      sync_interval_s,
    }),

  // ── Integraciones (gog / Google) ──────────────────────────────────
  gogAccounts: () => request<GogAccount[]>("GET", "/api/integrations/gog/accounts"),
  gogServices: () => request<GogService[]>("GET", "/api/integrations/gog/services"),
  gogFlowStatus: () => request<GogFlowStatus>("GET", "/api/integrations/gog/flow_status"),
  gogStartAuth: (body: { account: string; services?: string[]; force_consent?: boolean }) =>
    request<GogFlowStatus>("POST", "/api/integrations/gog/start_auth", body),
  gogCancelAuth: () => request<GogFlowStatus>("POST", "/api/integrations/gog/cancel"),
  gogResetAuth: () => request<GogFlowStatus>("POST", "/api/integrations/gog/reset"),
  gogCheckScopes: (body: { account: string; services: string[] }) =>
    request<GogCheckResult>("POST", "/api/integrations/gog/check", body),

  // ── MCP (servidores externos) ─────────────────────────────────────
  mcpListServers: () => request<Array<MCPServerStatus>>("GET", "/api/mcp/servers"),
  mcpListTools: () => request<Array<MCPToolInfo>>("GET", "/api/mcp/tools"),
  mcpCreateServer: (body: MCPServerBody & { id: string }) =>
    request<MCPServerStatus>("POST", "/api/mcp/servers", body),
  mcpUpdateServer: (id: string, body: MCPServerBody) =>
    request<MCPServerStatus>("PUT", `/api/mcp/servers/${id}`, body),
  mcpDeleteServer: (id: string) => request<void>("DELETE", `/api/mcp/servers/${id}`),
  mcpRestartServer: (id: string) =>
    request<{ ok: true; server_id: string; tool_count: number }>(
      "POST",
      `/api/mcp/servers/${id}/restart`,
    ),
  mcpReload: () => request<{ ok: true; tool_count: number }>("POST", "/api/mcp/reload"),
  mcpRegistrySearch: (q: string, limit = 20, cursor?: string) => {
    const qs = new URLSearchParams({ q, limit: String(limit) });
    if (cursor) qs.set("cursor", cursor);
    return request<MCPRegistryPage>("GET", `/api/mcp/registry/search?${qs.toString()}`);
  },
  mcpRegistryStars: (repoUrl: string) => {
    const qs = new URLSearchParams({ repo_url: repoUrl });
    return request<{ repo_url: string; stars: number | null }>(
      "GET",
      `/api/mcp/registry/stars?${qs.toString()}`,
    );
  },
  mcpRecipes: () => request<MCPRecipe[]>("GET", "/api/mcp/recipes"),

  // ── Skills (formato SKILL.md tipo OpenClaw/Anthropic) ─────────────
  listSkills: () => request<Array<SkillSummary>>("GET", "/api/skills/"),
  getSkill: (id: string) => request<SkillDetail>("GET", `/api/skills/${id}`),
  reloadSkills: () => request<{ ok: true; count: number }>("POST", "/api/skills/reload"),
  searchSkillRegistry: (q = "") =>
    request<Array<SkillRegistryItem>>(
      "GET",
      `/api/skills/registry/search?q=${encodeURIComponent(q)}`,
    ),
  installSkill: (name: string, source = "openclaw") =>
    request<{
      ok: true;
      id: string;
      files: string[];
      path: string;
      loaded: boolean;
    }>("POST", "/api/skills/install", { name, source }),
  // Legacy aliases (compat con código viejo del panel; usan los genéricos por debajo)
  gogStatus: () => request<CliStatus>("GET", "/api/skills/cli/gog/status"),
  gogInstall: (force = false) =>
    request<{ ok: true; name: string; path: string }>(
      "POST",
      `/api/skills/cli/gog/install${force ? "?force=true" : ""}`,
    ),
  listCli: () => request<Array<CliInfo>>("GET", "/api/skills/cli"),
  cliStatus: (name: string) => request<CliStatus>("GET", `/api/skills/cli/${name}/status`),
  cliInstall: (name: string, force = false) =>
    request<{ ok: true; name: string; path: string }>(
      "POST",
      `/api/skills/cli/${name}/install${force ? "?force=true" : ""}`,
    ),

  // ── Notificaciones (Gmail + Classroom) ──────────────────────────────
  listNotifications: (opts: { source?: string; unread?: boolean } = {}) => {
    const q = new URLSearchParams();
    if (opts.source) q.set("source", opts.source);
    if (opts.unread) q.set("unread", "true");
    const qs = q.toString();
    return request<Array<NotifItem>>("GET", `/api/notifications${qs ? "?" + qs : ""}`);
  },
  notificationsStatus: () => request<NotifPollerStatus>("GET", "/api/notifications/status"),
  pollNotifications: (source?: string) =>
    request<Record<string, unknown>>(
      "POST",
      `/api/notifications/poll${source ? "?source=" + encodeURIComponent(source) : ""}`,
    ),
  markNotificationsRead: (uids: string[]) =>
    request<{ ok: true; marked: number }>("POST", "/api/notifications/mark-read", { uids }),
  markAllNotificationsRead: (source?: string) =>
    request<{ ok: true; marked: number }>(
      "POST",
      `/api/notifications/mark-all-read${source ? "?source=" + encodeURIComponent(source) : ""}`,
    ),
  authorizeClassroom: () =>
    request<{ ok: true; token_path: string }>("POST", "/api/notifications/classroom/authorize"),

  // ── Onboarding (primer arranque) ───────────────────────────────────
  onboardingStatus: () => request<OnboardingStatus>("GET", "/api/onboarding/status"),
  onboardingSave: (geminiApiKey: string, validateRemote = true) =>
    request<OnboardingSaveResult>("POST", "/api/onboarding/save", {
      gemini_api_key: geminiApiKey,
      validate_remote: validateRemote,
    }),

  // ── Diagnóstico (panel de logs / paths / runtime info) ─────────────
  diagnosticsInfo: () => request<DiagnosticsInfo>("GET", "/api/diagnostics/info"),
  diagnosticsLogTail: (lines = 200) =>
    request<LogTailResult>("GET", `/api/diagnostics/log/tail?lines=${lines}`),
  diagnosticsOpenLogFolder: () =>
    request<{ ok: true; path: string }>("POST", "/api/diagnostics/log/open-folder"),

  // ── Access control (sistema de huella + Telegram) ─────────────────
  accessUsers: () => request<AccessUser[]>("GET", "/api/access/users"),
  accessCreateUser: (body: {
    fingerprint_id: number;
    name: string;
    phone?: string;
    active?: boolean;
  }) => request<AccessUser>("POST", "/api/access/users", body),
  accessUpdateUser: (id: string, body: { name?: string; phone?: string; active?: boolean }) =>
    request<AccessUser>("PATCH", `/api/access/users/${id}`, body),
  accessDeleteUser: (id: string) => request<void>("DELETE", `/api/access/users/${id}`),
  accessListEvents: (
    opts: {
      limit?: number;
      offset?: number;
      fingerprint_id?: number;
      since?: string;
      event_type?: string;
    } = {},
  ) => {
    const q = new URLSearchParams();
    if (opts.limit) q.set("limit", String(opts.limit));
    if (opts.offset) q.set("offset", String(opts.offset));
    if (opts.fingerprint_id !== undefined) q.set("fingerprint_id", String(opts.fingerprint_id));
    if (opts.since) q.set("since", opts.since);
    if (opts.event_type) q.set("event_type", opts.event_type);
    const qs = q.toString();
    return request<AccessEventsPage>("GET", `/api/access/events${qs ? "?" + qs : ""}`);
  },
  accessDaily: (since?: string) => {
    const qs = since ? `?since=${encodeURIComponent(since)}` : "";
    return request<AccessDailyRow[]>("GET", `/api/access/daily${qs}`);
  },

  // ── Circuit-from-image ─────────────────────────────────────────────
  circuitFromImage: (imagePath: string, outputs?: Array<"spice" | "kicad">) =>
    request<CircuitGenerateResult>("POST", "/api/circuit/from-image", {
      image_path: imagePath,
      outputs,
    }),
  circuitList: () => request<{ items: CircuitItem[] }>("GET", "/api/circuit/list"),
  circuitDelete: (path: string) =>
    request<{ ok: true }>("DELETE", `/api/circuit/item?path=${encodeURIComponent(path)}`),
  circuitProteusAutodraw: (
    cirPath: string,
    opts: { countdown?: number; placeInCanvas?: boolean; cols?: number } = {},
  ) =>
    request<{ ok: boolean; summary: string }>("POST", "/api/circuit/proteus-autodraw", {
      cir_path: cirPath,
      countdown: opts.countdown ?? 3,
      place_in_canvas: opts.placeInCanvas ?? true,
      cols: opts.cols ?? 3,
    }),
};

// ── Brain (cerebro del chat principal) ──────────────────────────────────
// El catálogo lo sirve el backend (orion/server/routes/brain.py) para
// que el frontend no tenga que mantener su propia lista hardcodeada de
// modelos por provider — si el backend agrega un modelo, aparece solo.

export interface BrainActive {
  provider: string;
  model: string;
  is_live: boolean;
}

export interface BrainProviderModel {
  id: string;
  label: string;
}

export interface BrainProvider {
  id: string;
  label: string;
  free: boolean;
  auth_hint: string;
  models: BrainProviderModel[];
  default_model: string;
  available: boolean;
  needs_key: boolean;
}

export interface BrainOllamaModel {
  name: string;
  size: number;
  modified_at: string;
}

export interface BrainOllamaStatus {
  running: boolean;
  base_url: string;
  models: BrainOllamaModel[];
}

export interface BrainState {
  active: BrainActive;
  providers: BrainProvider[];
  ollama: BrainOllamaStatus;
  gemini: { configured: boolean };
}

export interface BrainTestResult {
  ok: boolean;
  text?: string;
  model?: string;
  provider?: string;
  error?: string;
  actionable?: boolean;
}

export interface OnboardingStatus {
  ready: boolean;
  has_api_key: boolean;
  base_dir: string;
  config_dir: string;
  data_dir: string;
  api_keys_path: string;
  // El cerebro activo + si su provider está disponible. Si el usuario
  // ya completó el wizard eligiendo DeepSeek/Ollama, `ready` viene true
  // aunque no haya key Gemini.
  brain: {
    provider: string;
    model: string;
    is_live: boolean;
    available: boolean;
  };
}

export interface OnboardingSaveResult {
  ok: boolean;
  message: string;
  api_keys_path: string | null;
}

export interface DiagnosticsInfo {
  base_dir: string;
  resources_dir: string;
  config_dir: string;
  data_dir: string;
  api_keys_path: string;
  log_path: string;
  log_dir: string;
  python_version: string;
  platform: string;
  frozen: boolean;
  sys_executable: string;
}

export interface LogTailResult {
  path: string;
  exists: boolean;
  size_bytes: number;
  lines: string[];
  truncated: boolean;
}

export interface NotifItem {
  uid: string;
  source: string;
  title: string;
  summary: string;
  url: string | null;
  received_ts: number;
  metadata: Record<string, unknown>;
}

export interface NotifPollerStatus {
  running: boolean;
  last_status: Record<
    string,
    {
      ok: boolean;
      ts: number;
      error?: string;
      // Backend clasifica el error: setup_required (OAuth client borrado en
      // GCP), auth_required (falta autorizar la cuenta), transient (red/5xx).
      error_kind?: "setup_required" | "auth_required" | "transient";
      user_message?: string;
      doc?: string | null;
    }
  >;
  // Opcional para tolerar backends viejos que no expongan estos campos.
  is_configured?: Record<string, boolean>;
  setup_required?: Record<string, boolean>;
  config: {
    enabled: boolean;
    interval_seconds: number;
    max_per_source: number;
    sources: Record<string, { enabled: boolean }>;
  };
}

export interface SkillSummary {
  id: string;
  name: string;
  description: string;
  user_invocable: boolean;
  char_count: number;
  path: string;
}

export interface SkillDetail extends SkillSummary {
  body: string;
  frontmatter: Record<string, unknown>;
  max_inject: number;
}

export interface SkillRegistryItem {
  id: string;
  html_url: string;
  source: "openclaw";
}

export interface CliInfo {
  name: string;
  repo: string;
  version: string;
  description: string;
  installed: boolean;
  path: string | null;
}

export interface CliStatus {
  name: string;
  installed: boolean;
  path: string | null;
  managed: boolean;
  version: string;
}

// ── Types ──────────────────────────────────────────────────────────────
export interface NoteApi {
  id: string;
  text: string;
  pinned: boolean;
  color?: string;
  created: string;
  updated: string;
}

export interface MemoryEntry {
  value: string;
  updated?: string;
}

export type MemoryCategory =
  | "identity"
  | "preferences"
  | "projects"
  | "relationships"
  | "wishes"
  | "notes";

export type MemoryShape = Record<MemoryCategory, Record<string, MemoryEntry>>;

export interface ConversationSummary {
  id: string;
  started: string;
  title: string;
  messages: number;
}

export interface ConversationDetail {
  id: string;
  started: string;
  title: string;
  messages: Array<{ role: string; text: string; ts: string }>;
}

export interface ThemeInfo {
  name: string;
  theme: Record<string, unknown>;
  available: Array<{ id: string; name: string }>;
}

export interface ApiKeyStatus {
  configured: boolean;
  source: "env" | "file" | null;
  path: string | null;
}

export interface SharingState {
  enabled: boolean;
  tailscale_ip: string | null;
  port: number;
}

export interface TelegramState {
  enabled: boolean;
  configured: boolean;
  has_token: boolean;
  token_preview: string;
  default_chat_id: string;
  forward_notifications: boolean;
  running: boolean;
  bot_username: string | null;
  bot_ok: boolean;
  bot_error: string | null;
}

export interface TelegramConfigPatch {
  bot_token: string;
  default_chat_id: string;
  forward_notifications: boolean;
  enabled: boolean;
}

export interface OrchestraAgent {
  id: string;
  role: string;
  icon: string;
  description: string;
  provider: string;
  model: string;
  temperature: number;
  tools: string[];
  system: string;
  enabled: boolean;
  fallback_provider: string | null;
  fallback_model: string | null;
  available: boolean;
}

/** Lo que mandamos al POST (crear) y PUT (patch parcial) de /api/agent/orchestra. */
export interface AgentSpec {
  id?: string; // solo en POST
  role?: string;
  icon?: string;
  description?: string;
  provider?: string;
  model?: string;
  temperature?: number;
  tools?: string[];
  system?: string;
  enabled?: boolean;
  fallback_provider?: string | null;
  fallback_model?: string | null;
}

export interface ProviderModel {
  id: string;
  label: string;
}

export interface ProviderCatalog {
  id: string; // "gemini", "openrouter", "groq", ...
  label: string; // "Gemini", "OpenRouter", ...
  free: boolean; // ¿tier gratuito?
  auth_hint: string; // dónde poner la key
  models: ProviderModel[]; // sugeridos en dropdown
  available: boolean; // ¿key configurada?
}

export interface IoTCapabilities {
  on_off: boolean;
  dimmable: boolean;
  rgb: boolean;
  sensor: string | null;
}

export interface IoTDevice {
  id: string;
  name: string;
  transport: string;
  capabilities: IoTCapabilities;
  serial?: Record<string, unknown> | null;
  mqtt?: Record<string, unknown> | null;
}

/** Lo que mandamos al POST/PUT de admin/devices. */
export interface IoTDeviceBody {
  id?: string; // solo en POST
  name: string;
  transport: string;
  capabilities: IoTCapabilities;
  serial?: Record<string, unknown>;
  mqtt?: Record<string, unknown>;
}

/** Transport en disco. Discriminado por `type`. */
export type IoTTransportBody =
  | { type: "serial"; port: string; baud?: number }
  | {
      type: "mqtt";
      host: string;
      mqtt_port?: number;
      username?: string;
      password?: string;
      client_id?: string;
      tls?: boolean;
    };

export interface IoTFullConfig {
  version: number;
  transports: Record<string, Record<string, unknown>>;
  devices: Record<string, Record<string, unknown>>;
  scenes: Record<string, unknown>;
}

export interface IoTScene {
  id: string;
  name: string;
  steps: number;
}

export interface IoTSensor {
  value: string;
  numeric: number | null;
  age_s: number;
}

export interface GogAccount {
  email: string;
  services: string[];
  scopes: string[];
  client: string;
  created_at: string;
}

export interface GogService {
  service: string;
  scopes: string[];
  apis: string[];
  user: boolean;
}

export interface GogFlowStatus {
  status: "idle" | "running" | "success" | "error" | "cancelled";
  account?: string;
  services?: string[];
  started_at?: number;
  finished_at?: number;
  auth_url?: string | null;
  message?: string | null;
}

export interface GogCheckResult {
  satisfied: boolean;
  missing: string[];
  account_exists: boolean;
  error?: string;
}

export interface IoTSheetsState {
  enabled: boolean;
  account: string | null;
  spreadsheet_id: string | null;
  spreadsheet_url: string | null;
  sheet_name: string;
  last_pushed_row: number;
  last_sync_at: string | null;
  last_error: string | null;
  sync_interval_s: number;
}

export interface FileUploadResult {
  ok: true;
  path: string;
  name: string;
  original: string;
  size: number;
}

export interface CurrentFile {
  path: string;
  name: string;
  size: number | null;
  exists: boolean;
}

// ── Circuit-from-image ──────────────────────────────────────────────────
export interface CircuitGenerateResult {
  ok: true;
  summary: string;
  spice_path?: string;
  kicad_path?: string;
}

export interface CircuitItem {
  name: string;
  path: string;
  kind: "spice" | "kicad";
  size: number;
  modified: number;
}

// ── MCP ─────────────────────────────────────────────────────────────────
// ── NotebookLM ──────────────────────────────────────────────────────────
export interface NotebookLMLoginState {
  status: "idle" | "running" | "success" | "failed";
  message: string;
  started_at: number;
  finished_at: number;
  elapsed: number;
}
export interface NotebookLMStatus {
  installed: boolean;
  cli_path: string | null;
  has_session: boolean;
  login: NotebookLMLoginState;
}

export interface MCPServerBody {
  command: string;
  args?: string[];
  env?: Record<string, string>;
  enabled?: boolean;
  cwd?: string | null;
  startup_timeout?: number;
  call_timeout?: number;
}

export interface MCPToolBrief {
  name: string;
  description: string;
}

export interface MCPServerStatus {
  id: string;
  command: string;
  args: string[];
  env: Record<string, string>;
  enabled: boolean;
  cwd: string | null;
  startup_timeout: number;
  call_timeout: number;
  running: boolean;
  tool_count: number;
  tools: MCPToolBrief[];
  error?: string | null;
}

export interface MCPToolInfo {
  name: string;
  server_id: string;
  description: string;
  timeout: number;
}

// ── Registry (catálogo público) ─────────────────────────────────────────
export interface MCPRegistryEnvVar {
  name: string;
  description: string;
  required: boolean;
}

export interface MCPRegistryPackage {
  command: string;
  args: string[];
  env_required: MCPRegistryEnvVar[];
  registry_type: string;
  identifier: string;
  version: string;
}

export interface MCPRegistryServer {
  name: string;
  title: string;
  description: string;
  version: string;
  repository: string | null;
  packages: MCPRegistryPackage[];
  installable: boolean;
  /** True si el server solo expone transports HTTP/SSE (remote-only).
   *  El cliente MCP actual de ORION es stdio, así que no son instalables
   *  hoy — pero los mostramos diferenciados para que se sepa que existen. */
  remote: boolean;
  remote_kinds: string[];
}

export interface MCPRegistryPage {
  servers: MCPRegistryServer[];
  next_cursor: string | null;
  count: number;
}

// ── Recetas curadas (servers populares pre-armados) ────────────────────
export type MCPRecipeCategory = "files" | "dev" | "web" | "ai" | "system";

export interface MCPRecipePrompt {
  key: string;
  label: string;
  description: string;
  default: string;
  required: boolean;
}

export interface MCPRecipeEnv {
  name: string;
  description: string;
  required: boolean;
}

export interface MCPRecipe {
  recipe_id: string;
  title: string;
  description: string;
  category: MCPRecipeCategory;
  command: string;
  args_template: string[];
  suggested_id: string;
  repo_url: string;
  prompts: MCPRecipePrompt[];
  env_required: MCPRecipeEnv[];
  official: boolean;
}

// ── Access control (huella + Telegram) ────────────────────────────────
// Mapping huella↔persona + registros crudos + reporte diario.
//
// Estos tipos se exportan como re-mapeo de `Schemas[...]` autogenerados
// desde el OpenAPI del backend (ver `routes/access.py::AccessUserOut`,
// `AccessEventOut`, etc.). Si el backend renombra un campo, TS marca
// drift en el siguiente `npm run gen:api`.

export type AccessUser = Schemas["AccessUserOut"];
export type AccessEvent = Schemas["AccessEventOut"];
export type AccessEventType = AccessEvent["event_type"];
export type AccessEventsPage = Schemas["AccessEventsPageOut"];
export type AccessDailyRow = Schemas["AccessDailyRowOut"];
