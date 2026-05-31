/**
 * TelemetryPanel — CPU/RAM/disco en vivo.
 *
 * El backend publica el evento `telemetry` cada ~2 s. El store mantiene
 * los últimos 60 puntos en arrays paralelos; aquí los dibujamos como
 * sparklines en SVG (sin libs externas).
 */

import { useOrionStore } from "@/stores/orion";

const METRICS = [
  { key: "cpu",  label: "CPU",   color: "#ff2a4d" },
  { key: "ram",  label: "RAM",   color: "#ff6b1a" },
  { key: "disk", label: "Disco", color: "#33ff99" },
] as const;

export function TelemetryPanel() {
  const tel = useOrionStore((s) => s.telemetry);

  return (
    <div className="flex flex-col h-full overflow-y-auto scrollbar-thin">
      <header className="px-6 py-4 border-b border-border-b">
        <h2 className="text-sm uppercase tracking-[0.3em] text-text-dim">Telemetría</h2>
        <p className="text-xs text-text-dim/70 mt-1">
          Métricas del sistema, actualizadas cada 2 s vía WebSocket.
        </p>
      </header>

      <section className="grid grid-cols-1 lg:grid-cols-3 gap-3 p-6">
        {METRICS.map((m) => {
          const series = tel[m.key];
          const value  = tel.last ? tel.last[m.key] : 0;
          return (
            <article
              key={m.key}
              className="rounded-lg border border-border-b bg-panel2 p-4"
            >
              <header className="flex items-center justify-between mb-3">
                <span className="text-[10px] uppercase tracking-widest text-text-dim">{m.label}</span>
                <span className="text-2xl font-mono tabular-nums" style={{ color: m.color }}>
                  {(value * 100).toFixed(0)}%
                </span>
              </header>
              <Sparkline values={series} color={m.color} />
              <p className="text-[10px] text-text-dim mt-2">
                {series.length} muestra{series.length === 1 ? "" : "s"} ·{" "}
                últimos {(series.length * 2)} s
              </p>
            </article>
          );
        })}
      </section>

      {tel.last === null && (
        <p className="text-center text-text-dim text-sm italic mt-4">
          Esperando primer evento de telemetría…
        </p>
      )}
    </div>
  );
}

function Sparkline({ values, color }: { values: number[]; color: string }) {
  const W = 240, H = 60, P = 2;
  if (values.length < 2) {
    return <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-16 opacity-30" />;
  }
  const max = Math.max(...values, 0.01);
  const step = (W - 2 * P) / Math.max(values.length - 1, 1);
  const points = values
    .map((v, i) => `${(P + i * step).toFixed(1)},${(H - P - (v / max) * (H - 2 * P)).toFixed(1)}`)
    .join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-16">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
