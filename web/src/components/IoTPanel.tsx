/**
 * IoTPanel — smart-home dashboard.
 *
 * Three sections (Devices / Scenes / Sensors). Devices render premium
 * cards with capability chips, on/off switch, dim slider, quick-RGB
 * swatches, hover-revealed edit button, and inline sensor sparklines
 * when the user has enabled "show graph" for that device.
 *
 * Locally-defined devices (see useDeviceConfig) merge with the backend
 * catalog and get a "Local" badge. Their actions still target the same
 * /api/iot/devices/{id}/action endpoint, so wiring them up later is a
 * matter of registering the same id on the backend.
 */

import { useEffect, useMemo, useState } from "react";

import { api, type IoTDevice, type IoTScene, type IoTSensor } from "@/api/rest";
import { DeviceFormModal } from "@/components/DeviceFormModal";
import { useDeviceConfig, type DeviceConfig, type LocalDevice } from "@/hooks/useDeviceConfig";
import { useSensorHistory } from "@/hooks/useSensorHistory";
import { useOrionStore } from "@/stores/orion";
import { Icon } from "@/ui/Icon";
import { Badge, Button, Empty, SectionHeader, Surface, Switch } from "@/ui/primitives";

const QUICK_COLORS: { name: string; hex: string }[] = [
  { name: "rojo",     hex: "#EF4444" },
  { name: "naranja",  hex: "#F59E0B" },
  { name: "verde",    hex: "#22C55E" },
  { name: "cian",     hex: "#7EE7FF" },
  { name: "azul",     hex: "#6D7CFF" },
  { name: "morado",   hex: "#A78BFA" },
  { name: "rosa",     hex: "#F472B6" },
  { name: "blanco",   hex: "#F5F7FA" },
];

export function IoTPanel() {
  const rev         = useOrionStore((s) => s.rev.iot);
  const sensorsLive = useOrionStore((s) => s.iotSensors);
  const cfg         = useDeviceConfig();

  const [backendDevices, setBackendDevices] = useState<IoTDevice[]>([]);
  const [scenes,  setScenes]  = useState<IoTScene[]>([]);
  const [sensors, setSensors] = useState<Record<string, IoTSensor>>({});
  const [error,   setError]   = useState<string | null>(null);

  // modal
  const [editing, setEditing] = useState<IoTDevice | LocalDevice | undefined>(undefined);
  const [modalOpen, setModalOpen] = useState(false);
  // bump para forzar refetch tras crear/editar/borrar en backend
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    let alive = true;
    Promise.all([api.iotDevices(), api.iotScenes(), api.iotSensors()])
      .then(([d, s, se]) => { if (alive) { setBackendDevices(d); setScenes(s); setSensors(se); setError(null); } })
      .catch((e) => { if (alive) setError(String(e)); });
    return () => { alive = false; };
  }, [rev, refreshTick]);

  // merge backend + local, dedup by id (backend wins capabilities).
  const devices = useMemo<(IoTDevice | LocalDevice)[]>(() => {
    const byId = new Map<string, IoTDevice | LocalDevice>();
    cfg.localDevices.forEach((d) => byId.set(d.id, d));
    backendDevices.forEach((d) => byId.set(d.id, d));
    return Array.from(byId.values());
  }, [backendDevices, cfg.localDevices]);

  async function act(
    deviceId: string,
    body: { action: string; value?: number; color?: string; duration?: number },
  ) {
    try { await api.iotAction(deviceId, body); }
    catch (e) { setError(String(e)); }
  }
  async function runScene(sceneId: string) {
    try { await api.iotRunScene(sceneId); }
    catch (e) { setError(String(e)); }
  }

  const allSensors = useMemo(() => {
    const merged: Record<string, { value: string; ts?: number }> = {};
    Object.entries(sensors).forEach(([k, v]) => { merged[k] = { value: v.value }; });
    Object.entries(sensorsLive).forEach(([k, v]) => { merged[k] = v; });
    return merged;
  }, [sensors, sensorsLive]);

  function openCreate()   { setEditing(undefined); setModalOpen(true); }
  function openEdit(d: IoTDevice | LocalDevice) { setEditing(d); setModalOpen(true); }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <SectionHeader
        eyebrow="Sistema"
        title="IoT"
        hint="Dispositivos conectados, escenas y sensores en directo."
        action={
          <div className="flex items-center gap-2">
            <div className="hidden md:flex items-center gap-1.5">
              <Badge tone="info" dot>{devices.length} disp.</Badge>
              <Badge tone="accent">{scenes.length} escenas</Badge>
            </div>
            <Button variant="primary" size="sm" icon="plus" onClick={openCreate}>
              Nuevo
            </Button>
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {error && (
          <div className="mx-6 mt-3 flex items-start gap-2 p-3 rounded-md border border-danger/30 bg-danger/10 text-xs text-danger animate-fade-in">
            <Icon name="alert" size={14} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* devices */}
        <section className="p-6">
          <Subhead title="Dispositivos" count={devices.length} />
          {devices.length === 0
            ? (
              <Empty
                icon="iot"
                title="Sin dispositivos"
                hint="Crea tu primero dispositivo local con el botón Nuevo, o configura el backend para listarlos."
                action={<Button variant="primary" size="sm" icon="plus" onClick={openCreate}>Añadir dispositivo</Button>}
              />
            )
            : (
              <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
                {devices.map((d, i) => (
                  <DeviceCard
                    key={d.id}
                    dev={d}
                    config={cfg.getConfig(d.id)}
                    onAct={act}
                    onEdit={() => openEdit(d)}
                    delay={i * 40}
                  />
                ))}
              </div>
            )}
        </section>

        {/* scenes */}
        <section className="px-6 pb-6">
          <Subhead title="Escenas" count={scenes.length} />
          {scenes.length === 0 ? (
            <p className="text-sm text-text-dim italic">Sin escenas configuradas.</p>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-2">
              {scenes.map((s, i) => (
                <button
                  key={s.id}
                  onClick={() => runScene(s.id)}
                  style={{ animationDelay: `${i * 40}ms` }}
                  className="group relative rounded-xl border border-white/[0.08] bg-elevated/60
                             px-4 py-3 text-left transition-all duration-200 ease-out-expo
                             hover:border-pri/40 hover:bg-elevated hover:shadow-glow-soft
                             animate-fade-in-up"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-text">{s.name}</span>
                    <Icon name="play" size={14} className="text-text-dim group-hover:text-pri transition-colors" />
                  </div>
                  <div className="mt-1 text-[10px] uppercase tracking-[0.18em] text-muted">
                    {s.steps} paso{s.steps === 1 ? "" : "s"}
                  </div>
                </button>
              ))}
            </div>
          )}
        </section>

        {/* sensors (raw live readings, even if not bound to a device) */}
        <section className="px-6 pb-8">
          <Subhead title="Lecturas en vivo" count={Object.keys(allSensors).length} />
          {Object.keys(allSensors).length === 0 ? (
            <p className="text-sm text-text-dim italic">Aún sin lecturas.</p>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-2">
              {Object.entries(allSensors).map(([id, s], i) => (
                <Surface
                  key={id}
                  level={2}
                  className="p-3 animate-fade-in-up"
                  style={{ animationDelay: `${i * 30}ms` }}
                >
                  <div className="text-[10px] uppercase tracking-[0.18em] text-text-dim">{id}</div>
                  <div className="mt-1 text-lg font-mono tabular-nums text-acc">{s.value || "—"}</div>
                </Surface>
              ))}
            </div>
          )}
        </section>
      </div>

      <DeviceFormModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        device={editing}
        /* La identidad del config debe ser estable mientras no cambie la
           entry real — si no, el reset effect del modal se dispararía en
           cada render del panel y reseteamos lo que el usuario escribe. */
        config={editing ? cfg.configs[editing.id] : undefined}
        onSaved={() => setRefreshTick((n) => n + 1)}
        onSubmitLocal={(dev, c) => cfg.addLocal(dev, c)}
        onSubmitConfig={(id, c) => cfg.setConfig(id, c)}
        onDeleteLocal={cfg.removeLocal}
      />
    </div>
  );
}

