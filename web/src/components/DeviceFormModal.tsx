/**
 * DeviceFormModal — crear / editar / inspeccionar dispositivos IoT.
 *
 * Cambios v2 (refactor enero 2026):
 *
 *   ✓ Selector de TIPO DE TRANSPORTE (ESP32-MQTT / Arduino-Serial / Custom)
 *     con campos condicionales: COM+baud para serial, host+port+topics para MQTT.
 *   ✓ Auto-save para edición de dispositivos backend (no hay que dar a
 *     "Guardar" para que se persistan los overrides locales).
 *   ✓ Persistencia REAL al backend para Crear / Editar / Borrar dispositivos
 *     definidos por el usuario — escribe `iot_config.json` y recarga el
 *     IoTSystem en caliente. Los "Local" del localStorage siguen ahí pero
 *     ahora se pueden promover al backend con un click.
 *   ✓ Inputs numéricos sin spinners nativos (CSS global) y con quick-picks
 *     que aplican el cambio al instante.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  api,
  type IoTCapabilities,
  type IoTDevice,
  type IoTDeviceBody,
  type IoTFullConfig,
  type IoTTransportBody,
} from "@/api/rest";
import { Icon, type IconName } from "@/ui/Icon";
import { Badge, Button, Field, Modal, Surface, Switch, TextInput } from "@/ui/primitives";
import {
  SENSOR_FREQ_REC,
  type DeviceConfig,
  type LocalDevice,
  type SensorKind,
} from "@/hooks/useDeviceConfig";

type Mode = "create" | "edit-local" | "edit-backend";
type TransportType = "mqtt" | "serial" | "custom";

/** Palabras que sugieren "esto es una luz/foco" cuando solo tenemos
 *  on/off y no podemos distinguir entre foco e interruptor por capabilities. */
const LIGHT_HINTS = /\b(foco|luz|lampar|bombill|light|lamp|spot|led)\w*/i;

interface Props {
  open: boolean;
  onClose: () => void;
  device?: IoTDevice | LocalDevice;
  config?: DeviceConfig;

  /** Llamado tras éxito en backend o tras escribir local. */
  onSaved?: () => void;
  onSubmitLocal: (dev: LocalDevice, cfg: DeviceConfig) => void;
  onSubmitConfig: (id: string, cfg: DeviceConfig, displayName?: string) => void;
  onDeleteLocal?: (id: string) => void;
}

/* ── presets ──────────────────────────────────────────────────────── */
type DeviceKind = "light" | "switch" | "sensor" | "mixed";

const DEVICE_KINDS: { id: DeviceKind; label: string; icon: IconName; hint: string }[] = [
  { id: "light", label: "Foco / luz", icon: "lightbulb", hint: "Encendido, regulable, RGB" },
  { id: "switch", label: "Interruptor", icon: "bolt", hint: "Solo on/off" },
  { id: "sensor", label: "Sensor", icon: "gauge", hint: "Lecturas numéricas" },
  { id: "mixed", label: "Mixto / avanzado", icon: "cpu", hint: "Combinación libre" },
];

const SENSOR_PRESETS: { id: SensorKind; label: string; icon: IconName; backendId: string }[] = [
  { id: "temperature", label: "Temperatura", icon: "thermometer", backendId: "temperature" },
  { id: "humidity", label: "Humedad", icon: "droplet", backendId: "humidity" },
  { id: "pressure", label: "Presión", icon: "gauge", backendId: "pressure" },
  { id: "light", label: "Luminosidad", icon: "sun", backendId: "light" },
  { id: "motion", label: "Movimiento", icon: "motion", backendId: "motion" },
  { id: "co2", label: "Calidad aire", icon: "wind", backendId: "co2" },
  { id: "custom", label: "Personalizado", icon: "tag", backendId: "" },
];

const TRANSPORT_KINDS: { id: TransportType; label: string; icon: IconName; hint: string }[] = [
  { id: "mqtt", label: "ESP32 (MQTT)", icon: "wifi", hint: "WiFi, broker MQTT" },
  { id: "serial", label: "Arduino (Serial)", icon: "bolt", hint: "USB, puerto COM" },
  {
    id: "custom",
    label: "Otro / existente",
    icon: "cpu",
    hint: "Transport ya definido en el backend",
  },
];

/* ── helpers ──────────────────────────────────────────────────────── */
function slugify(s: string): string {
  return s
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 32);
}

function kindFromDevice(d?: IoTDevice, cfg?: DeviceConfig): DeviceKind {
  // Si el usuario ya eligió un kind manualmente, respétalo siempre.
  if (cfg?.kind) return cfg.kind;
  if (!d) return "light";
  const c = d.capabilities;
  if (c.sensor) return "sensor";
  if (c.rgb || c.dimmable) return "light";
  if (c.on_off && !c.dimmable && !c.rgb) {
    // Heurística por nombre/id: "foco", "luz", "lampara"... → light
    const hint = `${d.name ?? ""} ${d.id ?? ""}`;
    return LIGHT_HINTS.test(hint) ? "light" : "switch";
  }
  return "mixed";
}

