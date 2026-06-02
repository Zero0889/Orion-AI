/**
 * useDeviceConfig — local-only IoT customization layer.
 *
 * The backend currently exposes a read-only device catalog (GET
 * /api/iot/devices). To let the user add their own devices and tweak
 * existing ones without touching backend contracts, we persist a thin
 * config layer in localStorage:
 *
 *   - configs[id]:   per-device overrides (display name, update freq,
 *                    show-graph toggle, sensor kind).
 *   - local[]:       locally-defined devices. They show in the panel
 *                    with a "Local" badge; their actions still hit the
 *                    same /api/iot/devices/{id}/action endpoint so if
 *                    the backend later registers the same id, controls
 *                    just start working.
 *
 * Persisted under "orion.iot.config.v1".
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import type { IoTDevice } from "@/api/rest";

const STORAGE_KEY = "orion.iot.config.v1";

export type SensorKind =
  | "temperature" | "humidity" | "pressure" | "light"
  | "motion" | "co2" | "custom";

/** El "kind" elegido por el usuario en el modal. Se persiste localmente
 *  para que un foco no aparezca como "interruptor" solo porque ambos
 *  comparten capabilities (on/off sin dim ni rgb). Si está ausente,
 *  caemos en heurística por nombre / capabilities. */
export type DeviceKind = "light" | "switch" | "sensor" | "mixed";

export interface DeviceConfig {
  displayName?:  string;
  updateFreqS?:  number;  // user-set polling/refresh hint, seconds
  showGraph?:    boolean; // sensors only — render an inline sparkline
  sensorKind?:   SensorKind;
  kind?:         DeviceKind;
}

export interface LocalDevice extends IoTDevice {
  /** marker so we can distinguish local devices from backend ones */
  __local: true;
}

interface Persisted {
  configs: Record<string, DeviceConfig>;
  local:   LocalDevice[];
}

const EMPTY: Persisted = { configs: {}, local: [] };

function read(): Persisted {
  if (typeof window === "undefined") return EMPTY;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return EMPTY;
    const parsed = JSON.parse(raw) as Partial<Persisted>;
    return {
      configs: parsed.configs ?? {},
      local:   (parsed.local ?? []).map((d) => ({ ...d, __local: true as const })),
    };
  } catch {
    return EMPTY;
  }
}

function write(p: Persisted): void {
  try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(p)); }
  catch { /* quota? ignore */ }
}

/** Recommended update frequency (seconds) per sensor kind. */
export const SENSOR_FREQ_REC: Record<SensorKind, { value: number; label: string }> = {
  temperature: { value: 30, label: "30 s · moderada"   },
  humidity:    { value: 60, label: "60 s · lenta"      },
  pressure:    { value: 60, label: "60 s · lenta"      },
  light:       { value: 10, label: "10 s · rápida"     },
  motion:      { value: 1,  label: "1 s · instantánea" },
  co2:         { value: 60, label: "60 s · lenta"      },
  custom:      { value: 10, label: "10 s · genérica"   },
};

export function useDeviceConfig() {
  const [state, setState] = useState<Persisted>(() => read());

  // sync across tabs/windows
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) setState(read());
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  /** persist con functional setState — evita el bug clásico de stale
   *  closure cuando se llaman varias mutaciones en el mismo tick. */
  const persist = useCallback((updater: (prev: Persisted) => Persisted) => {
    setState((prev) => {
      const next = updater(prev);
      write(next);
      return next;
    });
  }, []);

  const getConfig = useCallback(
    (id: string): DeviceConfig => state.configs[id] ?? {},
    [state.configs],
  );

  const setConfig = useCallback((id: string, patch: Partial<DeviceConfig>) => {
    persist((prev) => ({
      ...prev,
      configs: {
        ...prev.configs,
        [id]: { ...(prev.configs[id] ?? {}), ...patch },
      },
    }));
  }, [persist]);

  const addLocal = useCallback((dev: LocalDevice, cfg?: DeviceConfig) => {
    persist((prev) => ({
      configs: cfg ? { ...prev.configs, [dev.id]: cfg } : prev.configs,
      local:   [...prev.local.filter((d) => d.id !== dev.id), dev],
    }));
  }, [persist]);

  const updateLocal = useCallback((id: string, patch: Partial<LocalDevice>, cfg?: Partial<DeviceConfig>) => {
    persist((prev) => ({
      configs: cfg
        ? { ...prev.configs, [id]: { ...(prev.configs[id] ?? {}), ...cfg } }
        : prev.configs,
      local: prev.local.map((d) => (d.id === id ? { ...d, ...patch, __local: true } : d)),
    }));
  }, [persist]);

  const removeLocal = useCallback((id: string) => {
    persist((prev) => {
      const nextConfigs = { ...prev.configs };
      delete nextConfigs[id];
      return {
        configs: nextConfigs,
        local:   prev.local.filter((d) => d.id !== id),
      };
    });
  }, [persist]);

  const removeConfig = useCallback((id: string) => {
    persist((prev) => {
      if (!prev.configs[id]) return prev;
      const next = { ...prev.configs };
      delete next[id];
      return { ...prev, configs: next };
    });
  }, [persist]);

  const localDevices = useMemo(() => state.local, [state.local]);

  return {
    configs: state.configs,
    localDevices,
    getConfig,
    setConfig,
    removeConfig,
    addLocal,
    updateLocal,
    removeLocal,
  };
}
