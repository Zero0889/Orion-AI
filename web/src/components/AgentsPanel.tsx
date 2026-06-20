/**
 * AgentsPanel — Orquesta de agentes con chat individual.
 *
 * Dos vistas:
 *   1. Grid: cards de cada agente con rol, proveedor, estado.
 *      Click → abre el chat con ese agente.
 *   2. Chat: conversación directa con un agente (sin orquestador).
 *      Incluye historial local, input de texto, y respuesta en vivo.
 *
 * El editor modal se abre desde el grid o desde dentro del chat.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import { api, type AgentSpec, type OrchestraAgent, type ProviderCatalog } from "@/api/rest";
import { useOrionStore } from "@/stores/orion";
import { Icon, type IconName } from "@/ui/Icon";
import { Badge, Button, Empty, Modal, SectionHeader, Switch } from "@/ui/primitives";
import { Markdown } from "@/lib/markdown";

/* ─── Icon aliases for agent roles ─────────────────────────────────── */

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
function agentIconTone(icon: string): string {
  return ICON_TONES[icon as IconName] ?? "text-pri";
}

/* ─── Chat types ───────────────────────────────────────────────────── */

interface ChatMsg {
  role: "user" | "agent";
  text: string;
  ts: number;
}

interface ChatSession {
  id: string;
  title: string;
  messages: ChatMsg[];
  createdAt: number;
}

/** All sessions across all agents: agentId → sessions[] */
type AgentSessions = Record<string, ChatSession[]>;

/* ═══════════════════════════════════════════════════════════════════════
   Main panel
   ═══════════════════════════════════════════════════════════════════════ */

