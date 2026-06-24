/**
 * ChatPanel — the core AI conversation surface.
 *
 * Two presentations:
 *   - Empty hero (no real user/IA turns yet): clean composition with a
 *     state-tinted status pill, big greeting, and 4 prompt suggestions.
 *     The BackgroundEye stays hidden in this state — solo aparece tras
 *     el primer turno real.
 *   - Conversation: messages stream into a focused timeline; the BG eye
 *     fade-in detrás. Each message animates in with fade-in-up;
 *     assistant turns are bubbleless prose, user turns are aligned
 *     chips, file/system are timeline rows.
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

import { AskUserPrompt } from "@/components/AskUserPrompt";
import { AttachmentChip } from "@/components/AttachmentChip";
import { OrbHUD } from "@/components/OrbHUD";
import { ToolBanner } from "@/components/ToolBanner";
import { Markdown } from "@/lib/markdown";
import { prettyToolName } from "@/lib/toolLabels";
import { useInteractionStore } from "@/stores/interaction";
import { useOrionStore } from "@/stores/orion";
import type { ChatMessage, LogRole } from "@/types";
import { Icon, type IconName } from "@/ui/Icon";
import { Button, Kbd } from "@/ui/primitives";
import { useEyeState } from "@/widgets/eye";

// BRIEF · Conversación: cada categoría con un acento de color propio
// (Sistema=azul de marca, Memoria=violeta, Hogar=verde, Agentes=ámbar).
// El token CSS lo resuelve el render (var() inline) para que respete
// el override del tema activo del usuario.
const SUGGESTIONS: { eyebrow: string; prompt: string; identity: string; icon: IconName }[] = [
  {
    eyebrow: "Sistema",
    prompt: "¿Cómo está el sistema ahora mismo?",
    identity: "--orion-pri",
    icon: "telemetry",
  },
  {
    eyebrow: "Memoria",
    prompt: "Recuérdame mis proyectos activos.",
    identity: "--agent-analyst",
    icon: "memory",
  },
  {
    eyebrow: "Hogar",
    prompt: "Pon una escena tranquila en el salón.",
    identity: "--sem-success",
    icon: "iot",
  },
  {
    eyebrow: "Agentes",
    prompt: "Lanza una tarea para resumir mis notas.",
    identity: "--agent-writer",
    icon: "agents",
  },
];

interface Props {
  /** Raw WS sender — acepta cualquier type/payload. ChatPanel lo usa
   *  para `text`, AskUserPrompt para `ask_user.response/cancel`. */
  send: (type: string, payload?: Record<string, unknown>) => void;
}