function isObj(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

/* ── component ────────────────────────────────────────────────────── */
export function DeviceFormModal({
  open,
  onClose,
  device,
  config,
  onSaved,
  onSubmitConfig,
  onDeleteLocal,
}: Props) {
  const isLocal = !!(device as LocalDevice | undefined)?.__local;
  const mode: Mode = !device ? "create" : isLocal ? "edit-local" : "edit-backend";

  // form state ──────────────────────────────────────────────────────
  const [kind, setKind] = useState<DeviceKind>(kindFromDevice(device, config));
  const [name, setName] = useState(device?.name ?? "");
  const [id, setId] = useState(device?.id ?? "");
  const [idTouched, setIdTouched] = useState(!!device);
  const [caps, setCaps] = useState<IoTCapabilities>(
    device?.capabilities ?? { on_off: true, dimmable: false, rgb: false, sensor: null },
  );
  const [sensorKind, setSensorKind] = useState<SensorKind>(
    config?.sensorKind ??
      SENSOR_PRESETS.find((p) => p.backendId === device?.capabilities.sensor)?.id ??
      "temperature",
  );
  const [customSensor, setCustomSensor] = useState<string>(
    device?.capabilities.sensor &&
      !SENSOR_PRESETS.some((p) => p.backendId === device.capabilities.sensor)
      ? device.capabilities.sensor
      : "",
  );
  const [displayName, setDisplayName] = useState(config?.displayName ?? "");
  const [updateFreq, setUpdateFreq] = useState<number>(
    config?.updateFreqS ?? SENSOR_FREQ_REC[sensorKind].value,
  );
  const [showGraph, setShowGraph] = useState<boolean>(config?.showGraph ?? false);

  // transport state ─────────────────────────────────────────────────
  const [transportType, setTransportType] = useState<TransportType>("mqtt");
  const [transportId, setTransportId] = useState(device?.transport ?? "esp32_mqtt");
  const [serialPort, setSerialPort] = useState("COM3");
  const [serialBaud, setSerialBaud] = useState(9600);
  const [mqttHost, setMqttHost] = useState("broker.hivemq.com");
  const [mqttPort, setMqttPort] = useState(1883);
  // per-device transport-specific config
  const [topicCommand, setTopicCommand] = useState("");
  const [topicState, setTopicState] = useState("");
  const [sensorField, setSensorField] = useState("");
  const [payloadOn, setPayloadOn] = useState("ON");
  const [payloadOff, setPayloadOff] = useState("OFF");
  const [cmdOn, setCmdOn] = useState("");
  const [cmdOff, setCmdOff] = useState("");
  const [serialSensorPrefix, setSerialSensorPrefix] = useState("");

  // backend full config (para listar transports existentes en custom)
  const [fullCfg, setFullCfg] = useState<IoTFullConfig | null>(null);

  // Ref del config para que el effect de reset NO se re-dispare cada vez
  // que el auto-save toca cfg.configs[id] (eso crea una nueva referencia,
  // y si "config" estuviera en deps, el reset borraría lo que el usuario
  // acaba de cambiar — bug clásico).
  const configRef = useRef(config);
  useEffect(() => {
    configRef.current = config;
  }, [config]);

  // bookkeeping
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<{
    name?: string;
    id?: string;
    transport?: string;
    submit?: string;
  }>({});

  /* ── reset SOLO cuando el modal se abre o cambia el device ───
   *  Importante: NO depende de `config` (lo leemos via configRef) — si
   *  estuviera en deps, cada auto-save dispararía un reset y borraría lo
   *  que el usuario acaba de cambiar (p. ej. el transportType). */
  useEffect(() => {
    if (!open) return;
    const cfg = configRef.current; // snapshot fresco al abrir

    setKind(kindFromDevice(device, cfg));
    setName(device?.name ?? "");
    setId(device?.id ?? "");
    setIdTouched(!!device);
    setCaps(device?.capabilities ?? { on_off: true, dimmable: false, rgb: false, sensor: null });
    const sk =
      cfg?.sensorKind ??
      SENSOR_PRESETS.find((p) => p.backendId === device?.capabilities.sensor)?.id ??
      "temperature";
    setSensorKind(sk);
    setCustomSensor(
      device?.capabilities.sensor &&
        !SENSOR_PRESETS.some((p) => p.backendId === device.capabilities.sensor)
        ? device.capabilities.sensor
        : "",
    );
    setDisplayName(cfg?.displayName ?? "");
    setUpdateFreq(cfg?.updateFreqS ?? SENSOR_FREQ_REC[sk].value);
    setShowGraph(cfg?.showGraph ?? false);

    // Transport: usa el TYPE del transport actual del device si lo conocemos
    // (de fullCfg), si no cae en la heurística de bloques mqtt/serial del device.
    const devMqtt = isObj(device?.mqtt) ? device!.mqtt! : {};
    const devSerial = isObj(device?.serial) ? device!.serial! : {};
    if (Object.keys(devMqtt).length) setTransportType("mqtt");
    else if (Object.keys(devSerial).length) setTransportType("serial");
    else setTransportType("mqtt");

    setTransportId(device?.transport ?? "esp32_mqtt");
    setTopicCommand((devMqtt.topic_command as string) ?? "");
    setTopicState((devMqtt.topic_state as string) ?? "");
    setSensorField((devMqtt.sensor_field as string) ?? "");
    setPayloadOn((devMqtt.payload_on as string) ?? "ON");
    setPayloadOff((devMqtt.payload_off as string) ?? "OFF");
    setCmdOn((devSerial.cmd_on as string) ?? "");
    setCmdOff((devSerial.cmd_off as string) ?? "");
    setSerialSensorPrefix((devSerial.sensor_prefix as string) ?? "");

    setErrors({});

    // Cargar el config completo del backend para conocer transports existentes
    api
      .iotConfig()
      .then(setFullCfg)
      .catch(() => setFullCfg(null));
  }, [open, device]);

  // Cuando el usuario elige un transport existente, precarga su host/port
  useEffect(() => {
    if (!fullCfg || transportType === "custom") return;
    const candidate = fullCfg.transports[transportId];
    if (!candidate) return;
    if (transportType === "mqtt" && candidate.type === "mqtt") {
      if (typeof candidate.host === "string") setMqttHost(candidate.host);
      if (typeof candidate.port === "number") setMqttPort(candidate.port);
    } else if (transportType === "serial" && candidate.type === "serial") {
      if (typeof candidate.port === "string") setSerialPort(candidate.port);
      if (typeof candidate.baud === "number") setSerialBaud(candidate.baud);
    }
  }, [fullCfg, transportId, transportType]);

  // Reconciliar transportType con el TYPE REAL del transport actual,
  // una sola vez al abrir (cuando fullCfg termine de cargar). Sin esto,
  // un device con bloque mqtt+serial cargado se vería siempre como mqtt
  // aunque su transport sea de tipo serial.
  const transportReconciled = useRef(false);
  useEffect(() => {
    transportReconciled.current = false;
  }, [open, device]);
  useEffect(() => {
    if (!open || !device || !fullCfg) return;
    if (transportReconciled.current) return;
    const real = fullCfg.transports[device.transport];
    if (!real) return;
    transportReconciled.current = true;
    if (real.type === "serial" || real.type === "mqtt") {
      setTransportType(real.type);
    }
  }, [open, device, fullCfg]);

  // ── auto-slug id desde el nombre (solo en create) ──────────────
  useEffect(() => {
    if (!idTouched && mode === "create") setId(slugify(name));
  }, [name, idTouched, mode]);

  // ── auto-save de overrides locales para dispositivos backend ───
  // Cuando estás editando un device del backend, los cambios en
  // displayName / updateFreq / showGraph / sensorKind se guardan
  // automáticamente con debounce de 250 ms. Así nunca pierdes un cambio
  // por olvidar el botón "Guardar".
  const isBackendEdit = mode === "edit-backend";
  const autoSaveTimer = useRef<number | undefined>(undefined);
  const firstAutoSave = useRef(true);
  useEffect(() => {
    if (!open || !isBackendEdit || !device) return;
    // No dispara el primer render — solo cuando algo cambia de verdad
    if (firstAutoSave.current) {
      firstAutoSave.current = false;
      return;
    }
    window.clearTimeout(autoSaveTimer.current);
    autoSaveTimer.current = window.setTimeout(() => {
      onSubmitConfig(
        device.id,
        {
          displayName: displayName.trim() || undefined,
          updateFreqS: updateFreq,
          showGraph,
          sensorKind,
          kind,
        },
        displayName.trim() || undefined,
      );
    }, 250);
    return () => window.clearTimeout(autoSaveTimer.current);
  }, [
    open,
    isBackendEdit,
    device,
    displayName,
    updateFreq,
    showGraph,
    sensorKind,
    kind,
    onSubmitConfig,
  ]);

  // Cuando se cierra el modal, resetea la guard de first-render para
  // que la próxima apertura no auto-guarde un cambio fantasma
  useEffect(() => {
    if (!open) firstAutoSave.current = true;
  }, [open]);

  function pickSensorKind(k: SensorKind) {
    setSensorKind(k);
    if (mode === "create") setUpdateFreq(SENSOR_FREQ_REC[k].value);
  }

  function pickKind(k: DeviceKind) {
    setKind(k);
    if (k === "light") {
      setCaps({ on_off: true, dimmable: true, rgb: true, sensor: null });
    } else if (k === "switch") {
      setCaps({ on_off: true, dimmable: false, rgb: false, sensor: null });
    } else if (k === "sensor") {
      setCaps({
        on_off: false,
        dimmable: false,
        rgb: false,
        sensor: SENSOR_PRESETS.find((p) => p.id === sensorKind)?.backendId || "temperature",
      });
      setShowGraph(true);
    } else {
      setCaps({ on_off: true, dimmable: false, rgb: false, sensor: null });
    }
  }

  const isSensor = !!caps.sensor || kind === "sensor";

  function toggleCap(k: keyof IoTCapabilities) {
    setCaps((c) => {
      if (k === "sensor") {
        return {
          ...c,
          sensor: c.sensor
            ? null
            : SENSOR_PRESETS.find((p) => p.id === sensorKind)?.backendId || "temperature",
        };
      }
      return { ...c, [k]: !c[k] };
    });
  }

  /* ── persistencia BACKEND (crear/editar/borrar real) ─────────── */
  const persistToBackend = useCallback(async (): Promise<boolean> => {
    setErrors({});
    const errs: typeof errors = {};
    const finalId = id.trim() || slugify(name);

    if (!name.trim()) errs.name = "Pon un nombre.";
    if (!finalId) errs.id = "Necesita un identificador.";
    if (finalId && /[^a-z0-9_]/i.test(finalId)) errs.id = "Solo letras, números y _.";

    if (transportType !== "custom" && !transportId.trim()) {
      errs.transport = "Necesita un ID de transporte.";
    }

    if (Object.keys(errs).length) {
      setErrors(errs);
      return false;
    }

    setSubmitting(true);
    try {
      // 1. Si vamos a crear/actualizar un transport, hazlo primero
      if (transportType === "mqtt") {
        const tBody: IoTTransportBody = {
          type: "mqtt",
          host: mqttHost.trim(),
          mqtt_port: mqttPort,
          client_id: "orion",
        };
        await api.iotUpsertTransport(transportId.trim(), tBody);
      } else if (transportType === "serial") {
        const tBody: IoTTransportBody = {
          type: "serial",
          port: serialPort.trim(),
          baud: serialBaud,
        };
        await api.iotUpsertTransport(transportId.trim(), tBody);
      }

      // 2. Capabilities finales
      const finalSensor = isSensor
        ? sensorKind === "custom"
          ? customSensor.trim() || "custom"
          : SENSOR_PRESETS.find((p) => p.id === sensorKind)?.backendId || "custom"
        : null;
      const finalCaps: IoTCapabilities = {
        on_off: isSensor ? false : !!caps.on_off,
        dimmable: isSensor ? false : !!caps.dimmable,
        rgb: isSensor ? false : !!caps.rgb,
        sensor: finalSensor,
      };

      // 3. Construimos AMBOS bloques (mqtt y serial) desde el estado actual
      //    del formulario. Solo el bloque correspondiente al transport
      //    activo se usa en runtime; el otro queda "dormido" y se preserva
      //    para que cuando cambies de modo no pierdas la config anterior.
      const mqttBlock: Record<string, unknown> = {};
      const serialBlock: Record<string, unknown> = {};

      if (topicCommand.trim()) mqttBlock.topic_command = topicCommand.trim();
      if (topicState.trim()) mqttBlock.topic_state = topicState.trim();
      if (sensorField.trim()) mqttBlock.sensor_field = sensorField.trim();
      if (finalCaps.on_off) {
        mqttBlock.payload_on = payloadOn || "ON";
        mqttBlock.payload_off = payloadOff || "OFF";
      }

      if (finalCaps.on_off) {
        serialBlock.cmd_on = cmdOn || `${finalId.toUpperCase()}_ON`;
        serialBlock.cmd_off = cmdOff || `${finalId.toUpperCase()}_OFF`;
      }
      if (finalCaps.sensor && serialSensorPrefix.trim()) {
        serialBlock.sensor_prefix = serialSensorPrefix.trim();
      }

      const body: IoTDeviceBody = {
        name: name.trim(),
        transport: transportId.trim(),
        capabilities: finalCaps,
        ...(Object.keys(mqttBlock).length && { mqtt: mqttBlock }),
        ...(Object.keys(serialBlock).length && { serial: serialBlock }),
      };

      if (mode === "edit-backend") {
        await api.iotUpdateDevice(device!.id, body);
      } else {
        await api.iotCreateDevice({ ...body, id: finalId });
      }

      // 4. Persistir overrides locales también (frecuencia/gráfico/kind)
      onSubmitConfig(finalId, {
        displayName: displayName.trim() || undefined,
        updateFreqS: updateFreq,
        showGraph: isSensor ? showGraph : false,
        sensorKind: isSensor ? sensorKind : undefined,
        kind,
      });

      onSaved?.();
      return true;
    } catch (e) {
      setErrors({ submit: String(e instanceof Error ? e.message : e) });
      return false;
    } finally {
      setSubmitting(false);
    }
  }, [
    id,
    name,
    transportType,
    transportId,
    mqttHost,
    mqttPort,
    serialPort,
    serialBaud,
    topicCommand,
    topicState,
    sensorField,
    payloadOn,
    payloadOff,
    cmdOn,
    cmdOff,
    serialSensorPrefix,
    caps,
    isSensor,
    sensorKind,
    customSensor,
    displayName,
    updateFreq,
    showGraph,
    mode,
    device,
    kind,
    onSaved,
    onSubmitConfig,
  ]);

  /* ── borrar device del backend ───────────────────────────────── */
  async function deleteFromBackend() {
    if (!device) return;
    if (
      !confirm(
        `¿Borrar el dispositivo "${device.name}" del backend?\n\nEsto edita iot_config.json y reinicia las conexiones del transport.`,
      )
    )
      return;
    setSubmitting(true);
    try {
      await api.iotDeleteDevice(device.id);
      onSaved?.();
      onClose();
    } catch (e) {
      setErrors({ submit: String(e instanceof Error ? e.message : e) });
    } finally {
      setSubmitting(false);
    }
  }

  /* ── submit (router según el modo) ───────────────────────────── */
  async function submit() {
    if (mode === "edit-backend") {
      // Los overrides ya se auto-guardan; lo que el botón "Guardar" hace
      // aquí es PROMOVER cambios en transport/capabilities/topics al
      // backend (solo si el usuario los editó). Mostramos la modal de
      // edición backend ahora también con campos editables.
      const ok = await persistToBackend();
      if (ok) onClose();
      return;
    }

    if (mode === "create") {
      const ok = await persistToBackend();
      if (ok) onClose();
      return;
    }

    // edit-local fallback (legado): aún soportado para devices ya creados
    // antes del refactor — los promueve al backend en cuanto el usuario
    // clicka Guardar.
    const ok = await persistToBackend();
    if (ok) {
      // Si el promote fue exitoso, también borra de localStorage para no
      // duplicarlo en la UI
      if (device && onDeleteLocal) onDeleteLocal(device.id);
      onClose();
    }
  }

  // OJO: NO envolvemos esto en useMemo. El `submit` y `deleteFromBackend`
  // cierran sobre `name`, `id`, `caps`, etc. — si memoizamos sin meter todo
  // eso en deps, el botón Save guarda valores viejos (stale closure clásico).
  // Recalcular el footer cada render es trivialmente barato.
  const footer = (
    <>
      {(mode === "edit-local" || mode === "edit-backend") && (
        <Button
          variant="danger"
          size="md"
          icon="trash"
          disabled={submitting}
          onClick={() => {
            if (mode === "edit-local" && onDeleteLocal) {
              if (confirm(`¿Borrar el dispositivo local "${device?.name}"?`)) {
                onDeleteLocal(device!.id);
                onClose();
              }
            } else {
              deleteFromBackend();
            }
          }}
          className="mr-auto"
        >
          Borrar
        </Button>
      )}
      <Button variant="ghost" size="md" onClick={onClose} disabled={submitting}>
        Cancelar
      </Button>
      <Button variant="primary" size="md" icon="save" onClick={submit} loading={submitting}>
        {mode === "create" ? "Crear dispositivo" : "Guardar cambios"}
      </Button>
    </>
  );

  return (
    <Modal
      open={open}
      onClose={onClose}
      eyebrow={
        mode === "create" ? "Nuevo dispositivo" : isLocal ? "Editar (local)" : "Editar dispositivo"
      }
      title={
        mode === "create"
          ? "Añadir un dispositivo IoT"
          : displayName || device?.name || "Dispositivo"
      }
      size="lg"
      footer={footer}
    >
      <div className="space-y-6">
        {errors.submit && (
          <Surface
            level={2}
            className="flex items-start gap-3 p-3 border border-danger/30 bg-danger/10"
          >
            <Icon name="alert" size={14} className="text-danger shrink-0 mt-0.5" />
            <span className="text-xs text-danger">{errors.submit}</span>
          </Surface>
        )}

        {isBackendEdit && (
          <Surface level={2} className="flex items-start gap-3 p-3.5">
            <Icon name="info" size={16} className="text-pri shrink-0 mt-0.5" />
            <p className="text-xs text-text-dim leading-relaxed">
              Los cambios de <b>frecuencia</b>, <b>gráfico</b> y <b>nombre visible</b> se guardan
              automáticamente al instante (no necesitas el botón). El botón
              <b> Guardar cambios</b> aplica modificaciones de transporte y capabilities al
              <code className="mx-1 font-mono">iot_config.json</code>y reconecta el transport en
              caliente.
            </p>
          </Surface>
        )}

        {/* TIPO DE DISPOSITIVO */}
        <Field label="Tipo de dispositivo">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {DEVICE_KINDS.map((k) => {
              const active = kind === k.id;
              return (
                <button
                  key={k.id}
                  type="button"
                  onClick={() => pickKind(k.id)}
                  className={[
                    "group relative rounded-xl border p-3 text-left transition-all duration-200 ease-out-expo",
                    active
                      ? "bg-pri/10 border-pri/40 shadow-glow-soft"
                      : "bg-elevated/40 border-white/[0.06] hover:border-white/[0.14]",
                  ].join(" ")}
                >
                  <Icon name={k.icon} size={18} className={active ? "text-pri" : "text-text-dim"} />
                  <div className="mt-2 text-sm font-medium text-text leading-tight">{k.label}</div>
                  <div className="text-[10px] text-muted mt-0.5">{k.hint}</div>
                </button>
              );
            })}
          </div>
        </Field>

        {/* NOMBRE / ID */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label="Nombre" error={errors.name}>
            <TextInput
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="p. ej. Foco salón"
            />
          </Field>

          <Field label="Identificador" hint="usa snake_case" error={errors.id}>
            <TextInput
              value={id}
              onChange={(e) => {
                setId(slugify(e.target.value));
                setIdTouched(true);
              }}
              placeholder="foco_salon"
              disabled={mode !== "create"}
            />
          </Field>

          {isBackendEdit && (
            <Field label="Nombre visible (override)" hint="Solo local · auto-guardado">
              <TextInput
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder={device!.name}
              />
            </Field>
          )}
        </div>

        {/* TRANSPORTE — selector */}
        <Field label="Cómo se conecta" hint="esto define cómo el ESP32 / Arduino habla con ORION">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            {TRANSPORT_KINDS.map((t) => {
              const active = transportType === t.id;
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => {
                    setTransportType(t.id);
                    // Sugerir un transport_id sensato según el tipo
                    if (t.id === "mqtt" && !device) setTransportId("esp32_mqtt");
                    if (t.id === "serial" && !device) setTransportId("main_arduino");
                  }}
                  className={[
                    "rounded-xl border p-3 text-left transition-all duration-200 ease-out-expo",
                    active
                      ? "bg-pri/10 border-pri/40 shadow-glow-soft"
                      : "bg-elevated/40 border-white/[0.06] hover:border-white/[0.14]",
                  ].join(" ")}
                >
                  <div className="flex items-center gap-2">
                    <Icon
                      name={t.icon}
                      size={16}
                      className={active ? "text-pri" : "text-text-dim"}
                    />
                    <span className="text-sm font-medium text-text">{t.label}</span>
                  </div>
                  <div className="text-[10px] text-muted mt-1">{t.hint}</div>
                </button>
              );
            })}
          </div>
        </Field>

        {/* TRANSPORTE — config */}
        {transportType !== "custom" && (
          <Surface level={2} className="p-4 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <Field
                label="ID del transport"
                hint="se reutiliza entre dispositivos"
                error={errors.transport}
              >
                <TextInput
                  value={transportId}
                  onChange={(e) => setTransportId(slugify(e.target.value))}
                  placeholder={transportType === "mqtt" ? "esp32_mqtt" : "main_arduino"}
                />
              </Field>

              {transportType === "mqtt" && (
                <>
                  <Field label="Host del broker">
                    <TextInput
                      value={mqttHost}
                      onChange={(e) => setMqttHost(e.target.value)}
                      placeholder="broker.hivemq.com o 192.168.1.10"
                    />
                  </Field>
                  <Field label="Puerto MQTT">
                    <NumInput value={mqttPort} onChange={setMqttPort} min={1} max={65535} />
                  </Field>
                </>
              )}

              {transportType === "serial" && (
                <>
                  <Field label="Puerto COM" hint="p. ej. COM3 o /dev/ttyUSB0">
                    <TextInput
                      value={serialPort}
                      onChange={(e) => setSerialPort(e.target.value)}
                      placeholder="COM3"
                    />
                  </Field>
                  <Field label="Baud rate">
                    <NumInput value={serialBaud} onChange={setSerialBaud} min={300} max={1000000} />
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {[9600, 19200, 38400, 57600, 115200].map((v) => (
                        <QuickPick
                          key={v}
                          active={serialBaud === v}
                          onClick={() => setSerialBaud(v)}
                          label={`${v}`}
                        />
                      ))}
                    </div>
                  </Field>
                </>
              )}
            </div>
          </Surface>
        )}

        {transportType === "custom" && (
          <Field label="ID del transport existente">
            <TextInput
              value={transportId}
              onChange={(e) => setTransportId(slugify(e.target.value))}
              placeholder="main_arduino"
            />
            {fullCfg && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {Object.keys(fullCfg.transports).map((tid) => (
                  <QuickPick
                    key={tid}
                    active={transportId === tid}
                    onClick={() => setTransportId(tid)}
                    label={`${tid} · ${fullCfg.transports[tid].type as string}`}
                  />
                ))}
              </div>
            )}
          </Field>
        )}

        {/* TOPICS / COMANDOS específicos del device en este transport */}
        {transportType === "mqtt" && (
          <Surface level={2} className="p-4 space-y-3">
            <div className="text-[11px] uppercase tracking-[0.18em] text-text-dim">
              Topics MQTT del dispositivo
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {!isSensor && (
                <Field label="Topic de comandos" hint="ORION publica aquí">
                  <TextInput
                    value={topicCommand}
                    onChange={(e) => setTopicCommand(e.target.value)}
                    placeholder="orion/zahir/foco_1/set"
                  />
                </Field>
              )}
              <Field
                label="Topic de estado / sensor"
                hint={isSensor ? "ESP32 publica aquí" : "ESP32 confirma su estado"}
              >
                <TextInput
                  value={topicState}
                  onChange={(e) => setTopicState(e.target.value)}
                  placeholder={
                    isSensor ? "orion/zahir/esp_sensores/dht" : "orion/zahir/foco_1/state"
                  }
                />
              </Field>
              {isSensor && (
                <Field
                  label="Campo JSON (opcional)"
                  hint="si el payload es JSON y quieres un campo"
                >
                  <TextInput
                    value={sensorField}
                    onChange={(e) => setSensorField(e.target.value)}
                    placeholder="temperatura"
                  />
                </Field>
              )}
              {!isSensor && (
                <>
                  <Field label="Payload encender">
                    <TextInput value={payloadOn} onChange={(e) => setPayloadOn(e.target.value)} />
                  </Field>
                  <Field label="Payload apagar">
                    <TextInput value={payloadOff} onChange={(e) => setPayloadOff(e.target.value)} />
                  </Field>
                </>
              )}
            </div>
          </Surface>
        )}

        {transportType === "serial" && !isSensor && (
          <Surface level={2} className="p-4">
            <div className="text-[11px] uppercase tracking-[0.18em] text-text-dim mb-3">
              Comandos serial
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field label="Comando encender">
                <TextInput
                  value={cmdOn}
                  onChange={(e) => setCmdOn(e.target.value)}
                  placeholder="FOCO1_ON"
                />
              </Field>
              <Field label="Comando apagar">
                <TextInput
                  value={cmdOff}
                  onChange={(e) => setCmdOff(e.target.value)}
                  placeholder="FOCO1_OFF"
                />
              </Field>
            </div>
          </Surface>
        )}

        {transportType === "serial" && isSensor && (
          <Surface level={2} className="p-4">
            <div className="text-[11px] uppercase tracking-[0.18em] text-text-dim mb-3">
              Lectura serial del sensor
            </div>
            <Field
              label="Prefijo de la lectura"
              hint="texto antes de ':' que envía el Arduino. Ej: TEMPERATURA → TEMPERATURA:23.5"
            >
              <TextInput
                value={serialSensorPrefix}
                onChange={(e) => setSerialSensorPrefix(e.target.value)}
                placeholder="TEMPERATURA"
              />
            </Field>
            <p className="text-[11px] text-text-dim mt-2 leading-relaxed">
              Si lo dejas vacío, ORION usa el ID en mayúsculas como prefijo (
              <code className="text-acc font-mono">{(id || "SENSOR").toUpperCase()}</code>). Debe
              coincidir <i>exactamente</i> con lo que tu sketch imprime por{" "}
              <code className="text-acc font-mono">Serial.print()</code>.
            </p>
          </Surface>
        )}

        {/* CAPACIDADES */}
        <Field
          label="Capacidades"
          hint={isSensor ? "Los sensores no controlan; solo leen" : "Marca todo lo que aplique"}
        >
          <div className="flex flex-wrap gap-2">
            <CapChip
              label="On / Off"
              active={!!caps.on_off}
              disabled={isSensor}
              onClick={() => toggleCap("on_off")}
            />
            <CapChip
              label="Regulable"
              active={!!caps.dimmable}
              disabled={isSensor}
              onClick={() => toggleCap("dimmable")}
            />
            <CapChip
              label="RGB"
              active={!!caps.rgb}
              disabled={isSensor}
              onClick={() => toggleCap("rgb")}
            />
            <CapChip label="Sensor" active={!!caps.sensor} onClick={() => toggleCap("sensor")} />
          </div>
        </Field>

        {/* SENSOR — kind & graph & freq */}
        {isSensor && (
          <>
            <Field label="Tipo de sensor">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                {SENSOR_PRESETS.map((p) => {
                  const active = sensorKind === p.id;
                  return (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => pickSensorKind(p.id)}
                      className={[
                        "flex items-center gap-2 rounded-lg border px-3 h-10 text-sm transition-all duration-200 ease-out-expo",
                        active
                          ? "bg-pri/10 border-pri/40 text-text shadow-glow-soft"
                          : "bg-elevated/40 border-white/[0.06] text-text-dim hover:border-white/[0.14] hover:text-text",
                      ].join(" ")}
                    >
                      <Icon name={p.icon} size={14} className={active ? "text-pri" : ""} />
                      <span className="truncate">{p.label}</span>
                    </button>
                  );
                })}
              </div>
              {sensorKind === "custom" && (
                <div className="mt-2.5">
                  <TextInput
                    value={customSensor}
                    onChange={(e) => setCustomSensor(e.target.value)}
                    placeholder="p. ej. lux, soil_moisture…"
                  />
                </div>
              )}
            </Field>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Field
                label="Frecuencia de actualización"
                hint={`Recomendada: ${SENSOR_FREQ_REC[sensorKind].label}`}
              >
                <div className="flex items-center gap-2">
                  <NumInput
                    value={updateFreq}
                    onChange={(n) => setUpdateFreq(Math.max(0.1, n))}
                    min={0.1}
                    step={0.5}
                    className="w-28"
                  />
                  <span className="text-xs text-text-dim">segundos</span>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {[1, 5, 10, 30, 60, 300].map((v) => (
                    <QuickPick
                      key={v}
                      active={updateFreq === v}
                      onClick={() => setUpdateFreq(v)}
                      label={v < 60 ? `${v}s` : `${v / 60}m`}
                    />
                  ))}
                  <button
                    type="button"
                    onClick={() => setUpdateFreq(SENSOR_FREQ_REC[sensorKind].value)}
                    className="text-[10px] uppercase tracking-[0.16em] px-2 py-1 rounded-md border border-acc/30 bg-acc/10 text-acc hover:bg-acc/15 transition-colors"
                    title="Usar recomendada"
                  >
                    Recom.
                  </button>
                </div>
              </Field>

              <Field label="Mostrar gráfico" hint="Sparkline en la tarjeta">
                <Surface level={2} className="flex items-center justify-between px-3.5 h-10">
                  <span className="inline-flex items-center gap-2 text-sm text-text">
                    <Icon name="chart-line" size={14} className="text-pri" />
                    {showGraph ? "Activado" : "Desactivado"}
                  </span>
                  <Switch on={showGraph} onClick={() => setShowGraph((v) => !v)} />
                </Surface>
              </Field>
            </div>
          </>
        )}

        {/* Frecuencia para no-sensores (override de UI) */}
        {!isSensor && (
          <Field label="Frecuencia de refresco UI" hint="opcional · solo afecta el dashboard">
            <div className="flex items-center gap-2">
              <NumInput
                value={updateFreq}
                onChange={(n) => setUpdateFreq(Math.max(0.1, n))}
                min={0.1}
                step={0.5}
                className="w-28"
              />
              <span className="text-xs text-text-dim">segundos</span>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {[1, 5, 10, 30, 60].map((v) => (
                <QuickPick
                  key={v}
                  active={updateFreq === v}
                  onClick={() => setUpdateFreq(v)}
                  label={v < 60 ? `${v}s` : `${v / 60}m`}
                />
              ))}
            </div>
          </Field>
        )}

        {readOnlyBackendBadges(device, mode)}
      </div>
    </Modal>
  );
}

