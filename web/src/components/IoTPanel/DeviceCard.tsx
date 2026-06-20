/**
 * DeviceCard — tarjeta premium de un dispositivo IoT.
 *
 * Renderiza:
 *  - Header con nombre, badges (Local / Gráfico), icono sensor, switch on/off.
 *  - Capability chips (on/off, dim, rgb, sensor).
 *  - Slider de dimmer si caps.dimmable.
 *  - Swatches de color rápido si caps.rgb.
 *  - SensorReadout (último valor + barra de rango + sparkline opcional) si
 *    caps.sensor.
 *
 * `memo`: solo re-renderiza si cambian sus props. Los sensores tickean a
 * 1Hz; sin memo + selector granular en SensorReadout, los 8 cards se
 * re-rendereaban en cada lectura (~480 renders/min del panel).
 */

import { memo, useMemo, useState } from "react";

import type { IoTDevice } from "@/api/rest";
import type { DeviceConfig, LocalDevice } from "@/hooks/useDeviceConfig";
import { useSensorHistory } from "@/hooks/useSensorHistory";
import {
  formatSensorValue,
  getSensorPersonality,
  rangePercent,
  type SensorPersonality,
} from "@/lib/sensorPersonality";
import { useOrionStore } from "@/stores/orion";
import { Icon } from "@/ui/Icon";
import { Badge, Surface, Switch } from "@/ui/primitives";

const QUICK_COLORS: { name: string; hex: string }[] = [
  { name: "rojo", hex: "#EF4444" },
  { name: "naranja", hex: "#F59E0B" },
  { name: "verde", hex: "#22C55E" },
  { name: "cian", hex: "#7EE7FF" },
  { name: "azul", hex: "#6D7CFF" },
  { name: "morado", hex: "#A78BFA" },
  { name: "rosa", hex: "#F472B6" },
  { name: "blanco", hex: "#F5F7FA" },
];

interface Props {
  dev: IoTDevice | LocalDevice;
  config: DeviceConfig;
  onAct: (
    id: string,
    body: { action: string; value?: number; color?: string; duration?: number },
  ) => void;
  onEdit: () => void;
  delay?: number;
}