export function ChatPanel({ send }: Props) {
  const messages = useOrionStore((s) => s.messages);
  const pushLocal = useOrionStore((s) => s.pushLocalUserText);
  const clearMsgs = useOrionStore((s) => s.clear);
  const state = useOrionStore((s) => s.state);
  const currentFile = useOrionStore((s) => s.currentFile);
  const eyeState = useEyeState();
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const taRef = useRef<HTMLTextAreaElement | null>(null);

  // Pre-fill desde el quick input del HomePanel (si el usuario escribió
  // algo allí y dio Enter, lo dejamos cargado y enfocado acá).
  useEffect(() => {
    const stashed = window.localStorage.getItem("orion.chat.draft");
    if (stashed) {
      setDraft(stashed);
      window.localStorage.removeItem("orion.chat.draft");
      window.setTimeout(() => taRef.current?.focus(), 20);
    }
  }, []);

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
    send("text", { text: t });
    setDraft("");
  }

  // El Hero solo desaparece cuando hay un turno REAL (usuario o IA). Los
  // mensajes de sistema/archivo/error que el backend pushea al conectar
  // ("SISTEMA: ORION en línea.", "Reconectando…", etc.) no cuentan — antes
  // sí contaban, y el Hero se "cerraba" solo sin que el usuario hubiera
  // hablado, dejando un timeline vacío.
  const empty = !messages.some((m) => m.role === "user" || m.role === "ai");

  return (
    <div className="flex flex-col h-full relative">
      {/* ambient atmosphere when empty */}
      {empty && <div className="pointer-events-none absolute inset-0 bg-dots opacity-50" />}

      {/* tool / agent activity banner — solo cuando hay actividad real */}
      <ToolBanner />

      {/* messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-thin">
        {empty ? (
          <Hero
            onPick={(p) => {
              setDraft(p);
              taRef.current?.focus();
            }}
          />
        ) : (
          <Timeline messages={messages} state={state} eyeState={eyeState} onNew={clearMsgs} />
        )}
      </div>

      {/* Pregunta interactiva del agente — solo aparece si hay una
          ask_user pendiente (researcher pidiendo clarificación, etc). */}
      <AskUserPrompt send={send} />

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

/* ─── HERO (empty state) ──────────────────────────────────────────────
   El ojo cinemático va arriba como centerpiece (igual que Inicio) con un
   halo ambiental detrás. Bajo el ojo: greeting + sugerencias. El
   BackgroundEye gigante sigue oculto en este estado — solo aparece tras
   el primer turno. Vista estable: no se cierra sola con mensajes de
   sistema, no parpadea. */
function Hero({ onPick }: { onPick: (p: string) => void }) {
  const eyeState = useEyeState();
  const listening = eyeState === "listening";
  const responding = eyeState === "speaking";
  // El Hero ya vive dentro de un scroll container del ChatPanel. NO
  // anidamos otro scroll acá: usábamos `h-full overflow-y-auto` +
  // `min-h-full + justify-center` y cuando la suma de eye + greeting +
  // 4 suggestions + spacer excedía el viewport, justify-center cortaba
  // contenido equitativamente arriba y abajo — las suggestions quedaban
  // ocultas detrás del composer. Ahora dejamos que el padre haga el
  // scroll y nos posicionamos top-aligned con padding razonable.
  return (
    <div className="min-h-full flex flex-col items-center px-6 pt-12 pb-6 animate-fade-in">
      {/* OJO centerpiece. Halo radial detrás + onda de audio reactiva
          debajo cuando ORION está escuchando o respondiendo (brief). */}
      <div className="relative flex flex-col items-center">
        <div
          className="absolute top-0 left-1/2 -translate-x-1/2 h-56 w-56 rounded-full
                        bg-[radial-gradient(circle,rgb(var(--orion-pri-glow)/0.18),transparent_70%)]
                        blur-3xl pointer-events-none animate-halo"
        />
        <OrbHUD />
        <AudioWave
          active={listening || responding}
          variant={responding ? "speaking" : "listening"}
        />
      </div>

      <h1 className="mt-6 text-3xl md:text-[34px] font-semibold tracking-tight text-text text-center max-w-2xl leading-[1.15] animate-fade-in-up">
        ¿En qué te ayudo hoy?
      </h1>
      <p
        className="mt-2 text-sm text-text-dim text-center max-w-md leading-relaxed animate-fade-in-up"
        style={{ animationDelay: "80ms" }}
      >
        Háblame en voz alta o escribí abajo.
      </p>

      <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-2.5 w-full max-w-2xl">
        {SUGGESTIONS.map((s, i) => {
          // BRIEF · Conversación: la card lleva su categoría como
          // identidad visual — eyebrow + icon + halo de hover en el
          // color asignado. El border-left fino comunica jerarquía sin
          // gritar (translation Y + ring de color al hover).
          const rgb = `rgb(var(${s.identity}))`;
          const rgbAlpha = (a: number) => `rgb(var(${s.identity}) / ${a})`;
          return (
            <button
              key={s.prompt}
              onClick={() => onPick(s.prompt)}
              style={{
                animationDelay: `${160 + 80 * i}ms`,
                borderLeft: `2px solid ${rgbAlpha(0.55)}`,
              }}
              className="group relative text-left rounded-lg surface-1 px-4 py-3
                         hover:border-white/[0.12] hover:bg-elevated/70
                         hover:-translate-y-0.5
                         transition-all duration-200 ease-out-expo
                         animate-fade-in-up"
            >
              <div className="flex items-center gap-2">
                <span
                  className="grid place-items-center h-5 w-5 rounded-md transition-colors"
                  style={{
                    background: rgbAlpha(0.13),
                    color: rgb,
                    border: `1px solid ${rgbAlpha(0.3)}`,
                  }}
                >
                  <Icon name={s.icon} size={11} />
                </span>
                <div
                  className="text-[10px] uppercase tracking-[0.22em] font-mono"
                  style={{ color: rgbAlpha(0.85) }}
                >
                  {s.eyebrow}
                </div>
              </div>
              <div className="mt-1.5 text-sm text-text leading-snug pr-6">{s.prompt}</div>
              <Icon
                name="chevron-right"
                size={14}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted
                           opacity-0 group-hover:opacity-100 group-hover:translate-x-0.5
                           transition-all duration-200"
              />
              {/* halo del hover en el color de identidad */}
              <span
                aria-hidden
                className="absolute inset-0 rounded-lg opacity-0 group-hover:opacity-100
                           transition-opacity duration-300 pointer-events-none"
                style={{ boxShadow: `0 8px 24px -12px ${rgbAlpha(0.55)}` }}
              />
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ─── AUDIO WAVE ─────────────────────────────────────────────────────
   Onda de barras CSS-animated. Reacciona al estado del Ojo:
     · listening → barras corren más rápido y vivas (cyan claro)
     · speaking  → barras más amplias y verdosas (sem-live)
     · inactivo  → render NULL (no ocupa espacio)
   No usa Web Audio API porque el volumen del mic real lo maneja el
   backend (Gemini Live). Es una visualización indicativa, no una
   medición. Cada barra tiene su propio delay y duración para que el
   patrón no se vea sincronizado/mecánico. */
const WAVE_BARS = [
  { d: 1100, delay: 0 },
  { d: 950, delay: 120 },
  { d: 1300, delay: 80 },
  { d: 850, delay: 200 },
  { d: 1180, delay: 40 },
  { d: 1000, delay: 260 },
  { d: 920, delay: 160 },
  { d: 1240, delay: 100 },
  { d: 880, delay: 300 },
  { d: 1080, delay: 60 },
  { d: 1160, delay: 220 },
  { d: 990, delay: 140 },
];

function AudioWave({ active, variant }: { active: boolean; variant: "listening" | "speaking" }) {
  if (!active) return null;
  // BRIEF · Conversación: la onda usa el color del tema (listening) o
  // sem-live (speaking). Antes el listening estaba hardcoded a cian
  // — al picar un tema distinto, el Ojo cambiaba pero la onda no.
  const color = variant === "speaking" ? "rgb(var(--sem-live))" : "rgb(var(--orion-pri))";
  const glow =
    variant === "speaking" ? "rgb(var(--sem-live) / 0.5)" : "rgb(var(--orion-pri) / 0.5)";
  return (
    <div className="mt-4 flex items-end justify-center gap-1 h-10 animate-fade-in-up" aria-hidden>
      {WAVE_BARS.map((b, i) => (
        <span
          key={i}
          className="w-1 rounded-full origin-bottom"
          style={{
            height: "100%",
            background: color,
            boxShadow: `0 0 8px ${glow}`,
            animation: `wave ${b.d}ms ease-in-out ${b.delay}ms infinite`,
          }}
        />
      ))}
    </div>
  );
}

/* ─── TIMELINE ────────────────────────────────────────────────────── */
function Timeline({
  messages,
  state,
  eyeState,
  onNew,
}: {
  messages: ChatMessage[];
  state: string;
  eyeState: ReturnType<typeof useEyeState>;
  /** Limpia la conversación y vuelve al Hero. */
  onNew: () => void;
}) {
  const stateLabel =
    eyeState === "listening"
      ? "escuchando"
      : eyeState === "thinking"
        ? "procesando"
        : eyeState === "speaking"
          ? "hablando"
          : eyeState === "error"
            ? "error"
            : state.toLowerCase();

  return (
    <div className="mx-auto max-w-3xl px-4 md:px-8 py-6 flex flex-col gap-5">
      {/* status row HUD — dot teñido del color del estado actual, monospace,
          tracking ancho. Sticky para que sobreviva al scroll. */}
      <div
        className="sticky top-0 z-10 -mx-4 md:-mx-8 px-4 md:px-8 py-2
                      backdrop-blur-md bg-bg/40 border-b border-white/[0.04]
                      flex items-center gap-2 text-[10px] uppercase tracking-[0.24em]
                      text-text-dim font-mono"
      >
        <span
          className="h-1.5 w-1.5 rounded-full animate-pulse-soft"
          style={{
            background: "rgb(var(--orion-state-rgb))",
            boxShadow: "0 0 10px rgb(var(--orion-state-rgb) / 0.7)",
          }}
        />
        <span>Sesión activa</span>
        <span className="text-muted">·</span>
        <span style={{ color: "rgb(var(--orion-state-rgb) / 0.95)" }}>{stateLabel}</span>
        {/* Nueva conversación — limpia el historial local. No pide
            confirmación porque los mensajes se persisten server-side
            (history panel) y un click accidental no destruye nada. */}
        <button
          onClick={onNew}
          title="Limpiar y empezar una nueva conversación"
          className="ml-auto inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md
                     border border-white/[0.08] bg-white/[0.03]
                     text-[10px] uppercase tracking-[0.18em] text-text-dim
                     hover:text-text hover:border-pri/40 hover:bg-pri/[0.06]
                     transition-all duration-150"
        >
          <Icon name="plus" size={11} />
          <span>Nueva</span>
        </button>
      </div>

      {messages.map((m, i) => (
        <MessageRow
          key={m.id}
          msg={m}
          isLastAssistant={m.role === "ai" && !messages.slice(i + 1).some((x) => x.role === "ai")}
        />
      ))}

      {/* Indicador inline: aparece cuando el último mensaje es del usuario
          y aún no llegó respuesta de la IA. Muestra texto contextual
          según lo que esté pasando (tool activa, agente, o "Pensando").
          Antes solo aparecía si state === "PENSANDO", pero ese state
          únicamente se setea por eventos de audio Live — para input de
          texto nunca se gatillaba y el usuario veía silencio. */}
      {(() => {
        const last = messages[messages.length - 1];
        const awaiting =
          last?.role === "user" || (last?.role === "ai" && last.streaming && !last.text.trim());
        return awaiting ? <ThinkingIndicator /> : null;
      })()}
    </div>
  );
}

/* ─── INDICADOR CONTEXTUAL "PENSANDO / BUSCANDO…" ─────────────────── */
function ThinkingIndicator() {
  const tool = useInteractionStore((s) => s.tool);
  const agent = useInteractionStore((s) => s.agent);

  // Prioridad de contenido:
  //   1) tool activa → label específica ("Buscando en la web", etc)
  //   2) agente con tarea → "Agente: <goal corto>" o lastSpeech
  //   3) fallback genérico → "Pensando"
  let icon = "";
  let label = "Pensando";
  let sub: string | null = null;

  if (tool) {
    const p = prettyToolName(tool.name);
    icon = p.icon;
    label = p.label;
    // Args principales (1-2) como subtexto
    const argEntries = Object.entries(tool.args).slice(0, 2);
    if (argEntries.length) {
      sub = argEntries.map(([, v]) => String(v).slice(0, 60)).join(" · ");
    }
  } else if (agent && (agent.status === "running" || agent.status === "pending")) {
    icon = "🎼";
    label = agent.status === "pending" ? "Agente en cola" : "Agente trabajando";
    sub = agent.lastSpeech ?? agent.goal ?? null;
    if (sub && sub.length > 90) sub = sub.slice(0, 90) + "…";
  }

  return (
    <div className="self-start max-w-[90%] animate-fade-in">
      <div className="flex items-center gap-2 mb-1.5">
        <span className="relative inline-grid place-items-center h-5 w-5 rounded-full bg-pri/15">
          <span className="absolute inset-0 rounded-full bg-pri/30 blur-[6px] animate-pulse-soft" />
          <span className="relative h-2 w-2 rounded-full bg-pri" />
        </span>
        <span className="text-[10px] uppercase tracking-[0.22em] text-pri/90 font-medium">
          Orion
        </span>
      </div>
      <div
        className="flex items-start gap-3 px-4 py-3 rounded-xl
                      border border-pri/25 bg-pri/[0.06] backdrop-blur-sm
                      shadow-[0_0_24px_-8px_rgb(var(--orion-pri-glow)/0.35)]"
      >
        {icon && <span className="text-xl leading-none mt-0.5">{icon}</span>}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2.5 text-[15px] text-text font-medium">
            <span>{label}</span>
            <span className="flex items-center gap-1">
              <Dot delay="0s" />
              <Dot delay="0.18s" />
              <Dot delay="0.36s" />
            </span>
          </div>
          {sub && <div className="mt-1 text-[12px] text-text-dim font-mono truncate">{sub}</div>}
        </div>
      </div>
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
        <span className="text-[10px] uppercase tracking-[0.22em] text-pri/90 font-medium">
          Orion
        </span>
      </div>
      <div className="relative">
        <Markdown source={msg.text} />
        {/* Caret solo mientras el mensaje está siendo streameado. Antes
            quedaba pegado al último mensaje de IA aunque ya hubiera
            terminado, generando un parpadeo permanente. */}
        {isLastAssistant && msg.streaming && <StreamCaret />}
      </div>
    </div>
  );
}

function StreamCaret() {
  return (
    <span className="inline-block w-[6px] h-[1.05em] -mb-[2px] ml-[2px] bg-pri/80 animate-caret align-middle" />
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
  taRef,
  draft,
  onChange,
  onSubmit,
  currentFile,
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
        <div
          className="group relative rounded-2xl border border-white/[0.08] bg-elevated/60
                        focus-within:border-pri/40 focus-within:shadow-glow-soft
                        transition-all duration-200 ease-out-expo"
        >
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
