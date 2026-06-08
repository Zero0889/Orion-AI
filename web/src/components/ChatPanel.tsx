/**
 * ChatPanel — the core AI conversation surface.
 *
 * Two presentations:
 *   - Empty hero (no messages yet): the OrbHUD is the centerpiece, with
 *     prompt suggestions below.
 *   - Conversation: messages stream into a focused timeline; the orb
 *     becomes a small status marker in the corner. Each message animates
 *     in with fade-in-up; assistant turns are bubbleless prose, user
 *     turns are aligned chips, file/system are timeline rows.
 *
 * Backend contract unchanged: send arrives via the `onSend` prop and the
 * store keeps absorbing WS events.
 *
 * I-18 TODO: virtualizar la timeline con react-virtuoso cuando el array
 * messages crezca a >150 items. Hoy renderizamos 300 (MAX_MESSAGES en el
 * store) en flat sin virtualización — scroll fluido hasta ~100, después
 * empieza a sentirse. Pendiente porque requiere añadir la dep al
 * package.json y reescribir el Timeline para integrarse con la animación
 * fade-in-up que hoy se aplica por elemento. Bloquea ningún feature.
 */

import { useEffect, useRef, useState } from "react";

import { AttachmentChip } from "@/components/AttachmentChip";
import { OrbHUD } from "@/components/OrbHUD";
import { ToolBanner } from "@/components/ToolBanner";
import { Markdown } from "@/lib/markdown";
import { useOrionStore } from "@/stores/orion";
import type { ChatMessage, LogRole } from "@/types";
import { Icon } from "@/ui/Icon";
import { Button, Kbd } from "@/ui/primitives";

const SUGGESTIONS: { eyebrow: string; prompt: string }[] = [
  { eyebrow: "Sistema",     prompt: "¿Cómo está el sistema ahora mismo?" },
  { eyebrow: "Memoria",     prompt: "Recuérdame mis proyectos activos." },
  { eyebrow: "Hogar",       prompt: "Pon una escena tranquila en el salón." },
  { eyebrow: "Agentes",     prompt: "Lanza una tarea para resumir mis notas." },
];

interface Props {
  onSend: (text: string) => void;
}

export function ChatPanel({ onSend }: Props) {
  const messages    = useOrionStore((s) => s.messages);
  const pushLocal   = useOrionStore((s) => s.pushLocalUserText);
  const state       = useOrionStore((s) => s.state);
  const currentFile = useOrionStore((s) => s.currentFile);
  const [draft, setDraft] = useState("");
  const scrollRef   = useRef<HTMLDivElement | null>(null);
  const taRef       = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length]);

  // autosize textarea
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "0px";
    ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
  }, [draft]);

  function submit(text?: string) {
    const t = (text ?? draft).trim();
    if (!t) return;
    pushLocal(t);
    onSend(t);
    setDraft("");
  }

  const empty = messages.length === 0;

  return (
    <div className="flex flex-col h-full relative">
      {/* ambient atmosphere when empty */}
      {empty && (
        <div className="pointer-events-none absolute inset-0 bg-dots opacity-50" />
      )}

      {/* tool / agent activity banner — solo cuando hay actividad real */}
      <ToolBanner />

      {/* messages */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto scrollbar-thin"
      >
        {empty
          ? <Hero onPick={(p) => { setDraft(p); taRef.current?.focus(); }} />
          : <Timeline messages={messages} state={state} />}
      </div>

      {/* composer */}
      <Composer
        taRef={taRef}
        draft={draft}
        onChange={setDraft}
        onSubmit={() => submit()}
        currentFile={currentFile}
      />
    </div>
  );
}

/* ─── HERO (empty state) ──────────────────────────────────────────── */
function Hero({ onPick }: { onPick: (p: string) => void }) {
  return (
    <div className="h-full flex flex-col items-center justify-center px-6 py-10 animate-fade-in">
      <OrbHUD />

      <h1 className="mt-10 text-2xl md:text-3xl font-semibold tracking-tight text-text text-center max-w-xl">
        Bienvenido a Orion
      </h1>
      <p className="mt-2 text-sm text-text-dim text-center max-w-md leading-relaxed">
        Tu sistema operativo asistido por IA. Pídeme algo en voz alta o escribe abajo.
      </p>

      <div className="mt-9 grid grid-cols-1 md:grid-cols-2 gap-2 w-full max-w-2xl">
        {SUGGESTIONS.map((s, i) => (
          <button
            key={s.prompt}
            onClick={() => onPick(s.prompt)}
            style={{ animationDelay: `${80 * i}ms` }}
            className="group relative text-left rounded-lg surface-1 px-4 py-3
                       hover:border-white/[0.12] hover:bg-elevated/70
                       transition-all duration-200 ease-out-expo
                       animate-fade-in-up"
          >
            <div className="text-[10px] uppercase tracking-[0.2em] text-pri/80">{s.eyebrow}</div>
            <div className="mt-1 text-sm text-text leading-snug">{s.prompt}</div>
            <Icon
              name="chevron-right"
              size={14}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted
                         opacity-0 group-hover:opacity-100 group-hover:translate-x-0.5
                         transition-all duration-200"
            />
          </button>
        ))}
      </div>
    </div>
  );
}

