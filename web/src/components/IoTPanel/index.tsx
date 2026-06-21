/**
 * IoTPanel — smart-home dashboard.
 *
 * Tres secciones (Devices / Scenes / Sensors). Devices renderizan cards
 * premium con capability chips, on/off switch, dim slider, swatches RGB,
 * botón edit hover-revealed, y sparklines inline cuando el user activó
 * "show graph" para ese device.
 *
 * Dispositivos definidos localmente (ver `useDeviceConfig`) se mergean
 * con el catálogo backend y reciben badge "Local". Sus acciones siguen
 * yendo al mismo /api/iot/devices/{id}/action — registrarlos en backend
 * después es solo registrar el mismo id.
 *
 * Estructura (Fase 4):
 *   - index.tsx (este archivo) — shell + Subhead + secciones
 *   - DeviceCard.tsx — DeviceCard + SensorReadout + RangeBar + Sparkline + QUICK_COLORS
 *   - SheetsPanel.tsx — sync continuo con Google Sheets + IntervalControl + formatAge
 *   - ExportMenu.tsx — dropdown de descarga CSV/XLSX
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { api, type IoTDevice, type IoTScene, type IoTSensor } from "@/api/rest";
import { DeviceFormModal } from "@/components/DeviceFormModal";
import { GogScopeGuard } from "@/components/GogScopeGuard";
import { useDeviceConfig, type LocalDevice } from "@/hooks/useDeviceConfig";
import { QUERY_KEYS } from "@/query/keys";
import { useOrionStore } from "@/stores/orion";
import { Icon } from "@/ui/Icon";
import { Badge, Button, Empty, SectionHeader, Surface } from "@/ui/primitives";

import { DeviceCard } from "./DeviceCard";
import { ExportMenu } from "./ExportMenu";
import { SheetsPanel } from "./SheetsPanel";

export function IoTPanel() {
  const queryClient = useQueryClient();
  // `iotSensors` es WS-state (snapshots por evento iot.sensor) y se
  // queda en Zustand. El resto (devices/scenes/sensors-snapshot/paused)
  // pasa a useQuery — el bridge invalida QUERY_KEYS.iot.* por evento
  // iot.action.
  const sensorsLive = useOrionStore((s) => s.iotSensors);
  const cfg = useDeviceConfig();

  const { data: backendDevices = [], error: devicesError } = useQuery<IoTDevice[]>({
    queryKey: QUERY_KEYS.iot.devices,
    queryFn: () => api.iotDevices(),
  });
  const { data: scenes = [], error: scenesError } = useQuery<IoTScene[]>({
    queryKey: QUERY_KEYS.iot.scenes,
    queryFn: () => api.iotScenes(),
  });
  const { data: sensors = {}, error: sensorsError } = useQuery<Record<string, IoTSensor>>({
    queryKey: QUERY_KEYS.iot.sensors,
    queryFn: () => api.iotSensors(),
  });
  const { data: pausedStatus, error: pausedError } = useQuery<{ paused: boolean }>({
    queryKey: QUERY_KEYS.iot.paused,
    queryFn: () => api.iotPausedStatus(),
  });
  const paused = pausedStatus?.paused ?? false;

  const [pausing, setPausing] = useState<boolean>(false);
  const [actError, setActError] = useState<string | null>(null);
  const queryError = devicesError ?? scenesError ?? sensorsError ?? pausedError;
  const error = actError ?? (queryError ? String(queryError) : null);

  // modal
  const [editing, setEditing] = useState<IoTDevice | LocalDevice | undefined>(undefined);
  const [modalOpen, setModalOpen] = useState(false);

  async function togglePause() {
    setPausing(true);
    try {
      await (paused ? api.iotConnect() : api.iotDisconnect());
      await queryClient.invalidateQueries({ queryKey: QUERY_KEYS.iot.all });
    } catch (e) {
      setActError(String(e));
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
      setActError(String(e));
    }
  }
  async function runScene(sceneId: string) {
    try {
      await api.iotRunScene(sceneId);
    } catch (e) {
      setActError(String(e));
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
        onSaved={() => queryClient.invalidateQueries({ queryKey: QUERY_KEYS.iot.all })}
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
