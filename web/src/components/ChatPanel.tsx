/**
 * ChatPanel — historial de mensajes + input de texto.
 *
 * Equivalente minimal del ChatPanel de PyQt. Renderiza ``messages`` del
 * store y envía nuevos mensajes vía WS (type: "text").
 */

import { useEffect, useRef, useState } from "react";

import { AttachmentChip } from "@/components/AttachmentChip";
import { useOrionStore } from "@/stores/orion";
import type { LogRole } from "@/types";

const ROLE_STYLES: Record<LogRole, string> = {
  user: "self-end bg-pri-dim/40 border-pri/30",
  ai:   "self-start bg-panel2 border-border-b",
  sys:  "self-center bg-transparent border-border text-text-dim text-xs italic",
  err:  "self-start bg-pri-dim/30 border-pri text-pri",
  file: "self-center bg-panel2 border-acc text-acc text-xs",
};

const ROLE_LABEL: Record<LogRole, string> = {
  user: "Tú",
  ai:   "ORION",
  sys:  "Sistema",
  err:  "Error",
  file: "Archivo",
};

interface Props {
  onSend: (text: string) => void;
}

export function ChatPanel({ onSend }: Props) {
  const messages    = useOrionStore((s) => s.messages);
  const pushLocal   = useOrionStore((s) => s.pushLocalUserText);
  const [draft, setDraft] = useState("");
  const scrollRef   = useRef<HTMLDivElement | null>(null);

  // Auto-scroll al fondo cuando cambia la lista.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length]);

  function submit() {
    const t = draft.trim();
    if (!t) return;
    pushLocal(t);     // pinta de inmediato el burbuja local
    onSend(t);        // envía por WS al backend
    setDraft("");
  }

  return (
    <div className="flex flex-col h-full">
      {/* Mensajes */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto scrollbar-thin p-4 flex flex-col gap-2"
      >
        {messages.length === 0 ? (
          <div className="text-center text-text-dim text-sm mt-12 italic">
            Esperando la primera interacción…
          </div>
        ) : (
          messages.map((m) => (
            <div
              key={m.id}
              className={`max-w-[80%] rounded-lg border px-3 py-2 ${ROLE_STYLES[m.role]}`}
            >
              {m.role !== "sys" && m.role !== "file" && (
                <div className="text-[10px] uppercase tracking-widest text-text-dim mb-1">
                  {ROLE_LABEL[m.role]}
                </div>
              )}
              <div className="whitespace-pre-wrap leading-relaxed text-sm">
                {m.text}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Input */}
      <div className="border-t border-border-b bg-panel p-3">
        <div className="mb-2"><AttachmentChip /></div>
        <div className="flex gap-2 items-end">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder="Escribe a Orion…  (Enter para enviar, Shift+Enter para salto)"
            rows={2}
            className="flex-1 resize-none rounded-md bg-panel2 border border-border-b
                       px-3 py-2 text-sm placeholder-text-dim
                       focus:outline-none focus:border-pri focus:ring-1 focus:ring-pri/40"
          />
          <button
            onClick={submit}
            disabled={!draft.trim()}
            className="rounded-md bg-pri text-bg font-medium text-sm px-4 py-2
                       disabled:opacity-30 disabled:cursor-not-allowed
                       hover:brightness-110 active:brightness-95 transition"
          >
            Enviar
          </button>
        </div>
      </div>
    </div>
  );
}
