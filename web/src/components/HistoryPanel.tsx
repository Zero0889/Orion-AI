/**
 * HistoryPanel — historial de conversaciones.
 *
 * Lista izquierda con las conversaciones (más reciente arriba).
 * Click → muestra el detalle a la derecha con todos los mensajes.
 * Botón para borrar (con confirmación).
 */

import { useEffect, useState } from "react";

import { api, type ConversationDetail, type ConversationSummary } from "@/api/rest";
import { useOrionStore } from "@/stores/orion";

const ROLE_STYLES: Record<string, string> = {
  user: "self-end bg-pri-dim/40 border-pri/30",
  ai:   "self-start bg-panel2 border-border-b",
  sys:  "self-center bg-transparent border-border text-text-dim text-xs italic",
  err:  "self-start bg-pri-dim/30 border-pri text-pri",
  file: "self-center bg-panel2 border-acc text-acc text-xs",
};

const ROLE_LABEL: Record<string, string> = {
  user: "Tú",
  ai:   "ORION",
  sys:  "Sistema",
  err:  "Error",
  file: "Archivo",
};

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
      <header className="px-6 py-4 border-b border-border-b">
        <h2 className="text-sm uppercase tracking-[0.3em] text-text-dim">Historial</h2>
        <p className="text-xs text-text-dim/70 mt-1">{list.length} conversación{list.length === 1 ? "" : "es"}</p>
      </header>

      {error && (
        <div className="mx-4 mt-3 p-2 text-xs rounded border border-pri bg-pri/10 text-pri">
          {error}
        </div>
      )}

      <div className="grid grid-cols-[260px_1fr] flex-1 overflow-hidden">
        {/* Lista */}
        <aside className="border-r border-border-b overflow-y-auto scrollbar-thin">
          {list.length === 0 && (
            <p className="text-center text-text-dim text-sm italic mt-6 px-3">
              Sin conversaciones guardadas.
            </p>
          )}
          {list.map((c) => (
            <button
              key={c.id}
              onClick={() => setActive(c.id)}
              className={`group w-full text-left px-3 py-2 border-b border-border-b
                transition flex flex-col gap-0.5
                ${active === c.id
                  ? "bg-pri-dim/20 border-l-2 border-l-pri"
                  : "hover:bg-panel2"}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm truncate">{c.title || "Conversación"}</span>
                <button
                  onClick={(e) => { e.stopPropagation(); remove(c.id); }}
                  className="opacity-0 group-hover:opacity-100 text-text-dim hover:text-pri"
                  title="Borrar"
                >×</button>
              </div>
              <div className="text-[10px] uppercase tracking-widest text-text-dim flex gap-2">
                <span>{c.messages} msg</span>
                <span>·</span>
                <span>{c.started}</span>
              </div>
            </button>
          ))}
        </aside>

        {/* Detalle */}
        <main className="overflow-y-auto scrollbar-thin p-4 flex flex-col gap-2">
          {!detail && (
            <p className="text-center text-text-dim text-sm italic mt-6">
              Selecciona una conversación a la izquierda.
            </p>
          )}
          {detail?.messages.map((m, i) => (
            <div
              key={i}
              className={`max-w-[80%] rounded-lg border px-3 py-2 ${ROLE_STYLES[m.role] ?? ROLE_STYLES.sys}`}
            >
              {m.role !== "sys" && m.role !== "file" && (
                <div className="text-[10px] uppercase tracking-widest text-text-dim mb-1">
                  {ROLE_LABEL[m.role] ?? m.role}
                </div>
              )}
              <div className="whitespace-pre-wrap leading-relaxed text-sm">{m.text}</div>
              <div className="text-[10px] text-text-dim mt-1">{m.ts}</div>
            </div>
          ))}
        </main>
      </div>
    </div>
  );
}
