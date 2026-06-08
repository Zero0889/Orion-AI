/**
 * HomePanel — pantalla de inicio tipo dashboard.
 *
 * Reúne en una sola vista lo que está pasando AHORA en Orion:
 *   - OrbHUD grande con el estado actual
 *   - Saludo dinámico según hora del día
 *   - Tarjetas de quick-actions (chat / agente nuevo / IoT / nota)
 *   - Métricas live: telemetría CPU/RAM/disco, sensores favoritos
 *   - Lista breve de tareas de agentes en curso y notificaciones
 *
 * No reemplaza al chat — solo es la PRIMERA cosa que ves al abrir Orion.
 * Es la "página de inicio" que hace que el producto no parezca "otro
 * cliente de chat".
 */

import { useEffect, useMemo, useState } from "react";

import { OrbHUD } from "@/components/OrbHUD";
import { api, type NotifItem } from "@/api/rest";
import { useOrionStore } from "@/stores/orion";
import { useViewStore } from "@/stores/view";
import { Icon, type IconName } from "@/ui/Icon";
import { Surface } from "@/ui/primitives";

function greet(): string {
  const h = new Date().getHours();
  if (h < 5)  return "Buenas noches";
  if (h < 12) return "Buenos días";
  if (h < 19) return "Buenas tardes";
  return "Buenas noches";
}

