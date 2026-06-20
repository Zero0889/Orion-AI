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

import { memo, useEffect, useMemo, useState } from "react";

import { api, type IoTDevice, type IoTScene, type IoTSensor } from "@/api/rest";
import { DeviceFormModal } from "@/components/DeviceFormModal";
import { GogScopeGuard } from "@/components/GogScopeGuard";
import { useDeviceConfig, type DeviceConfig, type LocalDevice } from "@/hooks/useDeviceConfig";
import { useSensorHistory } from "@/hooks/useSensorHistory";
import {
  formatSensorValue,
  getSensorPersonality,
  rangePercent,
  type SensorPersonality,
} from "@/lib/sensorPersonality";
import { useOrionStore } from "@/stores/orion";
import { Icon } from "@/ui/Icon";
import { Badge, Button, Empty, SectionHeader, Surface, Switch } from "@/ui/primitives";

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

export function IoTPanel() {
  const rev = useOrionStore((s) => s.rev.iot);
  const sensorsLive = useOrionStore((s) => s.iotSensors);
  const cfg = useDeviceConfig();

  const [backendDevices, setBackendDevices] = useState<IoTDevice[]>([]);
  const [scenes, setScenes] = useState<IoTScene[]>([]);
  const [sensors, setSensors] = useState<Record<string, IoTSensor>>({});
  const [error, setError] = useState<string | null>(null);
  const [paused, setPaused] = useState<boolean>(false);
  const [pausing, setPausing] = useState<boolean>(false);

  // modal
  const [editing, setEditing] = useState<IoTDevice | LocalDevice | undefined>(undefined);
  const [modalOpen, setModalOpen] = useState(false);
  // bump para forzar refetch tras crear/editar/borrar en backend
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    let alive = true;
    Promise.all([api.iotDevices(), api.iotScenes(), api.iotSensors(), api.iotPausedStatus()])
      .then(([d, s, se, p]) => {
        if (!alive) return;
        setBackendDevices(d);
        setScenes(s);
        setSensors(se);
        setPaused(p.paused);
        setError(null);
      })
      .catch((e) => {
        if (alive) setError(String(e));
      });
    return () => {
      alive = false;
    };
  }, [rev, refreshTick]);

  async function togglePause() {
    setPausing(true);
    try {
      const r = paused ? await api.iotConnect() : await api.iotDisconnect();
      setPaused(r.paused);
      setRefreshTick((n) => n + 1);
    } catch (e) {
      setError(String(e));
    } finally {
      setPausing(false);
    }
  }

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
    try {
      await api.iotAction(deviceId, body);
    } catch (e) {
      setError(String(e));
    }
  }
  async function runScene(sceneId: string) {
    try {
      await api.iotRunScene(sceneId);
    } catch (e) {
      setError(String(e));
    }
  }

  const allSensors = useMemo(() => {
    const merged: Record<string, { value: string; ts?: number }> = {};
    Object.entries(sensors).forEach(([k, v]) => {
      merged[k] = { value: v.value };
    });
    Object.entries(sensorsLive).forEach(([k, v]) => {
      merged[k] = v;
    });
    return merged;
  }, [sensors, sensorsLive]);

  function openCreate() {
    setEditing(undefined);
    setModalOpen(true);
  }
  function openEdit(d: IoTDevice | LocalDevice) {
    setEditing(d);
    setModalOpen(true);
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <SectionHeader
        eyebrow="Sistema"
        title="IoT"
        hint="Dispositivos conectados, escenas y sensores en directo."
        action={
          <div className="flex items-center gap-2">
            <div className="hidden md:flex items-center gap-1.5">
              <Badge tone={paused ? "warn" : "info"} dot>
                {paused ? "Sensores pausados" : `${devices.length} disp.`}
              </Badge>
              {!paused && <Badge tone="accent">{scenes.length} escenas</Badge>}
            </div>
            <ExportMenu />
            <Button
              variant={paused ? "primary" : "ghost"}
              size="sm"
              icon={paused ? "play" : "close"}
              onClick={togglePause}
              disabled={pausing}
              title={
                paused
                  ? "Reconectar transports (COM + MQTT)"
                  : "Cortar conexión: cierra COM y broker hasta que reactives"
              }
            >
              {paused ? "Reactivar sensores" : "Apagar sensores"}
            </Button>
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
          {devices.length === 0 ? (
            <Empty
              icon="iot"
              title="Sin dispositivos"
              hint="Crea tu primero dispositivo local con el botón Nuevo, o configura el backend para listarlos."
              action={
                <Button variant="primary" size="sm" icon="plus" onClick={openCreate}>
                  Añadir dispositivo
                </Button>
              }
            />
          ) : (
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
                    <Icon
                      name="play"
                      size={14}
                      className="text-text-dim group-hover:text-pri transition-colors"
                    />
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
                  <div className="mt-1 text-lg font-mono tabular-nums text-acc">
                    {s.value || "—"}
                  </div>
                </Surface>
              ))}
            </div>
          )}
        </section>

        {/* google sheets sync */}
        <section className="px-6 pb-10">
          <Subhead title="Google Sheets" count={0} />
          <GogScopeGuard requires={["sheets", "drive"]} title="Sheets requiere permisos de Google">
            <SheetsPanel />
          </GogScopeGuard>
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
// React.memo: DeviceCard solo re-renderiza si cambian sus props. Como el
// sensor en vivo se lee dentro de <SensorReadout> con un selector granular
// del store (solo escucha iotSensors[deviceId]), los cards de OTROS
// dispositivos no se rerenderean cuando llega una lectura. Sin esto, con 8
// sensores ticking a 1Hz teníamos ~480 re-renders/min del panel entero.
const DeviceCard = memo(function DeviceCard({
  dev,
  config,
  onAct,
  onEdit,
  delay,
}: {
  dev: IoTDevice | LocalDevice;
  config: DeviceConfig;
  onAct: (
    id: string,
    body: { action: string; value?: number; color?: string; duration?: number },
  ) => void;
  onEdit: () => void;
  delay?: number;
}) {
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

/* ── SPARKLINE (mirrors the area chart from TelemetryPanel) ──────── */
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

/* ── SHEETS PANEL ─────────────────────────────────────────────────── */
// Pequeño dashboard que muestra el estado del sync continuo a Google
// Sheets. Si está desconectado, muestra el formulario de conexión.
// Si está conectado, muestra el link al Sheet, último sync, errores
// y un botón para forzar sync inmediato o desconectar.
function SheetsPanel() {
  const [state, setState] = useState<import("@/api/rest").IoTSheetsState | null>(null);
  const [email, setEmail] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // tick para refrescar el "hace Xs" sin pegarle al backend
  const [, setTick] = useState(0);

  async function refresh() {
    try {
      setState(await api.iotSheetsStatus());
    } catch (e) {
      setErr(String(e));
    }
  }

  useEffect(() => {
    refresh();
  }, []);
  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), 5000);
    return () => clearInterval(id);
  }, []);

  async function doConnect() {
    if (!email.trim()) {
      setErr("Falta el email.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const s = await api.iotSheetsConnect({
        account: email.trim(),
        title: title.trim() || undefined,
      });
      setState(s);
      setEmail("");
      setTitle("");
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function doDisconnect() {
    setBusy(true);
    setErr(null);
    try {
      setState(await api.iotSheetsDisconnect());
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function doSyncNow() {
    setBusy(true);
    setErr(null);
    try {
      await api.iotSheetsSyncNow();
      // El sync corre en background, esperamos un tiquito y re-fetch.
      setTimeout(() => {
        refresh();
        setBusy(false);
      }, 1500);
    } catch (e) {
      setErr(String(e));
      setBusy(false);
    }
  }

  async function doReformat() {
    setBusy(true);
    setErr(null);
    try {
      await api.iotSheetsReformat();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function saveInterval(secs: number) {
    setBusy(true);
    setErr(null);
    try {
      setState(await api.iotSheetsSetInterval(secs));
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!state) {
    return <p className="text-sm text-text-dim italic">Cargando…</p>;
  }

  // ── Disconnected: formulario de conexión ────────────────────────
  if (!state.enabled) {
    return (
      <Surface level={2} className="p-4">
        <div className="flex items-start gap-3 mb-3">
          <span
            className="grid place-items-center h-9 w-9 rounded-lg
                           bg-acc/10 border border-acc/30 text-acc shrink-0"
          >
            <Icon name="upload" size={16} />
          </span>
          <div className="min-w-0">
            <h4 className="text-[15px] font-medium leading-tight">Sincronizar con Google Sheets</h4>
            <p className="mt-0.5 text-[12px] text-text-dim leading-snug">
              ORION va a crear un Sheet nuevo y le pushea las lecturas cada 5 minutos. Necesita que
              tu cuenta tenga el scope <code className="text-acc font-mono">sheets</code> autorizado
              en gog.
            </p>
          </div>
        </div>

        <div className="grid gap-2 mt-3">
          <input
            type="email"
            placeholder="tu-email@gmail.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={busy}
            className="w-full px-3 py-2 rounded-md border border-white/[0.08]
                       bg-bg/40 text-sm focus:outline-none focus:border-acc/60"
          />
          <input
            type="text"
            placeholder="Nombre del Sheet (opcional)"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            disabled={busy}
            className="w-full px-3 py-2 rounded-md border border-white/[0.08]
                       bg-bg/40 text-sm focus:outline-none focus:border-acc/60"
          />
          <div className="flex justify-end mt-1">
            <Button
              variant="primary"
              size="sm"
              icon="upload"
              disabled={busy || !email.trim()}
              onClick={doConnect}
            >
              {busy ? "Conectando…" : "Conectar"}
            </Button>
          </div>
          {err && (
            <div
              className="mt-1 flex items-start gap-2 p-2 rounded-md
                            border border-danger/30 bg-danger/10 text-xs text-danger"
            >
              <Icon name="alert" size={13} className="mt-0.5 shrink-0" />
              <span className="break-all">{err}</span>
            </div>
          )}
        </div>
      </Surface>
    );
  }

  // ── Connected: dashboard ────────────────────────────────────────
  const ageStr = state.last_sync_at ? formatAge(state.last_sync_at) : "nunca";

  return (
    <Surface level={2} className="p-4">
      <div className="flex items-start gap-3">
        <span
          className="grid place-items-center h-9 w-9 rounded-lg
                         bg-ok/15 border border-ok/40 text-ok shrink-0"
        >
          <Icon name="check" size={16} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h4 className="text-[15px] font-medium leading-tight">Sheet conectado</h4>
            <Badge tone="info" dot>
              live
            </Badge>
          </div>
          <div className="mt-0.5 text-[12px] text-text-dim font-mono break-all">
            {state.account}
          </div>
        </div>
        <Button variant="ghost" size="sm" icon="close" onClick={doDisconnect} disabled={busy}>
          Desconectar
        </Button>
      </div>

      <div className="mt-3 grid sm:grid-cols-3 gap-2">
        <Surface level={2} className="p-3 bg-bg/40">
          <div className="text-[10px] uppercase tracking-[0.18em] text-text-dim">Última sync</div>
          <div className="mt-0.5 text-sm tabular-nums">{ageStr}</div>
        </Surface>
        <Surface level={2} className="p-3 bg-bg/40">
          <div className="text-[10px] uppercase tracking-[0.18em] text-text-dim">
            Filas pusheadas
          </div>
          <div className="mt-0.5 text-sm font-mono tabular-nums">
            {state.last_pushed_row.toLocaleString()}
          </div>
        </Surface>
        <IntervalControl value={state.sync_interval_s} disabled={busy} onSave={saveInterval} />
      </div>

      {state.spreadsheet_url && (
        <a
          href={state.spreadsheet_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 flex items-center gap-2 px-3 py-2 rounded-md
                     border border-acc/30 bg-acc/10 text-sm text-acc
                     hover:bg-acc/15 transition-colors"
        >
          <Icon name="chart" size={14} />
          <span className="flex-1 truncate font-mono">{state.spreadsheet_url}</span>
          <Icon name="arrow-right" size={13} />
        </a>
      )}

      <div className="mt-3 flex justify-end gap-1.5">
        <Button
          variant="ghost"
          size="sm"
          icon="edit"
          onClick={doReformat}
          disabled={busy}
          title="Reaplica cabecera, freeze, formato de fechas y bandas al Sheet"
        >
          Reformatear
        </Button>
        <Button variant="ghost" size="sm" icon="bolt" onClick={doSyncNow} disabled={busy}>
          {busy ? "Sincronizando…" : "Sync ahora"}
        </Button>
      </div>

      {state.last_error && (
        <div
          className="mt-3 flex items-start gap-2 p-2 rounded-md
                        border border-danger/30 bg-danger/10 text-xs text-danger"
        >
          <Icon name="alert" size={13} className="mt-0.5 shrink-0" />
          <span className="break-all">{state.last_error}</span>
        </div>
      )}
    </Surface>
  );
}

/* ── INTERVAL CONTROL ─────────────────────────────────────────────── */
// Permite editar `sync_interval_s` desde la UI. Acepta 10..3600 s y
// guarda solo cuando cambia respecto al valor del backend, para evitar
// PUTs ruidosos cuando el usuario abre/cierra el panel.
function IntervalControl({
  value,
  disabled,
  onSave,
}: {
  value: number;
  disabled: boolean;
  onSave: (s: number) => void;
}) {
  const [draft, setDraft] = useState<string>(String(value));
  useEffect(() => {
    setDraft(String(value));
  }, [value]);

  const parsed = Number(draft);
  const isValid = Number.isFinite(parsed) && parsed >= 10 && parsed <= 3600;
  const dirty = isValid && parsed !== value;

  function commit() {
    if (!dirty) return;
    onSave(Math.round(parsed));
  }

  return (
    <Surface level={2} className="p-3 bg-bg/40">
      <div className="text-[10px] uppercase tracking-[0.18em] text-text-dim">Sync cada</div>
      <div className="mt-1 flex items-center gap-1.5">
        <input
          type="number"
          min={10}
          max={3600}
          step={5}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
          }}
          disabled={disabled}
          className="w-16 px-2 py-1 rounded-md border border-white/[0.08]
                     bg-bg/40 text-sm font-mono tabular-nums
                     focus:outline-none focus:border-acc/60"
        />
        <span className="text-[11px] text-text-dim">seg</span>
        {dirty && (
          <button
            onClick={commit}
            disabled={disabled || !isValid}
            className="ml-auto px-2 py-1 rounded-md text-[11px]
                       border border-acc/40 bg-acc/10 text-acc
                       hover:bg-acc/20 disabled:opacity-40 transition-colors"
          >
            Guardar
          </button>
        )}
      </div>
      {!isValid && <div className="mt-1 text-[10px] text-danger">10 – 3600 s</div>}
    </Surface>
  );
}

function formatAge(iso: string): string {
  const past = new Date(iso).getTime();
  if (isNaN(past)) return iso;
  const secs = Math.max(0, Math.floor((Date.now() - past) / 1000));
  if (secs < 60) return `hace ${secs}s`;
  if (secs < 3600) return `hace ${Math.floor(secs / 60)} min`;
  return `hace ${Math.floor(secs / 3600)} h`;
}

/* tiny per-component id helper for the SVG gradient URLs */
let _sparkSeq = 0;
function useStableId(): number {
  // We don't need React.useId (TS lib level) — a module-scoped counter is fine
  // since SVG <defs> ids only need to be unique on the page at a given moment.

  const [id] = useState(() => ++_sparkSeq);
  return id;
}

/* ── EXPORT MENU ──────────────────────────────────────────────────── */
// Mini dropdown que ofrece CSV / XLSX. Usa <a download> directo así no
// inflamos el cliente con blobs en memoria — el browser dispara la
// descarga en streaming desde el endpoint.
function ExportMenu() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    function close(e: MouseEvent) {
      const t = e.target as HTMLElement;
      if (!t.closest("[data-export-menu]")) setOpen(false);
    }
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, [open]);

  return (
    <div className="relative" data-export-menu>
      <Button
        variant="ghost"
        size="sm"
        icon="download"
        onClick={() => setOpen((o) => !o)}
        title="Descargar histórico de sensores"
      >
        Exportar
      </Button>
      {open && (
        <div
          className="absolute right-0 top-full mt-1.5 z-30 min-w-[200px]
                     rounded-lg border border-white/[0.08] bg-elevated/95
                     backdrop-blur-md shadow-xl p-1.5 animate-fade-in"
        >
          <a
            href="/api/iot/sensor_log/xlsx"
            download
            onClick={() => setOpen(false)}
            className="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm text-text
                       hover:bg-white/[0.06] transition-colors"
          >
            <Icon name="chart" size={14} className="text-acc" />
            <div className="flex-1">
              <div className="leading-tight">Excel (.xlsx)</div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-muted">
                una hoja por sensor
              </div>
            </div>
          </a>
          <a
            href="/api/iot/sensor_log/csv"
            download
            onClick={() => setOpen(false)}
            className="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm text-text
                       hover:bg-white/[0.06] transition-colors"
          >
            <Icon name="download" size={14} className="text-text-dim" />
            <div className="flex-1">
              <div className="leading-tight">CSV (.csv)</div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-muted">tabla cruda</div>
            </div>
          </a>
        </div>
      )}
    </div>
  );
}