function Subhead({ title, count }: { title: string; count: number }) {
  return (
    <div className="flex items-end justify-between mb-3">
      <h3 className="text-[11px] uppercase tracking-[0.24em] text-text-dim">{title}</h3>
      <span className="text-[10px] uppercase tracking-[0.18em] text-muted">{count}</span>
    </div>
  );
}

/* ── DEVICE CARD ─────────────────────────────────────────────────── */
function DeviceCard({
  dev, config, onAct, onEdit, delay,
}: {
  dev:    IoTDevice | LocalDevice;
  config: DeviceConfig;
  onAct:  (id: string, body: { action: string; value?: number; color?: string; duration?: number }) => void;
  onEdit: () => void;
  delay?: number;
}) {
  const [dim, setDim] = useState(50);
  const [on,  setOn]  = useState<boolean | null>(null);
  const caps   = dev.capabilities;
  const isLocal = !!(dev as LocalDevice).__local;
  const isSensor = !!caps.sensor;
  const displayName = config.displayName || dev.name;

  function toggle() {
    const next = !on;
    setOn(next);
    onAct(dev.id, { action: next ? "on" : "off" });
  }

  const chips = [
    caps.on_off   && { tone: "info"    as const, label: "on/off" },
    caps.dimmable && { tone: "accent"  as const, label: "dim"    },
    caps.rgb      && { tone: "neutral" as const, label: "rgb"    },
    caps.sensor   && { tone: "warn"    as const, label: caps.sensor },
  ].filter(Boolean) as { tone: "info" | "accent" | "neutral" | "warn"; label: string }[];

  return (
    <Surface
      level={2}
      className="group relative p-4 animate-fade-in-up"
      style={{ animationDelay: `${delay ?? 0}ms` }}
    >
      <header className="flex items-start justify-between gap-3 mb-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h4 className="text-[15px] font-medium text-text leading-tight truncate">{displayName}</h4>
            {isLocal   && <Badge tone="accent">Local</Badge>}
            {isSensor  && config.showGraph && <Badge tone="info" dot>Gráfico</Badge>}
          </div>
          <code className="text-[10px] font-mono text-muted">{dev.transport}</code>
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
          {caps.on_off && (
            <Switch on={on === true} onClick={toggle} />
          )}
        </div>
      </header>

      <div className="flex flex-wrap gap-1 mb-3">
        {chips.length === 0 && <span className="text-[10px] text-muted">—</span>}
        {chips.map((c) => (
          <Badge key={c.label} tone={c.tone}>{c.label}</Badge>
        ))}
        {config.updateFreqS !== undefined && (
          <Badge tone="neutral">
            ↻ {config.updateFreqS < 60 ? `${config.updateFreqS}s` : `${(config.updateFreqS / 60).toFixed(1)}m`}
          </Badge>
        )}
      </div>

      {caps.dimmable && (
        <div className="flex items-center gap-3 mb-2.5">
          <input
            type="range" min={0} max={100} value={dim}
            onChange={(e) => setDim(Number(e.target.value))}
            onMouseUp={() => onAct(dev.id, { action: "dim", value: dim })}
            onTouchEnd={() => onAct(dev.id, { action: "dim", value: dim })}
            className="flex-1 accent-pri"
          />
          <span className="text-xs font-mono tabular-nums w-9 text-right text-text-dim">{dim}%</span>
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
      {isSensor && (
        <SensorReadout deviceId={dev.id} graph={!!config.showGraph} />
      )}
    </Surface>
  );
}

/* ── SENSOR READOUT (value + optional sparkline) ─────────────────── */
function SensorReadout({ deviceId, graph }: { deviceId: string; graph: boolean }) {
  const sample  = useOrionStore((s) => s.iotSensors[deviceId]);
  const history = useSensorHistory(deviceId, 48);

  if (!sample && history.length === 0) {
    return (
      <div className="mt-2 rounded-md border border-dashed border-white/[0.06] px-3 py-2 text-[10px] uppercase tracking-[0.18em] text-muted text-center">
        Esperando primera lectura…
      </div>
    );
  }

  return (
    <div className="mt-3 rounded-lg border border-white/[0.05] bg-bg/40 p-3">
      <div className="flex items-baseline justify-between">
        <div className="text-[10px] uppercase tracking-[0.22em] text-text-dim">Última lectura</div>
        <div className="text-xl font-mono tabular-nums text-acc">{sample?.value || "—"}</div>
      </div>
      {graph && history.length >= 2 && (
        <div className="mt-2">
          <Sparkline data={history.map((p) => p.value)} />
          <div className="mt-1.5 flex items-center justify-between text-[10px] uppercase tracking-[0.18em] text-muted">
            <span>{history.length} muestras</span>
            <span className="flex items-center gap-1">
              <span className="h-1 w-1 rounded-full bg-acc shadow-[0_0_6px_rgb(var(--orion-acc))]" />
              live
            </span>
          </div>
        </div>
      )}
      {graph && history.length < 2 && (
        <div className="mt-2 h-12 rounded-md border border-dashed border-white/[0.06] grid place-items-center text-[10px] uppercase tracking-[0.18em] text-muted">
          Acumulando datos…
        </div>
      )}
    </div>
  );
}

/* ── SPARKLINE (mirrors the area chart from TelemetryPanel) ──────── */
function Sparkline({ data }: { data: number[] }) {
  const W = 260, H = 64, P = 3;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = Math.max(max - min, 0.001);
  const step  = (W - 2 * P) / Math.max(data.length - 1, 1);
  const pts   = data.map((v, i) => {
    const x = P + i * step;
    const y = H - P - ((v - min) / range) * (H - 2 * P);
    return [x, y] as const;
  });
  const line = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${pts[0][0]},${H} ${line} ${pts[pts.length - 1][0]},${H}`;
  const id = useStableId();

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-16">
      <defs>
        <linearGradient id={`spark-fill-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor="rgb(var(--orion-acc))" stopOpacity="0.36" />
          <stop offset="100%" stopColor="rgb(var(--orion-acc))" stopOpacity="0" />
        </linearGradient>
        <linearGradient id={`spark-line-${id}`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%"   stopColor="rgb(var(--orion-acc))" stopOpacity="0.25" />
          <stop offset="100%" stopColor="rgb(var(--orion-acc))" stopOpacity="1" />
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
        cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="2.2"
        fill="rgb(var(--orion-acc))"
        style={{ filter: "drop-shadow(0 0 4px rgb(var(--orion-acc)))" }}
      />
    </svg>
  );
}

/* tiny per-component id helper for the SVG gradient URLs */
let _sparkSeq = 0;
function useStableId(): number {
  // We don't need React.useId (TS lib level) — a module-scoped counter is fine
  // since SVG <defs> ids only need to be unique on the page at a given moment.
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const [id] = useState(() => ++_sparkSeq);
  return id;
}