export function AgentsPanel() {
  const rev = useOrionStore((s) => s.rev.orchestra);

  const [agents, setAgents] = useState<OrchestraAgent[]>([]);
  const [providers, setProviders] = useState<ProviderCatalog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Active chat — null = show grid
  const [activeAgentId, setActiveAgentId] = useState<string | null>(null);

  // Editor
  const [editing, setEditing] = useState<OrchestraAgent | null>(null);
  const [creatingNew, setCreatingNew] = useState(false);
  const [newAgentDraft, setNewDraft] = useState<OrchestraAgent | null>(null);

  // Per-agent chat sessions — persisted to localStorage
  const [sessions, setSessions] = useState<AgentSessions>(() => loadSessions());
  // Which session is active per agent
  const [activeSessions, setActiveSessions] = useState<Record<string, string>>({});

  // Save to localStorage whenever sessions change
  useEffect(() => {
    saveSessions(sessions);
  }, [sessions]);

  // Get current session for the active agent
  const currentSessionId = activeAgentId ? (activeSessions[activeAgentId] ?? "") : "";
  const currentSession =
    currentSessionId && activeAgentId
      ? (((sessions[activeAgentId] ?? []) as ChatSession[]).find(
          (s: ChatSession) => s.id === currentSessionId,
        ) ?? null)
      : null;
  const currentMessages = (currentSession?.messages as ChatMsg[]) ?? [];

  // Hydrate agents + providers
  useEffect(() => {
    let alive = true;
    setLoading(true);
    Promise.all([api.listOrchestra(), api.listProviders()])
      .then(([a, p]) => {
        if (!alive) return;
        setAgents(a);
        setProviders(p);
        setLoading(false);
      })
      .catch((e) => {
        if (alive) {
          setError(String(e));
          setLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [rev]);

  // ── Actions ─────────────────────────────────────────────────────────
  function startChat(agent: OrchestraAgent) {
    const existing = sessions[agent.id] ?? [];
    // Auto-create a session if none exists
    if (existing.length === 0) {
      const newSession = createSession("Nueva conversación");
      setSessions((prev) => ({
        ...prev,
        [agent.id]: [newSession],
      }));
      setActiveSessions((prev) => ({ ...prev, [agent.id]: newSession.id }));
    } else {
      // Use the most recent session by default
      const last = existing[existing.length - 1];
      setActiveSessions((prev) => ({ ...prev, [agent.id]: last.id }));
    }
    setActiveAgentId(agent.id);
  }

  function closeChat() {
    setActiveAgentId(null);
  }

  function addChatMsg(sessionId: string, msg: ChatMsg) {
    setSessions((prev) => {
      const next = { ...prev };
      for (const [agentId, sessList] of Object.entries(next)) {
        const idx = sessList.findIndex((s) => s.id === sessionId);
        if (idx >= 0) {
          const updated = [...sessList];
          const session = { ...updated[idx] };
          session.messages = [...session.messages, msg];
          // Auto-title from first user message
          if (
            msg.role === "user" &&
            session.messages.filter((m) => m.role === "user").length === 1
          ) {
            session.title = msg.text.slice(0, 60) + (msg.text.length > 60 ? "…" : "");
          }
          updated[idx] = session;
          next[agentId] = updated;
          break;
        }
      }
      return next;
    });
  }

  function newSession(agentId: string) {
    const session = createSession("Nueva conversación");
    setSessions((prev) => ({
      ...prev,
      [agentId]: [...(prev[agentId] ?? []), session],
    }));
    setActiveSessions((prev) => ({ ...prev, [agentId]: session.id }));
  }

  function switchSession(agentId: string, sessionId: string) {
    setActiveSessions((prev) => ({ ...prev, [agentId]: sessionId }));
  }

  function deleteSession(agentId: string, sessionId: string) {
    setSessions((prev) => {
      const next = { ...prev };
      const filtered = (next[agentId] ?? []).filter((s) => s.id !== sessionId);
      if (filtered.length === 0) {
        delete next[agentId];
      } else {
        next[agentId] = filtered;
      }
      return next;
    });
    // If deleting the active session, switch to the most recent remaining one
    setActiveSessions((prev) => {
      if (prev[agentId] === sessionId) {
        const remaining = (sessions[agentId] ?? []).filter((s) => s.id !== sessionId);
        const next = { ...prev };
        if (remaining.length > 0) {
          next[agentId] = remaining[remaining.length - 1].id;
        } else {
          delete next[agentId];
        }
        return next;
      }
      return prev;
    });
  }

  // ── Render ──────────────────────────────────────────────────────────
  const activeAgent = agents.find((a) => a.id === activeAgentId);

  return (
    <div className="flex flex-col h-full">
      <SectionHeader
        eyebrow="Sistema"
        title={activeAgent ? activeAgent.role : "Agentes autónomos"}
        hint={
          activeAgent
            ? `Conversación directa con ${activeAgent.role} (${activeAgent.model})`
            : `${agents.filter((a) => a.enabled).length} agentes listos. Click para hablar con uno.`
        }
        action={
          activeAgent ? (
            <div className="flex items-center gap-2">
              <Button size="sm" variant="ghost" icon="edit" onClick={() => setEditing(activeAgent)}>
                Editar
              </Button>
              <Button size="sm" variant="secondary" icon="arrow-left" onClick={closeChat}>
                Orquesta
              </Button>
            </div>
          ) : (
            <Button
              size="sm"
              variant="primary"
              icon="add"
              onClick={() => {
                const first = providers[0];
                setNewDraft({
                  id: "",
                  role: "",
                  icon: "sparkles",
                  description: "",
                  provider: first?.id ?? "gemini",
                  model: first?.models?.[0]?.id ?? "",
                  temperature: 0.7,
                  tools: ["*"],
                  system: "",
                  enabled: true,
                  fallback_provider: null,
                  fallback_model: null,
                  available: true,
                });
                setCreatingNew(true);
              }}
            >
              Crear agente
            </Button>
          )
        }
      />

      {/* Error banner */}
      {error && (
        <div className="mx-6 mt-3 flex items-start gap-2 p-3 rounded-md border border-danger/30 bg-danger/10 text-xs text-danger">
          <Icon name="alert" size={14} className="mt-0.5 shrink-0" />
          <span>{error}</span>
          <button
            className="ml-auto text-danger/70 hover:text-danger"
            onClick={() => setError(null)}
          >
            <Icon name="close" size={12} />
          </button>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {loading ? (
          <LoadingGrid />
        ) : activeAgent ? (
          <AgentChatView
            agent={activeAgent}
            sessions={sessions[activeAgent.id] ?? []}
            activeSessionId={currentSessionId}
            messages={currentMessages}
            onNewMsg={(msg) => addChatMsg(currentSessionId, msg)}
            onNewSession={() => newSession(activeAgent.id)}
            onSwitchSession={(sid) => switchSession(activeAgent.id, sid)}
            onDeleteSession={(sid) => deleteSession(activeAgent.id, sid)}
          />
        ) : agents.length === 0 ? (
          <Empty
            icon="chat"
            title="Sin agentes definidos"
            hint="Crea el primer agente para empezar."
            action={
              <Button
                variant="primary"
                size="sm"
                icon="add"
                onClick={() => {
                  setNewDraft({
                    id: "",
                    role: "",
                    icon: "sparkles",
                    description: "",
                    provider: "gemini",
                    model: "gemini-2.5-flash",
                    temperature: 0.7,
                    tools: ["*"],
                    system: "",
                    enabled: true,
                    fallback_provider: null,
                    fallback_model: null,
                    available: true,
                  });
                  setCreatingNew(true);
                }}
              >
                Crear agente
              </Button>
            }
          />
        ) : (
          <AgentGrid agents={agents} onChat={startChat} onEdit={(a) => setEditing(a)} />
        )}
      </div>

      {/* Editor modal */}
      <AgentEditorModal
        agent={editing}
        isNew={creatingNew}
        newDraft={newAgentDraft}
        providers={providers}
        onClose={() => {
          setEditing(null);
          setCreatingNew(false);
          setNewDraft(null);
        }}
        onSaved={() => {
          setEditing(null);
          setCreatingNew(false);
          setNewDraft(null);
        }}
        onError={(e) => setError(e)}
      />
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   Agent Grid
   ═══════════════════════════════════════════════════════════════════════ */

function AgentGrid({
  agents,
  onChat,
  onEdit,
}: {
  agents: OrchestraAgent[];
  onChat: (a: OrchestraAgent) => void;
  onEdit: (a: OrchestraAgent) => void;
}) {
  const enabled = agents.filter((a) => a.enabled);
  const disabled = agents.filter((a) => !a.enabled);

  return (
    <div className="overflow-y-auto scrollbar-thin h-full px-6 py-6">
      {/* Enabled agents */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 mb-6">
        {enabled.map((a, i) => (
          <AgentCard
            key={a.id}
            agent={a}
            index={i}
            onChat={() => onChat(a)}
            onEdit={() => onEdit(a)}
          />
        ))}
      </div>

      {/* Disabled agents */}
      {disabled.length > 0 && (
        <>
          <div className="divider-label mb-3">Inhabilitados</div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 opacity-60">
            {disabled.map((a, i) => (
              <AgentCard
                key={a.id}
                agent={a}
                index={i}
                onChat={() => onChat(a)}
                onEdit={() => onEdit(a)}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/* ─── Agent Card ────────────────────────────────────────────────────── */

function AgentCard({
  agent,
  index,
  onChat,
  onEdit,
}: {
  agent: OrchestraAgent;
  index: number;
  onChat: () => void;
  onEdit: () => void;
}) {
  const tone = agentIconTone(agent.icon);

  return (
    <button
      onClick={onChat}
      style={{ animationDelay: `${index * 50}ms` }}
      className="group relative text-left rounded-xl border border-white/[0.06]
                 bg-elevated/40 hover:bg-elevated/80 hover:border-pri/30
                 hover:shadow-glow-soft transition-all duration-200 ease-out-expo
                 p-4 animate-fade-in-up"
    >
      {/* Header */}
      <div className="flex items-start gap-3 mb-3">
        <span
          className={`grid place-items-center h-10 w-10 rounded-xl bg-white/[0.04] ${tone}
                         group-hover:bg-pri/15 group-hover:text-pri transition-colors`}
        >
          <Icon name={(agent.icon as IconName) || "circle"} size={18} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-text truncate">{agent.role}</h3>
            {!agent.enabled && <Badge tone="neutral">off</Badge>}
          </div>
          <div className="text-[10px] uppercase tracking-[0.16em] text-muted font-mono mt-0.5">
            {agent.id}
          </div>
        </div>
        {/* Edit button */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            onEdit();
          }}
          title="Editar agente"
          className="h-7 w-7 grid place-items-center rounded-md text-text-dim
                     hover:text-text hover:bg-white/[0.06] transition-colors opacity-0
                     group-hover:opacity-100"
        >
          <Icon name="settings" size={13} />
        </button>
      </div>

      {/* Description */}
      <p className="text-xs text-text-dim leading-relaxed mb-3 line-clamp-2">
        {agent.description || "Sin descripción"}
      </p>

      {/* Footer: provider + model + status */}
      <div className="flex items-center gap-2 pt-3 border-t border-white/[0.05]">
        <span
          className={`h-1.5 w-1.5 rounded-full shrink-0 ${
            agent.available ? "bg-ok shadow-[0_0_6px_rgb(var(--orion-ok))]" : "bg-warn"
          }`}
        />
        <span className="text-[10px] text-text-dim truncate flex-1">
          {useProviderLabel(agent.provider)} · {agent.model}
        </span>
        <span className="text-[9px] text-muted">Chat →</span>
      </div>
    </button>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   Agent Chat View (with session sidebar)
   ═══════════════════════════════════════════════════════════════════════ */

function AgentChatView({
  agent,
  sessions,
  activeSessionId,
  messages,
  onNewMsg,
  onNewSession,
  onSwitchSession,
  onDeleteSession,
}: {
  agent: OrchestraAgent;
  sessions: ChatSession[];
  activeSessionId: string;
  messages: ChatMsg[];
  onNewMsg: (msg: ChatMsg) => void;
  onNewSession: () => void;
  onSwitchSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
}) {
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    inputRef.current?.focus();
  }, [activeSessionId]);

  async function send() {
    const text = input.trim();
    if (!text || sending) return;

    const userMsg: ChatMsg = { role: "user", text, ts: Date.now() };
    onNewMsg(userMsg);
    setInput("");
    setSending(true);

    const chatHistory = messages.map((m) => ({ role: m.role, text: m.text }));

    try {
      const res = await api.agentChat(agent.id, text, chatHistory);
      const agentMsg: ChatMsg = { role: "agent", text: res.response, ts: Date.now() };
      onNewMsg(agentMsg);
    } catch (e) {
      const errMsg: ChatMsg = { role: "agent", text: `Error: ${e}`, ts: Date.now() };
      onNewMsg(errMsg);
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  const tone = agentIconTone(agent.icon);

  return (
    <div className="flex h-full">
      {/* Session sidebar */}
      <div
        className={`${sidebarOpen ? "w-56" : "w-0"} border-r border-white/[0.06] bg-sunken/40
                       flex flex-col transition-all duration-200 overflow-hidden shrink-0`}
      >
        <div className="p-2 border-b border-white/[0.05] flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-[0.2em] text-muted px-1">Sesiones</span>
          <button
            onClick={onNewSession}
            title="Nueva conversación"
            className="h-6 w-6 grid place-items-center rounded text-text-dim hover:text-text
                       hover:bg-white/[0.05] transition-colors"
          >
            <Icon name="add" size={13} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto scrollbar-thin py-1">
          {[...sessions].reverse().map((s) => (
            <div
              key={s.id}
              className={`group flex items-center gap-1.5 mx-1 rounded-md transition-colors ${
                s.id === activeSessionId
                  ? "bg-pri/10 border border-pri/20"
                  : "border border-transparent hover:bg-white/[0.03]"
              }`}
            >
              <button
                onClick={() => onSwitchSession(s.id)}
                className="flex-1 text-left px-2 py-2 min-w-0"
              >
                <div className="text-[11px] text-text truncate leading-tight">{s.title}</div>
                <div className="text-[9px] text-muted mt-0.5">
                  {s.messages.length} msgs · {new Date(s.createdAt).toLocaleDateString()}
                </div>
              </button>
              {sessions.length > 1 && (
                <button
                  onClick={() => onDeleteSession(s.id)}
                  title="Eliminar sesión"
                  className="h-6 w-5 grid place-items-center rounded text-text-dim/40
                             hover:text-danger hover:bg-danger/10 opacity-0 group-hover:opacity-100
                             transition-all mr-0.5 shrink-0"
                >
                  <Icon name="close" size={10} />
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Toggle sidebar button */}
      <button
        onClick={() => setSidebarOpen((v) => !v)}
        className="h-full w-5 grid place-items-center border-r border-white/[0.05]
                   bg-bg/40 hover:bg-white/[0.02] transition-colors shrink-0
                   text-text-dim hover:text-text"
        title={sidebarOpen ? "Ocultar sesiones" : "Mostrar sesiones"}
      >
        <Icon name={sidebarOpen ? "chevron-down" : "chevron-right"} size={12} />
      </button>

      {/* Chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto scrollbar-thin px-6 py-4 space-y-4">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center gap-3 px-8">
              <span
                className={`grid place-items-center h-14 w-14 rounded-2xl bg-pri/10 ${tone} mb-2`}
              >
                <Icon name={(agent.icon as IconName) || "chat"} size={24} />
              </span>
              <h3 className="text-lg font-semibold text-text">{agent.role}</h3>
              {agent.description && (
                <p className="text-sm text-text-dim max-w-sm leading-relaxed">
                  {agent.description}
                </p>
              )}
              <p className="text-xs text-muted mt-2">
                {agent.provider} · {agent.model}
              </p>
            </div>
          ) : null}

          {messages.map((msg, i) => (
            <div key={i} className={`flex gap-3 ${msg.role === "user" ? "justify-end" : ""}`}>
              {msg.role === "agent" && (
                <span
                  className={`shrink-0 h-7 w-7 grid place-items-center rounded-lg bg-white/[0.04] ${tone}`}
                >
                  <Icon name={(agent.icon as IconName) || "circle"} size={13} />
                </span>
              )}
              <div
                className={`max-w-[75%] rounded-xl px-4 py-2.5 ${
                  msg.role === "user"
                    ? "bg-pri/15 text-text border border-pri/20"
                    : "bg-elevated text-text border border-white/[0.06]"
                }`}
              >
                {msg.role === "agent" ? (
                  <Markdown source={msg.text} />
                ) : (
                  <p className="text-sm whitespace-pre-wrap leading-relaxed">{msg.text}</p>
                )}
                <span className="block text-[9px] text-muted mt-1">
                  {new Date(msg.ts).toLocaleTimeString()}
                </span>
              </div>
            </div>
          ))}

          {sending && (
            <div className="flex gap-3">
              <span
                className={`shrink-0 h-7 w-7 grid place-items-center rounded-lg bg-white/[0.04] ${tone}`}
              >
                <Icon name={(agent.icon as IconName) || "circle"} size={13} />
              </span>
              <div className="rounded-xl px-4 py-2.5 bg-elevated border border-white/[0.06]">
                <span className="flex items-center gap-1.5 text-xs text-text-dim">
                  <span
                    className="h-1 w-1 rounded-full bg-pri animate-bounce"
                    style={{ animationDelay: "0ms" }}
                  />
                  <span
                    className="h-1 w-1 rounded-full bg-pri animate-bounce"
                    style={{ animationDelay: "150ms" }}
                  />
                  <span
                    className="h-1 w-1 rounded-full bg-pri animate-bounce"
                    style={{ animationDelay: "300ms" }}
                  />
                </span>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="px-4 py-3 border-t border-white/[0.06] bg-bg/60 backdrop-blur-sm">
          <div className="flex items-center gap-2">
            <Button size="icon" variant="ghost" onClick={onNewSession} title="Nueva conversación">
              <Icon name="add" size={16} />
            </Button>
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              disabled={sending}
              placeholder={`Pregúntale a ${agent.role}…`}
              className="flex-1 h-10 px-4 rounded-lg bg-elevated border border-white/[0.08]
                         text-sm placeholder-muted
                         focus:outline-none focus:border-pri/40 focus:shadow-glow-soft
                         transition-all disabled:opacity-50"
            />
            <Button
              variant="primary"
              size="icon"
              onClick={send}
              disabled={!input.trim() || sending}
              loading={sending}
            >
              <Icon name="chat" size={16} />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   Editor Modal
   ═══════════════════════════════════════════════════════════════════════ */

function AgentEditorModal({
  agent,
  isNew,
  newDraft,
  providers,
  onClose,
  onSaved,
  onError,
}: {
  agent: OrchestraAgent | null;
  isNew: boolean;
  newDraft: OrchestraAgent | null;
  providers: ProviderCatalog[];
  onClose: () => void;
  onSaved: () => void;
  onError: (e: string) => void;
}) {
  const creating = isNew && !!newDraft;
  const show = !!agent || creating;
  const effectiveAgent = agent ?? newDraft;

  const [id, setId] = useState(effectiveAgent?.id ?? "");
  const [role, setRole] = useState(effectiveAgent?.role ?? "");
  const [icon, setIcon] = useState(effectiveAgent?.icon ?? "sparkles");
  const [description, setDesc] = useState(effectiveAgent?.description ?? "");
  const [provider, setProvider] = useState(effectiveAgent?.provider ?? "gemini");
  const [model, setModel] = useState(effectiveAgent?.model ?? "");
  const [temperature, setTemp] = useState(effectiveAgent?.temperature ?? 0.7);
  const [tools, setTools] = useState((effectiveAgent?.tools ?? []).join(", "));
  const [system, setSystem] = useState(effectiveAgent?.system ?? "");
  const [enabled, setEnabled] = useState(effectiveAgent?.enabled ?? true);
  const [fallbackProvider, setFbP] = useState(effectiveAgent?.fallback_provider ?? "");
  const [fallbackModel, setFbM] = useState(effectiveAgent?.fallback_model ?? "");
  const [showFallback, setShowFb] = useState(!!effectiveAgent?.fallback_provider);

  const [busy, setBusy] = useState(false);
  const [deleteConfirm, setDelConf] = useState(false);

  // Suggested models from the selected provider
  const suggestedModels = useMemo(() => {
    const p = providers.find((p) => p.id === provider);
    return p?.models ?? [];
  }, [provider, providers]);

  const ICONS: { id: string; label: string }[] = [
    { id: "sparkles", label: "Sparkles" },
    { id: "search", label: "Buscar" },
    { id: "code", label: "Código" },
    { id: "sigma", label: "Sigma" },
    { id: "feather", label: "Pluma" },
    { id: "chart", label: "Gráfico" },
    { id: "folder", label: "Carpeta" },
    { id: "sensors", label: "Sensor" },
    { id: "compass", label: "Brújula" },
  ];

  async function save() {
    if (!id || !provider || !model) return;
    setBusy(true);
    try {
      const spec: AgentSpec = {
        id,
        role,
        icon,
        description,
        provider,
        model,
        temperature,
        tools: tools
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        system,
        enabled,
        fallback_provider: fallbackProvider || undefined,
        fallback_model: fallbackModel || undefined,
      };
      if (creating) {
        await api.createAgent(spec);
      } else {
        const patch = { ...spec };
        delete patch.id;
        await api.updateAgent(agent!.id, patch);
      }
      onSaved();
    } catch (e) {
      onError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!agent) return;
    setBusy(true);
    try {
      await api.deleteAgent(agent.id);
      onSaved();
    } catch (e) {
      onError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={show}
      onClose={onClose}
      title={creating ? "Nuevo agente" : `Editar: ${agent?.role ?? agent?.id}`}
      eyebrow="Orquesta"
      size="lg"
      footer={
        <div className="flex items-center justify-between w-full gap-2">
          <div>
            {!creating && !deleteConfirm && (
              <Button variant="danger" size="sm" icon="trash" onClick={() => setDelConf(true)}>
                Eliminar
              </Button>
            )}
            {deleteConfirm && (
              <span className="flex items-center gap-2">
                <span className="text-xs text-danger">¿Seguro?</span>
                <Button variant="danger" size="sm" onClick={remove} loading={busy}>
                  Sí
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setDelConf(false)}>
                  No
                </Button>
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={onClose}>
              Cancelar
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={save}
              loading={busy}
              disabled={!id || !provider || !model}
            >
              {creating ? "Crear" : "Guardar"}
            </Button>
          </div>
        </div>
      }
    >
      <div className="space-y-4">
        {/* ID + Role */}
        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="text-[10px] uppercase tracking-[0.18em] text-muted">
              ID (snake_case)
            </span>
            <input
              className={inputCls}
              value={id}
              onChange={(e) => setId(e.target.value)}
              placeholder="mi_agente"
              disabled={!creating}
            />
          </label>
          <label className="block">
            <span className="text-[10px] uppercase tracking-[0.18em] text-muted">Nombre / Rol</span>
            <input
              className={inputCls}
              value={role}
              onChange={(e) => setRole(e.target.value)}
              placeholder="Matemático"
            />
          </label>
        </div>

        {/* Description */}
        <label className="block">
          <span className="text-[10px] uppercase tracking-[0.18em] text-muted">Descripción</span>
          <input
            className={inputCls}
            value={description}
            onChange={(e) => setDesc(e.target.value)}
            placeholder="Qué hace este agente…"
          />
        </label>

        {/* Icon picker */}
        <div>
          <span className="text-[10px] uppercase tracking-[0.18em] text-muted block mb-2">
            Icono
          </span>
          <div className="flex flex-wrap gap-1.5">
            {ICONS.map((ic) => (
              <button
                key={ic.id}
                onClick={() => setIcon(ic.id)}
                title={ic.label}
                className={`h-8 w-8 grid place-items-center rounded-lg border transition-all ${
                  icon === ic.id
                    ? "bg-pri/15 border-pri/40 text-pri shadow-glow-soft"
                    : "border-white/[0.06] text-text-dim hover:border-white/[0.14] hover:text-text"
                }`}
              >
                <Icon name={ic.id as IconName} size={14} />
              </button>
            ))}
          </div>
        </div>

        {/* Provider + Model */}
        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="text-[10px] uppercase tracking-[0.18em] text-muted">Proveedor</span>
            <select
              className={inputCls}
              value={provider}
              onChange={(e) => {
                setProvider(e.target.value);
                setModel("");
              }}
            >
              {providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label} {p.free ? "(gratis)" : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-[10px] uppercase tracking-[0.18em] text-muted">Modelo</span>
            <input
              className={inputCls}
              value={model}
              onChange={(e) => setModel(e.target.value)}
              list="suggested-models"
              placeholder="gemini-2.5-flash"
            />
            <datalist id="suggested-models">
              {suggestedModels.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </datalist>
          </label>
        </div>

        {/* Temperature slider */}
        <label className="block">
          <div className="flex items-baseline justify-between mb-1.5">
            <span className="text-[10px] uppercase tracking-[0.18em] text-muted">Temperatura</span>
            <span className="text-[10px] font-mono text-acc">{temperature.toFixed(1)}</span>
          </div>
          <input
            type="range"
            min="0"
            max="2"
            step="0.1"
            value={temperature}
            onChange={(e) => setTemp(parseFloat(e.target.value))}
            className="w-full accent-pri h-2"
          />
          <div className="flex justify-between text-[9px] text-muted mt-0.5">
            <span>Preciso (0)</span>
            <span>Creativo (2)</span>
          </div>
        </label>

        {/* Tools */}
        <label className="block">
          <span className="text-[10px] uppercase tracking-[0.18em] text-muted">
            Tools (* = todas)
          </span>
          <input
            className={inputCls}
            value={tools}
            onChange={(e) => setTools(e.target.value)}
            placeholder="web_search, file_controller"
          />
        </label>

        {/* System prompt */}
        <label className="block">
          <span className="text-[10px] uppercase tracking-[0.18em] text-muted">System prompt</span>
          <textarea
            className={`${inputCls} min-h-[80px] resize-y`}
            value={system}
            onChange={(e) => setSystem(e.target.value)}
            rows={3}
            placeholder="Eres el Matemático de O.R.I.O.N…"
          />
        </label>

        {/* Enabled */}
        <div className="flex items-center justify-between">
          <div>
            <span className="text-sm text-text">Habilitado</span>
            <p className="text-[11px] text-text-dim">
              Si está deshabilitado, no aparece en la orquesta
            </p>
          </div>
          <Switch on={enabled} onClick={() => setEnabled((v) => !v)} />
        </div>

        {/* Fallback (collapsible) */}
        <div className="border-t border-white/[0.06] pt-4">
          <button
            onClick={() => setShowFb((v) => !v)}
            className="flex items-center gap-2 text-xs text-text-dim hover:text-text transition-colors"
          >
            <Icon name={showFallback ? "arrow-down" : "arrow-right"} size={12} />
            Fallback (opcional)
          </button>
          {showFallback && (
            <div className="grid grid-cols-2 gap-3 mt-3">
              <label className="block">
                <span className="text-[10px] uppercase tracking-[0.18em] text-muted">
                  Proveedor alternativo
                </span>
                <input
                  className={inputCls}
                  value={fallbackProvider}
                  onChange={(e) => setFbP(e.target.value)}
                  placeholder="openrouter"
                />
              </label>
              <label className="block">
                <span className="text-[10px] uppercase tracking-[0.18em] text-muted">
                  Modelo alternativo
                </span>
                <input
                  className={inputCls}
                  value={fallbackModel}
                  onChange={(e) => setFbM(e.target.value)}
                  placeholder="deepseek/deepseek-r1:free"
                />
              </label>
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}

/* ─── Helpers ───────────────────────────────────────────────────────── */

function LoadingGrid() {
  return (
    <div className="px-6 py-6 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="skeleton h-40 rounded-xl" />
      ))}
    </div>
  );
}

/* ─── Chat session persistence (localStorage) ─────────────────────── */

const SESSIONS_KEY = "orion.agent.sessions";

function createSession(title: string): ChatSession {
  return {
    id: `s_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    title,
    messages: [],
    createdAt: Date.now(),
  };
}

function loadSessions(): AgentSessions {
  try {
    const raw = window.localStorage.getItem(SESSIONS_KEY);
    if (!raw) return {};
    return JSON.parse(raw) as AgentSessions;
  } catch {
    return {};
  }
}

function saveSessions(data: AgentSessions) {
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

function useProviderLabel(provider: string): string {
  const labels: Record<string, string> = {
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
  return labels[provider] ?? provider;
}

const inputCls = [
  "w-full px-3 h-9 text-sm rounded-md bg-surface border border-white/[0.08]",
  "focus:outline-none focus:border-pri/50 focus:shadow-glow-soft",
  "placeholder-muted transition-colors",
].join(" ");
