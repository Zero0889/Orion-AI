/**
 * AgentsPanel — Orquesta de agentes con chat individual.
 *
 * Dos vistas:
 *   1. Grid: cards de cada agente con rol, proveedor, estado.
 *      Click → abre el chat con ese agente.
 *   2. Chat: conversación directa con un agente (sin orquestador).
 *      Incluye historial local persistido en localStorage, input de
 *      texto, y respuesta en vivo.
 *
 * El editor modal se abre desde el grid o desde dentro del chat.
 *
 * Estructura (Fase 4):
 *   - index.tsx (este archivo) — shell + state cross-vista + LoadingGrid
 *   - types.ts — ChatMsg/ChatSession, helpers de iconos/proveedor, persistencia
 *   - AgentGrid.tsx — vista grilla con cards
 *   - AgentChatView.tsx — vista chat con sesiones laterales
 *   - AgentEditorModal.tsx — modal de crear/editar/borrar
 */

import { useEffect, useState } from "react";

import { api, type OrchestraAgent, type ProviderCatalog } from "@/api/rest";
import { useOrionStore } from "@/stores/orion";
import { Icon } from "@/ui/Icon";
import { Button, Empty, SectionHeader } from "@/ui/primitives";

import { AgentChatView } from "./AgentChatView";
import { AgentEditorModal } from "./AgentEditorModal";
import { AgentGrid } from "./AgentGrid";
import {
  createSession,
  loadSessions,
  saveSessions,
  type AgentSessions,
  type ChatMsg,
  type ChatSession,
} from "./types";

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
