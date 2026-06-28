/**
 * HomePanel — dashboard "neural core" de Orion.
 *
 * Estructura:
 *   [ MAIN (flex-1)                     | SIDE-RAIL 340px         ]
 *   [ orb central                                                  ]
 *   [ saludo + "Neural core estable"   | Actividad en Vivo        ]
 *   [ input rápido → chat              | Telemetría del sistema   ]
 *   [ 5 quick actions                  | Estado de la red         ]
 *                                       | Eventos del sistema
 *
 * Todos los datos vivos vienen de stores existentes — no hace fetch
 * extra. Sólo reorganiza la información que ya circula por la app.
 */

import { useEffect, useState } from "react";

import { OrbHUD } from "@/components/OrbHUD";
import { api, type NotifItem } from "@/api/rest";
import { sourceMeta, stripLeadingEmoji, formatRelative } from "@/lib/notificationSource";
import { useInteractionStore } from "@/stores/interaction";
import { useOrionStore } from "@/stores/orion";
import { useViewStore } from "@/stores/view";
import { Icon, type IconName } from "@/ui/Icon";

function greet(): string {
  const h = new Date().getHours();
  if (h < 5) return "Buenas noches";
  if (h < 12) return "Buenos días";
  if (h < 19) return "Buenas tardes";
  return "Buenas noches";
}

export function HomePanel() {
  const setView = useViewStore((s) => s.setView);
  const tlast = useOrionStore((s) => s.telemetry.last);
  // Sólo necesitamos el conteo — leer el objeto completo dispararía un
  // re-render de HomePanel cada vez que cualquier sensor reporta, aunque
  // la lista de devices no haya cambiado. Selector que devuelve un número
  // → Zustand sólo re-renderea cuando el número cambia.
  const sensorCount = useOrionStore((s) => Object.keys(s.iotSensors).length);
  const unread = useOrionStore((s) => s.unreadNotifs);
  const muted = useOrionStore((s) => s.muted);
  const connected = useOrionStore((s) => s.connected);
  const activeTool = useInteractionStore((s) => s.tool);
  const activeAgent = useInteractionStore((s) => s.agent);

  const [notifs, setNotifs] = useState<NotifItem[]>([]);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    let alive = true;
    api.listNotifications().then((n) => {
      if (alive) setNotifs(n.slice(0, 6));
    });
    return () => {
      alive = false;
    };
  }, []);

  function submitDraft() {
    const text = draft.trim();
    if (!text) {
      setView("chat");
      return;
    }
    // Stash en localStorage para que el ChatPanel lo pre-rellene al montar.
    window.localStorage.setItem("orion.chat.draft", text);
    setView("chat");
  }

  return (
    <div className="h-full overflow-y-auto scrollbar-thin">
      <div className="mx-auto max-w-[1500px] px-6 py-6 grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_340px] gap-6">
        {/* ═══════ MAIN COLUMN ═══════ */}
        <div className="min-w-0 flex flex-col items-center">
          {/* Hero: orb central limpio (sin nodos orbitales). El orb ya
              comunica el estado de Orion; los accesos a Memoria/IoT/
              Sistema/Agentes están en el sidebar y en las quick actions. */}
          <div className="relative grid place-items-center">
            <OrbHUD />
          </div>

          {/* Greeting — BRIEF Inicio: drama tipográfico real.
              Línea 1 ("Buenas tardes") en orion-display 38px weight 300.
              Línea 2 ("estoy operativo") en body 14px muted, como pulso
              continuo del sistema. Sin agruparlas en el mismo nodo, sino
              dos roles claramente jerárquicos. */}
          <h1 className="orion-display mt-3 text-center animate-fade-in-up">{greet()}</h1>
          {!muted && (
            <p
              className="orion-body text-text-dim/85 mt-1 text-center animate-fade-in-up"
              style={{ animationDelay: "60ms" }}
            >
              estoy operativo
            </p>
          )}
          <div
            className="mt-3 flex items-center gap-2 text-[10px] uppercase tracking-[0.28em] animate-fade-in-up"
            style={{ animationDelay: "120ms" }}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-sem-live shadow-[0_0_8px_rgb(var(--sem-live))] animate-pulse" : "bg-muted"}`}
            />
            <span className={connected ? "text-sem-live/90" : "text-muted"}>
              {connected ? "Neural core estable" : "Reconectando…"}
            </span>
          </div>

          {/* Search / quick chat input */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              submitDraft();
            }}
            className="mt-6 w-full max-w-xl flex items-center gap-2 px-4 py-3
                       rounded-2xl border border-white/[0.08] bg-elevated/60 backdrop-blur-md
                       focus-within:border-pri/40 focus-within:shadow-glow-soft transition-all"
          >
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="¿Qué deseas hacer hoy?"
              className="flex-1 bg-transparent text-sm placeholder-muted focus:outline-none text-text"
            />
            <button
              type="submit"
              className="grid place-items-center h-8 w-8 rounded-lg bg-pri text-bg
                               hover:brightness-110 transition-all"
            >
              <Icon name="play" size={14} />
            </button>
          </form>

          {/* Quick actions (5 cards) */}
          <section className="mt-8 w-full max-w-4xl">
            <SectionEyebrow>Acciones rápidas</SectionEyebrow>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
              <QuickAction
                icon="chat"
                label="Conversar"
                hint="Habla con Orion"
                onClick={() => setView("chat")}
                accent="pri"
              />
              <QuickAction
                icon="agents"
                label="Lanzar agente"
                hint="Ejecuta un agente"
                onClick={() => setView("agents")}
                accent="acc"
              />
              <QuickAction
                icon="iot"
                label="Casa"
                hint="Luces y sensores"
                onClick={() => setView("iot")}
                accent="ok"
              />
              <QuickAction
                icon="notes"
                label="Notas"
                hint="Captura ideas"
                onClick={() => setView("notes")}
                accent="warn"
              />
              <QuickAction
                icon="sparkles"
                label="Skills"
                hint="Descubre habilidades"
                onClick={() => setView("skills")}
                accent="acc"
              />
            </div>
          </section>

          <div className="h-4" />
        </div>

        {/* ═══════ SIDE-RAIL ═══════ */}
        <aside className="flex flex-col gap-4 min-w-0">
          <ActivityLiveCard tool={activeTool} agent={activeAgent} onSee={() => setView("agents")} />
          <TelemetryCard
            tlast={tlast}
            sensorCount={sensorCount}
            agentRunning={activeAgent?.status === "running"}
            onSee={() => setView("telemetry")}
          />
          <NetworkCard connected={connected} />
          <EventsCard notifs={notifs} unread={unread} onSee={() => setView("notifications")} />
        </aside>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   SIDE-RAIL CARDS
   ═══════════════════════════════════════════════════════════════════ */

