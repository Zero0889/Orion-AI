/**
 * HistoryPanel — conversation history.
 *
 * Two-pane layout: list (left) + detail (right). Premium card list with
 * hover affordances. Detail re-uses the chat presentation style.
 */

import { useEffect, useState } from "react";

import { api, type ConversationDetail, type ConversationSummary } from "@/api/rest";
import { useOrionStore } from "@/stores/orion";
import { Icon } from "@/ui/Icon";
import { Badge, Empty, SectionHeader, Surface } from "@/ui/primitives";

export function HistoryPanel() {
  const rev = useOrionStore((s) => s.rev.convs);
  const [list,    setList]    = useState<ConversationSummary[]>([]);
  const [active,  setActive]  = useState<string | null>(null);
  const [detail,  setDetail]  = useState<ConversationDetail | null>(null);
  const [error,   setError]   = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.listConversations()
      .then((cs) => { if (alive) { setList(cs); setError(null); } })
      .catch((e) => { if (alive) setError(String(e)); });
    return () => { alive = false; };
  }, [rev]);

  useEffect(() => {
    if (!active) { setDetail(null); return; }
    let alive = true;
    api.getConversation(active)
      .then((c) => { if (alive) setDetail(c); })
      .catch((e) => { if (alive) setError(String(e)); });
    return () => { alive = false; };
  }, [active, rev]);

  async function remove(id: string) {
    if (!confirm("¿Borrar esta conversación?")) return;
    try {
      await api.deleteConversation(id);
      if (active === id) { setActive(null); setDetail(null); }
    } catch (e) { setError(String(e)); }
  }

  return (
    <div className="flex flex-col h-full">
      <SectionHeader
        eyebrow="Conocimiento"
        title="Historial"
        hint="Conversaciones pasadas con Orion, persistidas localmente."
        action={<Badge tone="neutral">{list.length}</Badge>}
      />

      {error && (
        <div className="mx-6 mt-3 flex items-start gap-2 p-3 rounded-md border border-danger/30 bg-danger/10 text-xs text-danger">
          <Icon name="alert" size={14} className="mt-0.5 shrink-0" /><span>{error}</span>
        </div>
      )}

      <div className="grid grid-cols-[300px_1fr] flex-1 overflow-hidden">
        {/* list */}
        <aside className="border-r border-white/[0.06] overflow-y-auto scrollbar-thin p-3">
          {list.length === 0 && (
            <Empty icon="history" title="Sin conversaciones" hint="Cuando tengas tu primera charla con Orion aparecerá aquí." />
          )}
          <div className="flex flex-col gap-1.5">
            {list.map((c, i) => {
              const isActive = active === c.id;
              return (
                <button
                  key={c.id}
                  onClick={() => setActive(c.id)}
                  style={{ animationDelay: `${i * 20}ms` }}
                  className={[
                    "group relative text-left rounded-lg px-3 py-2.5 border transition-all duration-200 ease-out-expo animate-fade-in",
                    isActive
                      ? "bg-pri/10 border-pri/35 shadow-glow-soft"
                      : "bg-elevated/40 border-white/[0.05] hover:border-white/[0.12]",
                  ].join(" ")}
                >
                  {isActive && (
                    <span className="absolute left-0 top-2 bottom-2 w-[2px] rounded-full bg-pri shadow-[0_0_8px_rgb(var(--orion-pri))]" />
                  )}
                  <div className="flex items-center justify-between gap-2">
                    <span className={`text-sm font-medium truncate ${isActive ? "text-text" : "text-text"}`}>
                      {c.title || "Conversación"}
                    </span>
                    <button
                      onClick={(e) => { e.stopPropagation(); remove(c.id); }}
                      title="Borrar"
                      className="h-6 w-6 grid place-items-center rounded text-muted
                                 opacity-0 group-hover:opacity-100 hover:text-danger hover:bg-danger/10"
                    >
                      <Icon name="close" size={12} />
                    </button>
                  </div>
                  <div className="mt-1 flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] text-muted">
                    <span>{c.messages} msg</span>
                    <span className="text-white/[0.10]">·</span>
                    <span>{c.started}</span>
                  </div>
                </button>
              );
            })}
          </div>
        </aside>

        {/* detail */}
        <main className="overflow-y-auto scrollbar-thin">
          {!detail ? (
            <div className="h-full grid place-items-center">
              <Empty icon="chat" title="Selecciona una conversación" hint="Haz clic en cualquier elemento de la lista para abrirla." />
            </div>
          ) : (
            <div className="mx-auto max-w-3xl px-6 py-6 flex flex-col gap-5 animate-fade-in">
              <header className="border-b border-white/[0.06] pb-3 mb-1">
                <div className="text-[10px] uppercase tracking-[0.22em] text-pri/80">Conversación</div>
                <h3 className="text-base font-semibold text-text mt-0.5">{detail.title || detail.id}</h3>
                <div className="text-[11px] text-muted mt-0.5">{detail.started}</div>
              </header>
              {detail.messages.map((m, i) => (
                <DetailMessage key={i} role={m.role} text={m.text} ts={m.ts} />
              ))}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function DetailMessage({ role, text, ts }: { role: string; text: string; ts: string }) {
  if (role === "sys" || role === "err") {
    return (
      <div className="flex items-center gap-2 my-1">
        <span className={`h-1 w-1 rounded-full ${role === "err" ? "bg-danger" : "bg-muted"}`} />
        <span className={`text-xs italic ${role === "err" ? "text-danger" : "text-text-dim"}`}>{text}</span>
        <span className="text-[10px] text-muted ml-1">{ts}</span>
      </div>
    );
  }
  if (role === "file") {
    return (
      <div className="self-start">
        <Surface level={2} className="inline-flex items-center gap-2 px-3 py-1.5 text-xs text-acc">
          <Icon name="paperclip" size={13} /><span>{text}</span>
        </Surface>
      </div>
    );
  }
  if (role === "user") {
    return (
      <div className="self-end max-w-[78%]">
        <div className="rounded-2xl rounded-tr-md px-4 py-2.5 bg-pri/10 border border-pri/20">
          <div className="whitespace-pre-wrap leading-relaxed text-sm text-text">{text}</div>
        </div>
        <div className="text-right text-[9px] uppercase tracking-[0.22em] text-muted mt-1">Tú · {ts}</div>
      </div>
    );
  }
  return (
    <div className="self-start max-w-[90%]">
      <div className="flex items-center gap-2 mb-1.5">
        <span className="h-2 w-2 rounded-full bg-pri" />
        <span className="text-[10px] uppercase tracking-[0.22em] text-pri/90 font-medium">Orion</span>
        <span className="text-[10px] text-muted">{ts}</span>
      </div>
      <div className="whitespace-pre-wrap leading-[1.7] text-[15px] text-text">{text}</div>
    </div>
  );
}