export function HomePanel() {
  const setView = useViewStore((s) => s.setView);
  const tlast   = useOrionStore((s) => s.telemetry.last);
  const sensors = useOrionStore((s) => s.iotSensors);
  const unread  = useOrionStore((s) => s.unreadNotifs);
  const muted   = useOrionStore((s) => s.muted);

  const [notifs, setNotifs] = useState<NotifItem[]>([]);

  // Refresh cuando entras a Home — datos en vivo van por WS, pero la
  // primera vez necesitamos hidratar.
  useEffect(() => {
    let alive = true;
    api.listNotifications().then((n) => {
      if (alive) setNotifs(n.slice(0, 4));
    });
    return () => { alive = false; };
  }, []);

  const sensorList = useMemo(
    () => Object.entries(sensors).slice(0, 4),
    [sensors],
  );

  return (
    <div className="h-full overflow-y-auto scrollbar-thin">
      <div className="mx-auto max-w-5xl px-6 py-10">

        {/* Hero: orb + greeting with ambient background */}
        <div className="relative flex flex-col items-center text-center mb-12">
          {/* ambient halo behind orb */}
          <div className="absolute top-0 left-1/2 -translate-x-1/2 h-64 w-64 rounded-full
                          bg-[radial-gradient(circle,rgb(var(--orion-pri-glow)/0.18),transparent_70%)]
                          blur-3xl pointer-events-none animate-halo" />
          <OrbHUD />
          <h1 className="mt-8 text-3xl md:text-4xl font-semibold tracking-tight text-text animate-fade-in-up">
            {greet()}{muted ? "" : ", estoy operativo"}
          </h1>
          <p className="mt-2 text-sm text-text-dim max-w-md animate-fade-in-up" style={{ animationDelay: "100ms" }}>
            Pulsa <kbd className="px-1.5 py-0.5 rounded bg-white/[0.06] border border-white/[0.08] text-[10px]">⌘K</kbd>{" "}
            para buscar cualquier cosa, o elige debajo para empezar.
          </p>
        </div>

        {/* Quick actions */}
        <section className="mb-10">
          <SectionTitle>Comenzar</SectionTitle>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <QuickAction
              icon="chat"  label="Conversar"
              hint="Habla o escribe a Orion"
              onClick={() => setView("chat")}
            />
            <QuickAction
              icon="agents" label="Lanzar agente"
              hint="Investigar, escribir, calcular"
              onClick={() => setView("agents")}
            />
            <QuickAction
              icon="iot" label="Casa"
              hint="Luces, sensores, escenas"
              onClick={() => setView("iot")}
            />
            <QuickAction
              icon="notes" label="Notas rápidas"
              hint="Captura ideas al vuelo"
              onClick={() => setView("notes")}
            />
          </div>
        </section>

        {/* Telemetría + Sensores + Notificaciones */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-10">

          {/* Telemetría */}
          <Surface level={2} className="p-5 card-glow">
            <div className="flex items-center justify-between mb-4">
              <SectionTitle compact>Sistema</SectionTitle>
              <button
                onClick={() => setView("telemetry")}
                className="text-[10px] uppercase tracking-[0.22em] text-text-dim hover:text-text"
              >
                Ver detalle →
              </button>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <Metric label="CPU"    value={tlast?.cpu}  tone="pri" />
              <Metric label="RAM"    value={tlast?.ram}  tone="acc" />
              <Metric label="Disco"  value={tlast?.disk} tone="ok"  />
            </div>
            {!tlast && (
              <p className="mt-3 text-[10px] uppercase tracking-[0.2em] text-muted text-center">
                Esperando primer tick…
              </p>
            )}
          </Surface>

          {/* Sensores */}
          <Surface level={2} className="p-5 card-glow">
            <div className="flex items-center justify-between mb-4">
              <SectionTitle compact>Sensores</SectionTitle>
              <button
                onClick={() => setView("iot")}
                className="text-[10px] uppercase tracking-[0.22em] text-text-dim hover:text-text"
              >
                Panel IoT →
              </button>
            </div>
            {sensorList.length === 0 ? (
              <p className="text-sm text-text-dim italic">Sin lecturas todavía.</p>
            ) : (
              <div className="grid grid-cols-2 gap-3">
                {sensorList.map(([id, s]) => (
                  <div key={id} className="rounded-md border border-white/[0.06] bg-bg/40 px-3 py-2">
                    <div className="text-[10px] uppercase tracking-[0.22em] text-text-dim">{id}</div>
                    <div className="text-lg font-mono tabular-nums text-acc">{s.value}</div>
                  </div>
                ))}
              </div>
            )}
          </Surface>

          {/* Notificaciones */}
          <Surface level={2} className="p-5 card-glow">
            <div className="flex items-center justify-between mb-4">
              <SectionTitle compact>
                Notificaciones
                {unread > 0 && (
                  <span className="ml-2 px-1.5 py-0.5 rounded-full bg-pri/20 text-pri text-[10px] font-mono">
                    {unread}
                  </span>
                )}
              </SectionTitle>
              <button
                onClick={() => setView("notifications")}
                className="text-[10px] uppercase tracking-[0.22em] text-text-dim hover:text-text"
              >
                Ver todas →
              </button>
            </div>
            {notifs.length === 0 ? (
              <p className="text-sm text-text-dim italic">Sin notificaciones recientes.</p>
            ) : (
              <div className="space-y-2">
                {notifs.map((n) => (
                  <div key={n.uid} className="flex items-start gap-2 rounded-md px-2 py-1.5 hover:bg-white/[0.03]">
                    <span className="mt-1 h-1.5 w-1.5 rounded-full bg-acc shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="text-sm text-text truncate">{n.title}</div>
                      <div className="text-[11px] text-text-dim truncate">{n.source} · {new Date(n.received_ts * 1000).toLocaleTimeString()}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Surface>
        </div>
      </div>
    </div>
  );
}

/* ─── helpers ─────────────────────────────────────────────────────── */

function SectionTitle({ children, compact }: { children: React.ReactNode; compact?: boolean }) {
  return (
    <h3 className={`text-[10px] uppercase tracking-[0.28em] text-text-dim ${compact ? "" : "mb-3"} flex items-center`}>
      {children}
    </h3>
  );
}

function QuickAction({
  icon, label, hint, onClick,
}: {
  icon:    IconName;
  label:   string;
  hint:    string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="group relative text-left rounded-xl border border-white/[0.06]
                 surface-glass hover-lift p-4 animate-fade-in-up"
    >
      <div className="flex items-center gap-3 mb-1">
        <span className="grid place-items-center h-9 w-9 rounded-lg bg-pri/15 text-pri
                         group-hover:bg-pri/25 group-hover:shadow-[0_0_16px_rgb(var(--orion-pri-glow)/0.35)]
                         transition-all duration-200">
          <Icon name={icon} size={16} />
        </span>
        <div className="text-sm font-medium text-text">{label}</div>
      </div>
      <div className="text-[11px] text-text-dim leading-relaxed">{hint}</div>
    </button>
  );
}

function Metric({ label, value, tone }: { label: string; value: number | undefined; tone: "pri" | "acc" | "ok" }) {
  const pct = value == null ? null : Math.round(value * 100);
  const colorClass = tone === "pri" ? "text-pri" : tone === "acc" ? "text-acc" : "text-ok";
  return (
    <div className="text-center">
      <div className="text-[10px] uppercase tracking-[0.22em] text-text-dim mb-1">{label}</div>
      <div className={`text-3xl font-mono tabular-nums ${colorClass}`}>
        {pct == null ? "—" : `${pct}%`}
      </div>
    </div>
  );
}