function ActivityLiveCard({
  tool,
  agent,
  onSee,
}: {
  tool: ReturnType<typeof useInteractionStore.getState>["tool"];
  agent: ReturnType<typeof useInteractionStore.getState>["agent"];
  onSee: () => void;
}) {
  const entries: { icon: IconName; label: string; sub: string; tone: string }[] = [];
  if (tool)
    entries.push({ icon: "bolt", label: "Tool en curso", sub: tool.name, tone: "text-pri" });
  if (agent)
    entries.push({
      icon: "agents",
      label: agent.status === "running" ? "Agente activo" : agent.status,
      sub: agent.goal || agent.taskId || "—",
      tone: "text-acc",
    });

  return (
    <RailCard title="Actividad en vivo" icon="bolt" onSee={onSee} seeLabel="Ver agentes →">
      {entries.length === 0 ? (
        <p className="text-[11px] text-text-dim italic">
          Sistema en reposo. Esperando próxima orden.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {entries.map((e, i) => (
            <div
              key={i}
              className="flex items-start gap-2.5 px-2.5 py-2 rounded-md bg-white/[0.03] border border-white/[0.06]"
            >
              <span
                className={`grid place-items-center h-7 w-7 rounded-md bg-white/[0.04] ${e.tone} shrink-0`}
              >
                <Icon name={e.icon} size={13} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-[11px] text-text font-medium truncate">{e.label}</div>
                <div className="text-[10px] text-text-dim truncate">{e.sub}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </RailCard>
  );
}

function TelemetryCard({
  tlast,
  sensorCount,
  agentRunning,
  onSee,
}: {
  tlast: { cpu: number; ram: number; disk: number; ts: number } | null;
  sensorCount: number;
  agentRunning: boolean;
  onSee: () => void;
}) {
  // BRIEF Inicio · Telemetría como instrumentos de cockpit:
  //   · CPU/Memoria/Disco como diales circulares en una fila (tres
  //     luminosidades del MISMO acento — sem-data-{a,b,c}).
  //   · Agentes / Nodos IoT como métricas operativas debajo en
  //     barras (serie aparte, no se confunde con las del sistema).
  const dials = [
    { label: "CPU", pct: tlast ? Math.round(tlast.cpu * 100) : null, tone: "data-a" as const },
    { label: "Memoria", pct: tlast ? Math.round(tlast.ram * 100) : null, tone: "data-b" as const },
    { label: "Disco", pct: tlast ? Math.round(tlast.disk * 100) : null, tone: "data-c" as const },
  ];
  const bars = [
    {
      label: "Agentes",
      pct: agentRunning ? 100 : 0,
      tone: "live" as const,
      readout: agentRunning ? "1 activo" : "0 activos",
    },
    {
      label: "Nodos IoT",
      pct: Math.min(100, sensorCount * 20),
      tone: "acc" as const,
      readout: `${sensorCount} online`,
    },
  ];
  return (
    <RailCard title="Telemetría del sistema" icon="telemetry" onSee={onSee} seeLabel="Detalle →">
      <div className="flex items-end justify-between gap-2 mb-3">
        {dials.map((d) => (
          <TelemetryDial key={d.label} {...d} />
        ))}
      </div>
      <div className="h-px bg-white/[0.04] mb-3" />
      <div className="flex flex-col gap-2.5">
        {bars.map((b) => (
          <TelemetryBar key={b.label} {...b} />
        ))}
      </div>
    </RailCard>
  );
}

/* ── TelemetryDial — gauge circular SVG estilo cockpit ─────────────
   Anillo de fondo + anillo de progreso animado + número grande y
   monoespaciado en el centro. El stroke ocupa 270° (de -135° a +135°)
   dejando un hueco abajo — más legible que un círculo completo y se
   lee como velocímetro. */
function TelemetryDial({
  label,
  pct,
  tone,
}: {
  label: string;
  pct: number | null;
  tone: "data-a" | "data-b" | "data-c" | "live" | "acc";
}) {
  const SIZE = 78;
  const STROKE = 5;
  const R = (SIZE - STROKE) / 2;
  const ARC_LEN = R * Math.PI * 1.5; // 270°
  const value = pct == null ? 0 : Math.max(0, Math.min(100, pct));
  const offset = ARC_LEN * (1 - value / 100);
  const colorVar =
    tone === "data-a"
      ? "var(--sem-data-a)"
      : tone === "data-b"
        ? "var(--sem-data-b)"
        : tone === "data-c"
          ? "var(--sem-data-c)"
          : tone === "live"
            ? "var(--sem-live)"
            : "var(--orion-acc)";
  return (
    <div className="flex flex-col items-center gap-1 min-w-0 flex-1">
      <div className="relative" style={{ width: SIZE, height: SIZE }}>
        <svg
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          className="absolute inset-0"
          style={{ transform: "rotate(135deg)" }}
        >
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={R}
            fill="none"
            stroke="rgb(var(--orion-border) / 0.08)"
            strokeWidth={STROKE}
            strokeDasharray={`${ARC_LEN} ${R * 2 * Math.PI}`}
            strokeLinecap="round"
          />
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={R}
            fill="none"
            stroke={`rgb(${colorVar})`}
            strokeWidth={STROKE}
            strokeDasharray={`${ARC_LEN} ${R * 2 * Math.PI}`}
            strokeDashoffset={offset}
            strokeLinecap="round"
            style={{
              transition: "stroke-dashoffset 600ms cubic-bezier(0.22, 1, 0.36, 1)",
              filter: `drop-shadow(0 0 6px rgb(${colorVar} / 0.5))`,
            }}
          />
        </svg>
        <div className="absolute inset-0 grid place-items-center text-center">
          <div>
            <div
              className="orion-mono text-[18px] font-semibold leading-none"
              style={{ color: `rgb(${colorVar})` }}
            >
              {pct == null ? "—" : pct}
              <span className="text-[10px] text-text-dim/80 ml-0.5 font-mono">%</span>
            </div>
          </div>
        </div>
      </div>
      <div className="text-[9px] uppercase tracking-[0.18em] text-text-dim font-medium">
        {label}
      </div>
    </div>
  );
}

function TelemetryBar({
  label,
  pct,
  tone,
  readout,
}: {
  label: string;
  pct: number;
  tone: "live" | "acc";
  readout: string;
}) {
  const colorClass = tone === "live" ? "bg-sem-live" : "bg-acc";
  return (
    <div>
      <div className="flex items-baseline justify-between text-[10px] uppercase tracking-[0.16em] mb-1">
        <span className="text-text-dim">{label}</span>
        <span className="text-text font-mono tabular-nums">{readout}</span>
      </div>
      <div className="h-1 rounded-full bg-white/[0.04] overflow-hidden">
        <div
          className={`h-full ${colorClass} rounded-full transition-all duration-500`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function NetworkCard({ connected }: { connected: boolean }) {
  const pct = connected ? 98 : 0;
  return (
    <RailCard title="Estado de la red" icon="bolt">
      <div className="flex items-center gap-4">
        <div className="relative grid place-items-center h-16 w-16">
          <svg viewBox="0 0 64 64" className="absolute inset-0 -rotate-90">
            <circle
              cx="32"
              cy="32"
              r="26"
              fill="none"
              stroke="rgb(var(--orion-pri) / 0.12)"
              strokeWidth="4"
            />
            <circle
              cx="32"
              cy="32"
              r="26"
              fill="none"
              stroke="rgb(var(--orion-pri))"
              strokeWidth="4"
              strokeLinecap="round"
              strokeDasharray={`${(pct / 100) * 163} 163`}
              style={{ transition: "stroke-dasharray 600ms ease" }}
            />
          </svg>
          <div className="text-[14px] font-mono tabular-nums text-text font-semibold">{pct}%</div>
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[11px] text-text font-medium">
            {connected ? "Conectado" : "Sin conexión"}
          </div>
          <div className="text-[10px] text-text-dim mt-0.5">
            {connected ? "Backend WS estable · sin pérdidas" : "Reintentando handshake…"}
          </div>
        </div>
      </div>
    </RailCard>
  );
}

function EventsCard({
  notifs,
  unread,
  onSee,
}: {
  notifs: NotifItem[];
  unread: number;
  onSee: () => void;
}) {
  const items = notifs.slice(0, 3);
  return (
    <RailCard
      title="Eventos del sistema"
      icon="bell"
      badge={unread > 0 ? `${unread}` : undefined}
      onSee={onSee}
      seeLabel="Ver todos →"
    >
      {items.length === 0 ? (
        <p className="text-[11px] text-text-dim italic">Sin eventos recientes.</p>
      ) : (
        <div className="flex flex-col gap-2">
          {items.map((n) => {
            const meta = sourceMeta(n.source);
            const title = stripLeadingEmoji(n.title);
            return (
              <div
                key={n.uid}
                className="flex items-start gap-2.5 px-2 py-1.5 rounded-md hover:bg-white/[0.04] transition-colors"
              >
                <img
                  src={meta.logo}
                  alt=""
                  width={20}
                  height={20}
                  loading="lazy"
                  decoding="async"
                  className="mt-0.5 shrink-0"
                />
                <div className="min-w-0 flex-1">
                  <div className="text-[11px] text-text font-medium truncate">{title}</div>
                  <div className="text-[10px] text-text-dim truncate">
                    {meta.label} · {formatRelative(n.received_ts)}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </RailCard>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   PRIMITIVOS LOCALES
   ═══════════════════════════════════════════════════════════════════ */

function RailCard({
  title,
  icon,
  children,
  onSee,
  seeLabel = "Ver →",
  badge,
}: {
  title: string;
  icon: IconName;
  children: React.ReactNode;
  onSee?: () => void;
  seeLabel?: string;
  badge?: string;
}) {
  return (
    <div className="relative rounded-xl border border-white/[0.07] surface-glass overflow-hidden">
      {/* HUD corner brackets en las 4 esquinas */}
      <span aria-hidden className="absolute top-0 left-0 h-2 w-2 border-t border-l border-pri/50" />
      <span
        aria-hidden
        className="absolute top-0 right-0 h-2 w-2 border-t border-r border-pri/50"
      />
      <span
        aria-hidden
        className="absolute bottom-0 left-0 h-2 w-2 border-b border-l border-pri/30"
      />
      <span
        aria-hidden
        className="absolute bottom-0 right-0 h-2 w-2 border-b border-r border-pri/30"
      />
      {/* línea horizontal sutil bajo el header */}
      <div className="p-4 relative">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 min-w-0">
            <span
              className="grid place-items-center h-6 w-6 rounded-md bg-pri/10 text-pri border border-pri/25
                             shadow-[inset_0_0_8px_rgb(var(--orion-pri-glow)/0.25)]"
            >
              <Icon name={icon} size={11} />
            </span>
            <h3 className="text-[10px] uppercase tracking-[0.24em] text-text font-semibold truncate">
              {title}
            </h3>
            {badge && (
              <span className="px-1.5 py-0.5 rounded-full bg-pri/20 text-pri text-[9px] font-mono tabular-nums shrink-0">
                {badge}
              </span>
            )}
          </div>
          {onSee && (
            <button
              onClick={onSee}
              className="text-[9px] uppercase tracking-[0.22em] text-pri/70 hover:text-pri transition-colors shrink-0"
            >
              {seeLabel}
            </button>
          )}
        </div>
        {/* divider bajo el header del card */}
        <div className="h-px bg-gradient-to-r from-pri/20 via-pri/5 to-transparent -mx-4 mb-3" />
        {children}
      </div>
    </div>
  );
}

function SectionEyebrow({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] uppercase tracking-[0.28em] text-pri/75 font-semibold mb-3 text-center">
      {children}
    </div>
  );
}

function QuickAction({
  icon,
  label,
  hint,
  onClick,
  accent,
}: {
  icon: IconName;
  label: string;
  hint: string;
  onClick: () => void;
  accent: "pri" | "acc" | "ok" | "warn";
}) {
  // CSS var per-accent → un sólo set de tokens, hover glow controlado.
  const accentVar =
    accent === "pri"
      ? "var(--orion-pri)"
      : accent === "acc"
        ? "var(--orion-acc)"
        : accent === "ok"
          ? "var(--orion-ok)"
          : "var(--orion-warn)";

  return (
    <button
      onClick={onClick}
      style={{ ["--qa-accent" as string]: accentVar }}
      className="group relative text-left rounded-xl overflow-hidden
                 border border-white/[0.06]
                 bg-[rgb(var(--orion-elevated)/0.55)] backdrop-blur-sm
                 transition-all duration-300 ease-spring
                 hover:border-[rgb(var(--qa-accent)/0.45)]
                 hover:bg-[rgb(var(--orion-elevated)/0.78)]
                 hover:-translate-y-1
                 hover:shadow-[0_18px_38px_-16px_rgb(var(--qa-accent)/0.65),0_0_0_1px_rgb(var(--qa-accent)/0.25)]
                 animate-fade-in-up"
    >
      {/* HUD corner brackets — top-left + bottom-right, brillan en hover */}
      <span
        aria-hidden
        className="absolute top-1.5 left-1.5 h-2 w-2 border-t border-l opacity-55 group-hover:opacity-100 transition-opacity"
        style={{ borderColor: `rgb(${accentVar})` }}
      />
      <span
        aria-hidden
        className="absolute bottom-1.5 right-1.5 h-2 w-2 border-b border-r opacity-55 group-hover:opacity-100 transition-opacity"
        style={{ borderColor: `rgb(${accentVar})` }}
      />

      {/* Sheen lateral al hover (tinte de color, no blanco) */}
      <span
        aria-hidden
        className="absolute inset-y-0 left-0 w-1 opacity-0 group-hover:opacity-100 transition-opacity duration-300"
        style={{ background: `linear-gradient(to right, rgb(${accentVar}/0.55), transparent)` }}
      />
      {/* Halo radial detrás del icono al hover */}
      <span
        aria-hidden
        className="absolute top-3 left-3 h-12 w-12 rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-300 blur-xl pointer-events-none"
        style={{ background: `radial-gradient(circle, rgb(${accentVar}/0.45), transparent 70%)` }}
      />

      <div className="relative p-4">
        <div className="flex items-start gap-3">
          <span
            className="grid place-items-center h-12 w-12 rounded-xl border transition-all duration-300
                       group-hover:scale-[1.06]"
            style={{
              backgroundColor: `rgb(${accentVar} / 0.15)`,
              borderColor: `rgb(${accentVar} / 0.38)`,
              color: `rgb(${accentVar})`,
              boxShadow: `inset 0 0 12px rgb(${accentVar}/0.14), 0 0 18px -6px rgb(${accentVar}/0.55)`,
            }}
          >
            <Icon name={icon} size={22} />
          </span>
          <div className="min-w-0 pt-0.5">
            <div className="text-sm font-semibold text-text truncate transition-colors leading-tight">
              {label}
            </div>
            <div className="text-[11px] text-text-dim/85 leading-snug mt-0.5">{hint}</div>
          </div>
        </div>
        {/* Línea HUD horizontal — pulsa de izq a der en hover */}
        <div className="mt-3.5 relative h-px overflow-hidden">
          <div
            className="absolute inset-0 transition-opacity duration-300 opacity-55 group-hover:opacity-100"
            style={{
              background: `linear-gradient(to right, rgb(${accentVar}/0.45), transparent 75%)`,
            }}
          />
        </div>
      </div>
    </button>
  );
}
