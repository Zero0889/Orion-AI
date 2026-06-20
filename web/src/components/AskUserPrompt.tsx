/**
 * AskUserPrompt — renderiza la pregunta interactiva pendiente del agente.
 *
 * Cuando un agente (researcher, writer, coder, etc) invoca la tool
 * `ask_user`, el backend emite `ask_user.start` por WS, el handler del
 * store empuja el payload a `useAskUserStore`, y este componente
 * renderiza un menú clickeable arriba del composer en ChatPanel.
 *
 * Al elegir una opción (o cancelar), enviamos `ask_user.response` /
 * `ask_user.cancel` por WS — el backend desbloquea la tool y el agente
 * recibe la respuesta como tool-response para continuar.
 *
 * Solo aparece si hay una pregunta pendiente; null cuando no.
 */

import { useState } from "react";

import { useAskUserStore } from "@/stores/askUser";
import { Icon } from "@/ui/Icon";

interface Props {
  /** El sender del WS — viene del hook useOrionSocket que vive en App.tsx
   *  y se pasa a ChatPanel. Lo aceptamos como prop para no acoplarnos
   *  al hook acá (más fácil de testear, evita ciclos de import). */
  send: (type: string, payload?: Record<string, unknown>) => void;
}

export function AskUserPrompt({ send }: Props) {
  const pending = useAskUserStore((s) => s.pending);
  const clear = useAskUserStore((s) => s.clear);

  // Estado local para el modo "Otro" — input de texto libre
  const [otherMode, setOtherMode] = useState(false);
  const [otherText, setOtherText] = useState("");

  if (!pending) return null;

  function submit(answer: string) {
    if (!pending) return;
    send("ask_user.response", { question_id: pending.questionId, answer });
    setOtherMode(false);
    setOtherText("");
    clear();
  }

  function cancel() {
    if (!pending) return;
    send("ask_user.cancel", { question_id: pending.questionId });
    setOtherMode(false);
    setOtherText("");
    clear();
  }

  return (
    <div className="border-t border-pri/30 bg-pri/[0.04] animate-fade-in-up">
      <div className="mx-auto max-w-3xl px-4 md:px-8 py-4">
        {/* Header: badge + pregunta */}
        <div className="flex items-start gap-3 mb-3">
          <div
            className="grid place-items-center h-7 w-7 rounded-md bg-pri/15 text-pri shrink-0
                          shadow-[0_0_12px_rgb(var(--orion-pri-glow)/0.35)]"
          >
            <Icon name="search" size={14} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[10px] uppercase tracking-[0.24em] text-pri/80 font-mono">
              Orion pregunta
            </div>
            <div className="mt-1 text-sm text-text leading-relaxed">{pending.question}</div>
          </div>
          <button
            onClick={cancel}
            className="h-7 w-7 grid place-items-center rounded text-text-dim
                       hover:text-danger hover:bg-danger/10 transition-colors shrink-0"
            title="Cancelar"
          >
            <Icon name="close" size={14} />
          </button>
        </div>

        {/* Opciones */}
        {!otherMode ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {pending.options.map((opt, i) => (
              <button
                key={`${opt.label}-${i}`}
                onClick={() => submit(opt.label)}
                style={{ animationDelay: `${60 * i}ms` }}
                className="group relative text-left rounded-lg px-3 py-2.5
                           border border-white/[0.08] bg-elevated/60
                           hover:border-pri/40 hover:bg-pri/10
                           transition-all duration-150 animate-fade-in-up"
              >
                <div className="text-sm text-text font-medium leading-snug">{opt.label}</div>
                {opt.description && (
                  <div className="text-[11px] text-text-dim mt-0.5 leading-relaxed">
                    {opt.description}
                  </div>
                )}
                <Icon
                  name="chevron-right"
                  size={13}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted
                             opacity-0 group-hover:opacity-100 group-hover:translate-x-0.5
                             transition-all duration-200"
                />
              </button>
            ))}
            {pending.allowOther && (
              <button
                onClick={() => setOtherMode(true)}
                className="text-left rounded-lg px-3 py-2.5
                           border border-dashed border-white/[0.10] bg-transparent
                           hover:border-pri/40 hover:bg-pri/[0.04]
                           transition-all duration-150"
              >
                <div
                  className="text-sm text-text-dim italic leading-snug
                                flex items-center gap-2"
                >
                  <Icon name="edit" size={12} />
                  Otro… (escribir respuesta libre)
                </div>
              </button>
            )}
          </div>
        ) : (
          // Modo Otro — input libre
          <div className="flex gap-2 items-center">
            <input
              autoFocus
              value={otherText}
              onChange={(e) => setOtherText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && otherText.trim()) submit(otherText.trim());
                if (e.key === "Escape") {
                  setOtherMode(false);
                  setOtherText("");
                }
              }}
              placeholder="Tu respuesta…"
              className="flex-1 h-9 rounded-md bg-elevated border border-pri/40
                         px-3 text-sm placeholder-muted focus:outline-none focus:border-pri"
            />
            <button
              onClick={() => {
                setOtherMode(false);
                setOtherText("");
              }}
              className="h-9 px-3 rounded-md text-xs text-text-dim hover:text-text
                         hover:bg-white/[0.05] transition-colors"
            >
              Cancelar
            </button>
            <button
              onClick={() => otherText.trim() && submit(otherText.trim())}
              disabled={!otherText.trim()}
              className="h-9 px-4 rounded-md text-xs font-medium
                         bg-pri text-bg hover:brightness-110
                         disabled:bg-elevated disabled:text-muted disabled:cursor-not-allowed
                         transition-all"
            >
              Enviar
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