function readOnlyBackendBadges(device: IoTDevice | LocalDevice | undefined, mode: Mode) {
  if (mode !== "edit-backend" || !device) return null;
  return (
    <Field label="Capacidades reales del backend (lectura)">
      <div className="flex flex-wrap gap-1.5">
        {device.capabilities.on_off && <Badge tone="info">on/off</Badge>}
        {device.capabilities.dimmable && <Badge tone="accent">dim</Badge>}
        {device.capabilities.rgb && <Badge tone="neutral">rgb</Badge>}
        {device.capabilities.sensor && (
          <Badge tone="warn">sensor · {device.capabilities.sensor}</Badge>
        )}
      </div>
    </Field>
  );
}

/* ── helpers visuales ─────────────────────────────────────────────── */
function NumInput({
  value,
  onChange,
  min,
  max,
  step,
  className,
}: {
  value: number;
  onChange: (n: number) => void;
  min?: number;
  max?: number;
  step?: number;
  className?: string;
}) {
  return (
    <TextInput
      type="number"
      value={Number.isFinite(value) ? value : ""}
      onChange={(e) => {
        const raw = e.target.value;
        if (raw === "") {
          onChange(0);
          return;
        }
        const n = Number(raw);
        if (Number.isNaN(n)) return;
        let v = n;
        if (min !== undefined) v = Math.max(min, v);
        if (max !== undefined) v = Math.min(max, v);
        onChange(v);
      }}
      min={min}
      max={max}
      step={step}
      className={className}
    />
  );
}