/* ─── TIMELINE ────────────────────────────────────────────────────── */
function Timeline({ messages, state }: { messages: ChatMessage[]; state: string }) {
  return (
    <div className="mx-auto max-w-3xl px-4 md:px-8 py-6 flex flex-col gap-5">
      {/* persistent status row at the top */}
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] text-text-dim mb-1">
        <span className="h-1.5 w-1.5 rounded-full bg-pri shadow-[0_0_8px_rgb(var(--orion-pri))] animate-pulse-soft" />
        <span>Sesión activa</span>
        <span className="text-muted">·</span>
        <span>{state.toLowerCase()}</span>
      </div>

      {messages.map((m, i) => (
        <MessageRow
          key={m.id}
          msg={m}
          isLastAssistant={
            m.role === "ai" &&
            !messages.slice(i + 1).some((x) => x.role === "ai")
          }
        />
      ))}

      {/* "thinking" indicator when last message is user and orion state is PENSANDO */}
      {messages[messages.length - 1]?.role === "user" && state === "PENSANDO" && (
        <TypingDots />
      )}
    </div>
  );
}

function MessageRow({ msg, isLastAssistant }: { msg: ChatMessage; isLastAssistant: boolean }) {
  const r: LogRole = msg.role;

  if (r === "sys" || r === "err") {
    return (
      <div className="flex items-center gap-2 my-1 animate-fade-in">
        <span className={`h-1 w-1 rounded-full ${r === "err" ? "bg-danger" : "bg-muted"}`} />
        <span className={`text-xs italic ${r === "err" ? "text-danger" : "text-text-dim"}`}>
          {msg.text}
        </span>
      </div>
    );
  }

  if (r === "file") {
    return (
      <div className="self-start animate-fade-in-up">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md border border-acc/30 bg-acc/5 text-acc text-xs">
          <Icon name="paperclip" size={13} />
          <span className="truncate max-w-xs">{msg.text}</span>
        </div>
      </div>
    );
  }

  if (r === "user") {
    return (
      <div className="self-end max-w-[78%] animate-fade-in-up">
        <div className="rounded-2xl rounded-tr-md px-4 py-2.5 bg-pri/15 border border-pri/25 text-text">
          <div className="whitespace-pre-wrap leading-relaxed text-sm">{msg.text}</div>
        </div>
        <div className="text-right text-[9px] uppercase tracking-[0.22em] text-muted mt-1">Tú</div>
      </div>
    );
  }

  // assistant — bubbleless cinematic prose con markdown
  return (
    <div className="self-start max-w-[90%] animate-fade-in-up">
      <div className="flex items-center gap-2 mb-1.5">
        <span className="relative inline-grid place-items-center h-5 w-5 rounded-full bg-pri/15">
          <span className="absolute inset-0 rounded-full bg-pri/30 blur-[6px]" />
          <span className="relative h-2 w-2 rounded-full bg-pri" />
        </span>
        <span className="text-[10px] uppercase tracking-[0.22em] text-pri/90 font-medium">Orion</span>
      </div>
      <div className="relative">
        <Markdown source={msg.text} />
        {isLastAssistant && <StreamCaret />}
      </div>
    </div>
  );
}

function StreamCaret() {
  return (
    <span className="inline-block w-[6px] h-[1.05em] -mb-[2px] ml-[2px] bg-pri/80 animate-caret align-middle" />
  );
}

function TypingDots() {
  return (
    <div className="self-start flex items-center gap-2 animate-fade-in">
      <span className="relative inline-grid place-items-center h-5 w-5 rounded-full bg-pri/15">
        <span className="absolute inset-0 rounded-full bg-pri/30 blur-[6px]" />
        <span className="relative h-2 w-2 rounded-full bg-pri" />
      </span>
      <span className="flex items-center gap-1.5">
        <Dot delay="0s" />
        <Dot delay="0.18s" />
        <Dot delay="0.36s" />
      </span>
    </div>
  );
}
function Dot({ delay }: { delay: string }) {
  return (
    <span
      className="block h-1.5 w-1.5 rounded-full bg-pri/80 animate-pulse-soft"
      style={{ animationDelay: delay }}
    />
  );
}

/* ─── COMPOSER ────────────────────────────────────────────────────── */
function Composer({
  taRef, draft, onChange, onSubmit, currentFile,
}: {
  taRef: React.MutableRefObject<HTMLTextAreaElement | null>;
  draft: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  currentFile: string | null;
}) {
  const has = draft.trim().length > 0;

  return (
    <div className="border-t border-white/[0.06] bg-bg/80 backdrop-blur-md">
      {/* attachment lane */}
      {currentFile && (
        <div className="px-4 pt-3 animate-fade-in-up">
          <AttachmentChip />
        </div>
      )}

      <div className="mx-auto max-w-3xl px-4 md:px-8 py-3">
        <div className="group relative rounded-2xl border border-white/[0.08] bg-elevated/60
                        focus-within:border-pri/40 focus-within:shadow-glow-soft
                        transition-all duration-200 ease-out-expo">
          <textarea
            ref={taRef}
            value={draft}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onSubmit();
              }
            }}
            placeholder="Pregúntale a Orion…"
            rows={1}
            className="block w-full resize-none bg-transparent rounded-2xl
                       px-4 pt-3 pb-12 text-[15px] leading-relaxed placeholder-muted
                       focus:outline-none"
          />

          <div className="absolute left-3 right-3 bottom-2.5 flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              {!currentFile && <AttachmentChip />}
              <span className="text-[10px] uppercase tracking-[0.18em] text-muted hidden sm:inline">
                <Kbd>Enter</Kbd> enviar · <Kbd>Shift</Kbd>+<Kbd>↵</Kbd> nueva línea
              </span>
            </div>
            <Button
              variant={has ? "primary" : "secondary"}
              size="sm"
              icon="send"
              onClick={onSubmit}
              disabled={!has}
            >
              Enviar
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