export const DeviceCard = memo(function DeviceCard({ dev, config, onAct, onEdit, delay }: Props) {
  const [dim, setDim] = useState(50);
  const [on, setOn] = useState<boolean | null>(null);
  const caps = dev.capabilities;
  const isLocal = !!(dev as LocalDevice).__local;
  const isSensor = !!caps.sensor;
  const displayName = config.displayName || dev.name;
  const personality = isSensor ? getSensorPersonality(caps.sensor) : null;

  function toggle() {
    const next = !on;
    setOn(next);
    onAct(dev.id, { action: next ? "on" : "off" });
  }

  const chips = [
    caps.on_off && { tone: "info" as const, label: "on/off" },
    caps.dimmable && { tone: "accent" as const, label: "dim" },
    caps.rgb && { tone: "neutral" as const, label: "rgb" },
    caps.sensor && { tone: "warn" as const, label: caps.sensor },
  ].filter(Boolean) as { tone: "info" | "accent" | "neutral" | "warn"; label: string }[];

  return (
    <Surface
      level={2}
      className="group relative p-4 pl-5 animate-fade-in-up overflow-hidden"
      style={{
        animationDelay: `${delay ?? 0}ms`,
        ...(personality ? { ["--sensor-accent" as string]: personality.color } : {}),
      }}
    >
      {/* Barra lateral identitaria del sensor (solo cards de sensor) */}
      {personality && (
        <span
          aria-hidden="true"
          className="absolute left-0 top-3 bottom-3 w-[3px] rounded-r-full"
          style={{
            background: personality.color,
            boxShadow: `0 0 12px ${personality.color}55`,
          }}
        />
      )}

      <header className="flex items-start justify-between gap-3 mb-2">
        <div className="min-w-0 flex items-start gap-2.5">
          {personality && (
            <span
              className="grid place-items-center h-8 w-8 shrink-0 rounded-lg border"
              style={{
                background: `${personality.color}1A`,
                borderColor: `${personality.color}55`,
                color: personality.color,
              }}
            >
              <Icon name={personality.icon} size={16} />
            </span>
          )}
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h4 className="text-[15px] font-medium text-text leading-tight truncate">
                {displayName}
              </h4>
              {isLocal && <Badge tone="accent">Local</Badge>}
              {isSensor && config.showGraph && (
                <Badge tone="info" dot>
                  Gráfico
                </Badge>
              )}
            </div>
            <code className="text-[10px] font-mono text-muted">{dev.transport}</code>
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <button
            onClick={onEdit}
            title="Editar"
            className="h-8 w-8 grid place-items-center rounded-md text-text-dim
                       opacity-0 group-hover:opacity-100
                       hover:text-text hover:bg-white/[0.05] transition-all"
          >
            <Icon name="edit" size={14} />
          </button>
          {caps.on_off && <Switch on={on === true} onClick={toggle} />}
        </div>
      </header>

      <div className="flex flex-wrap gap-1 mb-3">
        {chips.length === 0 && <span className="text-[10px] text-muted">—</span>}
        {chips.map((c) => (
          <Badge key={c.label} tone={c.tone}>
            {c.label}
          </Badge>
        ))}
        {config.updateFreqS !== undefined && (
          <Badge tone="neutral">
            ↻{" "}
            {config.updateFreqS < 60
              ? `${config.updateFreqS}s`
              : `${(config.updateFreqS / 60).toFixed(1)}m`}
          </Badge>
        )}
      </div>

      {caps.dimmable && (
        <div className="flex items-center gap-3 mb-2.5">
          <input
            type="range"
            min={0}
            max={100}
            value={dim}
            onChange={(e) => setDim(Number(e.target.value))}
            onMouseUp={() => onAct(dev.id, { action: "dim", value: dim })}
            onTouchEnd={() => onAct(dev.id, { action: "dim", value: dim })}
            className="flex-1 accent-pri"
          />
          <span className="text-xs font-mono tabular-nums w-9 text-right text-text-dim">
            {dim}%
          </span>
        </div>
      )}

      {caps.rgb && (
        <div className="flex flex-wrap gap-1.5 mt-1">
          {QUICK_COLORS.map((c) => (
            <button
              key={c.name}
              onClick={() => onAct(dev.id, { action: "rgb", color: c.name })}
              title={c.name}
              className="h-6 w-6 rounded-full border border-white/[0.10] hover:scale-110
                         hover:shadow-glow-soft transition-transform duration-150"
              style={{ background: c.hex }}
            />
          ))}
        </div>
      )}

      {/* SENSOR readout + optional sparkline */}
      {isSensor && personality && (
        <SensorReadout deviceId={dev.id} graph={!!config.showGraph} personality={personality} />
      )}
    </Surface>
  );
});

/* ── SENSOR READOUT (value + optional sparkline) ─────────────────── */
const SensorReadout = memo(function SensorReadout({
  deviceId,
  graph,
  personality,
}: {
  deviceId: string;
  graph: boolean;
  personality: SensorPersonality;
}) {
  const sample = useOrionStore((s) => s.iotSensors[deviceId]);
  const history = useSensorHistory(deviceId, 48);

  if (!sample && history.length === 0) {
    return (
      <div className="mt-2 rounded-md border border-dashed border-white/[0.06] px-3 py-2 text-[10px] uppercase tracking-[0.18em] text-muted text-center">
        Esperando primera lectura…
      </div>
    );
  }

  const pct = rangePercent(sample?.value, personality);
  const displayValue = formatSensorValue(sample?.value, personality);

  return (
    <div
      className="mt-3 rounded-lg border bg-bg/40 p-3"
      style={{ borderColor: `${personality.color}22` }}
    >
      <div className="flex items-end justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.22em] text-text-dim">
            Última lectura · {personality.hint ?? personality.label.toLowerCase()}
          </div>
          <div
            className="mt-0.5 text-2xl font-mono tabular-nums leading-none"
            style={{ color: personality.color }}
          >
            {displayValue}
          </div>
        </div>
        {pct !== null && <RangeBar pct={pct} color={personality.color} />}
      </div>

      {graph && history.length >= 2 && (
        <div className="mt-3">
          <Sparkline data={history.map((p) => p.value)} accent={personality.color} />
          <div className="mt-1.5 flex items-center justify-between text-[10px] uppercase tracking-[0.18em] text-muted">
            <span>{history.length} muestras</span>
            <span className="flex items-center gap-1">
              <span
                className="h-1 w-1 rounded-full"
                style={{ background: personality.color, boxShadow: `0 0 6px ${personality.color}` }}
              />
              live
            </span>
          </div>
        </div>
      )}
      {graph && history.length < 2 && (
        <div className="mt-3 h-12 rounded-md border border-dashed border-white/[0.06] grid place-items-center text-[10px] uppercase tracking-[0.18em] text-muted">
          Acumulando datos…
        </div>
      )}
    </div>
  );
});

