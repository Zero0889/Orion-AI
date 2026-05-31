/**
 * IoTPanel — dashboard de domótica.
 *
 * Tres bloques:
 *   - Dispositivos con sus capabilities → switches on/off, slider dim,
 *     selector RGB rápido.
 *   - Escenas configuradas → botón "Ejecutar".
 *   - Sensores con valor actual (cacheado en backend, vivo via WS).
 *
 * Las acciones disparan ``iot_control`` en el backend — el mismo punto
 * de entrada que usa Gemini Live. Refresca al recibir ``iot.action``.
 */

import { useEffect, useState } from "react";

import { api, type IoTDevice, type IoTScene, type IoTSensor } from "@/api/rest";
import { useOrionStore } from "@/stores/orion";

const QUICK_COLORS = [
  { name: "rojo",     hex: "#ff2a4d" },
  { name: "verde",    hex: "#33ff99" },
  { name: "azul",     hex: "#3366ff" },
  { name: "naranja",  hex: "#ff6b1a" },
  { name: "morado",   hex: "#aa44ff" },
  { name: "blanco",   hex: "#ffffff" },
];

export function IoTPanel() {
  const rev = useOrionStore((s) => s.rev.iot);
  const sensorsLive = useOrionStore((s) => s.iotSensors);
  const [devices, setDevices] = useState<IoTDevice[]>([]);
  const [scenes,  setScenes]  = useState<IoTScene[]>([]);
  const [sensors, setSensors] = useState<Record<string, IoTSensor>>({});
  const [error,   setError]   = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    Promise.all([api.iotDevices(), api.iotScenes(), api.iotSensors()])
      .then(([d, s, se]) => { if (alive) { setDevices(d); setScenes(s); setSensors(se); setError(null); } })
      .catch((e) => { if (alive) setError(String(e)); });
    return () => { alive = false; };
  }, [rev]);

  async function act(deviceId: string, body: { action: string; value?: number; color?: string; duration?: number }) {
    try { await api.iotAction(deviceId, body); }
    catch (e) { setError(String(e)); }
  }

  async function runScene(sceneId: string) {
    try { await api.iotRunScene(sceneId); }
    catch (e) { setError(String(e)); }
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto scrollbar-thin">
      <header className="px-6 py-4 border-b border-border-b">
        <h2 className="text-sm uppercase tracking-[0.3em] text-text-dim">IoT</h2>
        <p className="text-xs text-text-dim/70 mt-1">
          Dispositivos conectados, escenas y sensores en directo.
        </p>
      </header>

      {error && (
        <div className="mx-6 mt-3 p-2 text-xs rounded border border-pri bg-pri/10 text-pri">
          {error}
        </div>
      )}

      {/* Devices */}
      <section className="p-6">
        <h3 className="text-xs uppercase tracking-widest text-text-dim mb-3">Dispositivos</h3>
        {devices.length === 0 ? (
          <p className="text-text-dim text-sm italic">Sin dispositivos configurados.</p>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {devices.map((d) => (
              <DeviceCard key={d.id} dev={d} onAct={act} />
            ))}
          </div>
        )}
      </section>

      {/* Scenes */}
      <section className="px-6 pb-6">
        <h3 className="text-xs uppercase tracking-widest text-text-dim mb-3">Escenas</h3>
        {scenes.length === 0 ? (
          <p className="text-text-dim text-sm italic">Sin escenas configuradas.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {scenes.map((s) => (
              <button
                key={s.id}
                onClick={() => runScene(s.id)}
                className="px-3 py-1.5 rounded-md border border-border-b bg-panel2
                           text-sm hover:border-pri hover:text-pri transition"
                title={`${s.steps} paso${s.steps === 1 ? "" : "s"}`}
              >
                {s.name}
              </button>
            ))}
          </div>
        )}
      </section>

      {/* Sensors */}
      <section className="px-6 pb-6">
        <h3 className="text-xs uppercase tracking-widest text-text-dim mb-3">Sensores</h3>
        {Object.keys(sensors).length === 0 && Object.keys(sensorsLive).length === 0 ? (
          <p className="text-text-dim text-sm italic">Sin lecturas de sensores aún.</p>
        ) : (
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-2">
            {Object.entries({ ...sensors, ...sensorsLive }).map(([devId, s]) => {
              // s puede ser IoTSensor o {value, ts}
              const value = "value" in s ? s.value : "";
              return (
                <div key={devId} className="rounded-md border border-border-b bg-panel2 p-3">
                  <div className="text-[10px] uppercase tracking-widest text-text-dim">{devId}</div>
                  <div className="text-lg font-mono tabular-nums text-pri">{value}</div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}

function DeviceCard({
  dev, onAct,
}: {
  dev: IoTDevice;
  onAct: (id: string, body: { action: string; value?: number; color?: string; duration?: number }) => void;
}) {
  const [dim, setDim] = useState(50);
  const caps = dev.capabilities;

  return (
    <article className="rounded-lg border border-border-b bg-panel2 p-4">
      <header className="flex items-center justify-between mb-2">
        <h4 className="font-medium">{dev.name}</h4>
        <code className="text-[10px] font-mono text-text-dim">{dev.transport}</code>
      </header>
      <p className="text-[10px] uppercase tracking-widest text-text-dim mb-3">
        {[
          caps.on_off   && "on/off",
          caps.dimmable && "dim",
          caps.rgb      && "rgb",
          caps.sensor   && `sensor:${caps.sensor}`,
        ].filter(Boolean).join(" · ") || "—"}
      </p>

      {caps.on_off && (
        <div className="flex gap-2 mb-2">
          <button
            onClick={() => onAct(dev.id, { action: "on"  })}
            className="flex-1 rounded-md bg-pri text-bg text-sm py-1.5 hover:brightness-110"
          >Encender</button>
          <button
            onClick={() => onAct(dev.id, { action: "off" })}
            className="flex-1 rounded-md border border-border-b text-sm py-1.5 hover:border-pri"
          >Apagar</button>
        </div>
      )}

      {caps.dimmable && (
        <div className="flex items-center gap-2 mb-2">
          <input
            type="range" min={0} max={100} value={dim}
            onChange={(e) => setDim(Number(e.target.value))}
            onMouseUp={() => onAct(dev.id, { action: "dim", value: dim })}
            onTouchEnd={() => onAct(dev.id, { action: "dim", value: dim })}
            className="flex-1 accent-pri"
          />
          <span className="text-xs font-mono tabular-nums w-10 text-right">{dim}%</span>
        </div>
      )}

      {caps.rgb && (
        <div className="flex gap-1.5 flex-wrap mt-2">
          {QUICK_COLORS.map((c) => (
            <button
              key={c.name}
              onClick={() => onAct(dev.id, { action: "rgb", color: c.name })}
              className="w-6 h-6 rounded-full border border-border-b hover:scale-110 transition"
              style={{ background: c.hex }}
              title={c.name}
            />
          ))}
        </div>
      )}
    </article>
  );
}
