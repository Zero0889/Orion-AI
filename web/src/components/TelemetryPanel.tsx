/**
 * TelemetryPanel — live system metrics rendered as elegant SVG area
 * charts. The backend pushes a `telemetry` event every ~2 s with cpu/ram
 * /disk in 0..1. We keep up to 60 points per series.
 */

import { useOrionStore } from "@/stores/orion";
import { Icon } from "@/ui/Icon";
import { Badge, Empty, SectionHeader, Surface } from "@/ui/primitives";

type Key = "cpu" | "ram" | "disk";
const METRICS: { key: Key; label: string; tone: string; gradientId: string }[] = [
  { key: "cpu",  label: "CPU",   tone: "rgb(var(--orion-pri))",    gradientId: "telCpu"  },
  { key: "ram",  label: "RAM",   tone: "rgb(var(--orion-acc))",    gradientId: "telRam"  },
  { key: "disk", label: "Disco", tone: "rgb(var(--orion-ok))",     gradientId: "telDisk" },
];

export function TelemetryPanel() {
  const tel = useOrionStore((s) => s.telemetry);
  const empty = tel.last === null;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <SectionHeader
        eyebrow="Sistema"
        title="Telemetría"
        hint="Métricas en vivo, actualizadas cada 2 s vía WebSocket."
        action={
          <Badge tone={empty ? "neutral" : "success"} dot>
            {empty ? "Esperando" : "En directo"}
          </Badge>
        }
      />

      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {empty ? (
          <Empty
            icon="telemetry"
            title="Esperando datos"
            hint="Cuando el backend empiece a emitir eventos `telemetry` los verás dibujados aquí."
          />
        ) : (
          <section className="p-6 grid grid-cols-1 lg:grid-cols-3 gap-3">
            {METRICS.map((m, i) => {
              const series = tel[m.key];
              const value  = tel.last ? tel.last[m.key] : 0;
              return (
                <Surface
                  key={m.key}
                  level={2}
                  className="p-4 animate-fade-in-up"
                  style={{ animationDelay: `${i * 60}ms` }}
                >
                  <header className="flex items-center justify-between mb-2">
                    <div>
                      <div className="text-[10px] uppercase tracking-[0.22em] text-text-dim">{m.label}</div>
                      <div className="mt-1 text-3xl font-semibold tabular-nums" style={{ color: m.tone }}>
                        {(value * 100).toFixed(0)}
                        <span className="text-base text-muted ml-0.5">%</span>
                      </div>
                    </div>
                    <PulseDot color={m.tone} />
                  </header>
                  <AreaChart values={series} tone={m.tone} gradientId={m.gradientId} />
                  <p className="mt-2 text-[10px] uppercase tracking-[0.18em] text-muted">
                    {series.length} muestra{series.length === 1 ? "" : "s"} · {series.length * 2}s
                  </p>
                </Surface>
              );
            })}
          </section>
        )}
      </div>
    </div>
  );
}

function PulseDot({ color }: { color: string }) {
  return (
    <span className="relative inline-grid place-items-center h-6 w-6">
      <span className="absolute inset-0 rounded-full animate-pulse-soft" style={{ background: color, opacity: 0.18 }} />
      <span className="relative h-1.5 w-1.5 rounded-full" style={{ background: color }} />
    </span>
  );
}

function AreaChart({ values, tone, gradientId }: { values: number[]; tone: string; gradientId: string }) {
  const W = 260, H = 80, P = 4;
  if (values.length < 2) {
    return (
      <div className="h-20 rounded-md bg-white/[0.02] flex items-center justify-center text-[10px] text-muted">
        <Icon name="telemetry" size={14} className="mr-1.5 opacity-50" />
        Esperando datos…
      </div>
    );
  }
  const max  = Math.max(...values, 0.01);
  const step = (W - 2 * P) / Math.max(values.length - 1, 1);
  const pts  = values.map((v, i) => {
    const x = P + i * step;
    const y = H - P - (v / max) * (H - 2 * P);
    return [x, y] as const;
  });
  const line = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${pts[0][0]},${H} ${line} ${pts[pts.length - 1][0]},${H}`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-20">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor={tone} stopOpacity="0.4" />
          <stop offset="100%" stopColor={tone} stopOpacity="0" />
        </linearGradient>
        <linearGradient id={`${gradientId}-line`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%"   stopColor={tone} stopOpacity="0.2" />
          <stop offset="100%" stopColor={tone} stopOpacity="1" />
        </linearGradient>
      </defs>
      <polygon points={area} fill={`url(#${gradientId})`} />
      <polyline
        points={line}
        fill="none"
        stroke={`url(#${gradientId}-line)`}
        strokeWidth="1.6"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {/* leading dot */}
      <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="2.5"
              fill={tone}
              style={{ filter: `drop-shadow(0 0 4px ${tone})` }} />
    </svg>
  );
}