/* ── RANGE BAR (mini termostato vertical) ────────────────────────── */
const RangeBar = memo(function RangeBar({ pct, color }: { pct: number; color: string }) {
  const h = Math.max(0, Math.min(1, pct)) * 100;
  return (
    <div
      className="relative w-2 h-12 rounded-full overflow-hidden border"
      style={{ background: `${color}10`, borderColor: `${color}33` }}
      aria-label={`${Math.round(h)}% del rango`}
    >
      <div
        className="absolute bottom-0 left-0 right-0 rounded-full transition-[height] duration-500 ease-out"
        style={{
          height: `${h}%`,
          background: color,
          boxShadow: `0 0 10px ${color}AA`,
        }}
      />
    </div>
  );
});

/* ── SPARKLINE ───────────────────────────────────────────────────── */
// memo + useMemo de los path SVG: el cálculo de min/max/range/pts/line es
// O(n) sobre la ventana de muestras. Se recalcula solo cuando el array
// `data` cambia de referencia (history es un nuevo array cada tick, así
// que sirve como tripwire natural).
const Sparkline = memo(function Sparkline({ data, accent }: { data: number[]; accent?: string }) {
  const W = 260,
    H = 64,
    P = 3;
  const id = useStableId();
  // Si llega un acento por personalidad lo usamos; si no, caemos al
  // token global --orion-acc (compatibilidad con consumidores futuros).
  const stroke = accent ?? "rgb(var(--orion-acc))";

  const { line, area, tip } = useMemo(() => {
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = Math.max(max - min, 0.001);
    const step = (W - 2 * P) / Math.max(data.length - 1, 1);
    const pts = data.map((v, i) => {
      const x = P + i * step;
      const y = H - P - ((v - min) / range) * (H - 2 * P);
      return [x, y] as const;
    });
    const lineStr = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
    const areaStr = `${pts[0][0]},${H} ${lineStr} ${pts[pts.length - 1][0]},${H}`;
    return { line: lineStr, area: areaStr, tip: pts[pts.length - 1] };
  }, [data]);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-16">
      <defs>
        <linearGradient id={`spark-fill-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.36" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
        <linearGradient id={`spark-line-${id}`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.25" />
          <stop offset="100%" stopColor={stroke} stopOpacity="1" />
        </linearGradient>
      </defs>
      <polygon points={area} fill={`url(#spark-fill-${id})`} />
      <polyline
        points={line}
        fill="none"
        stroke={`url(#spark-line-${id})`}
        strokeWidth="1.4"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle
        cx={tip[0]}
        cy={tip[1]}
        r="2.2"
        fill={stroke}
        style={{ filter: `drop-shadow(0 0 4px ${stroke})` }}
      />
    </svg>
  );
});

/* tiny per-component id helper for the SVG gradient URLs */
let _sparkSeq = 0;
function useStableId(): number {
  // We don't need React.useId (TS lib level) — a module-scoped counter is fine
  // since SVG <defs> ids only need to be unique on the page at a given moment.
  const [id] = useState(() => ++_sparkSeq);
  return id;
}
