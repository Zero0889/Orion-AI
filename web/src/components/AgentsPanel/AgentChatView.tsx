/**
 * AgentChatView — vista de conversación directa con un agente.
 *
 * Layout: sidebar de sesiones (colapsable) + área de mensajes + input.
 * Las sesiones se persisten en localStorage por agente (el padre maneja
 * el state via session helpers de `./types`).
 *
 * Comportamiento:
 *   - Auto-scroll al fondo cuando llega un mensaje nuevo.
 *   - Focus automático del input al cambiar de sesión.
 *   - Enter = enviar, Shift+Enter sin agregar (la API recibe el array
 *     completo de history para que el agente tenga contexto).
 */

import { useEffect, useRef, useState } from "react";

import { api, type OrchestraAgent } from "@/api/rest";
import { Markdown } from "@/lib/markdown";
import { Icon, type IconName } from "@/ui/Icon";
import { Button } from "@/ui/primitives";

import { agentIconTone, type ChatMsg, type ChatSession } from "./types";

export function AgentChatView({
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