function QuickPick({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "text-[10px] uppercase tracking-[0.16em] px-2 py-1 rounded-md border transition-colors",
        active
          ? "bg-pri/15 border-pri/40 text-pri"
          : "bg-elevated/40 border-white/[0.06] text-text-dim hover:text-text",
      ].join(" ")}
    >
      {label}
    </button>
  );
}

function CapChip({
  label,
  active,
  disabled,
  onClick,
}: {
  label: string;
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      className={[
        "inline-flex items-center gap-2 h-9 px-3 rounded-lg border text-sm",
        "transition-all duration-200 ease-out-expo",
        disabled
          ? "opacity-30 cursor-not-allowed border-white/[0.04] bg-elevated/30 text-muted"
          : active
            ? "bg-pri/15 border-pri/40 text-pri shadow-glow-soft"
            : "bg-elevated/40 border-white/[0.06] text-text-dim hover:text-text hover:border-white/[0.14]",
      ].join(" ")}
    >
      <span
        className={[
          "h-2 w-2 rounded-full transition-colors",
          disabled
            ? "bg-white/[0.08]"
            : active
              ? "bg-pri shadow-[0_0_8px_rgb(var(--orion-pri))]"
              : "bg-white/[0.15]",
        ].join(" ")}
      />
      {label}
    </button>
  );
}
