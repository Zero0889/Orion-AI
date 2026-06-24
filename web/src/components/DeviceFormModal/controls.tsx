/**
 * Controles UI puros del DeviceFormModal.
 *
 * Componentes pequeños sin lógica de negocio — solo presentación.
 * Viven acá para que el index.tsx (el componente principal con el state)
 * quede solo con la lógica de la forma.
 */

import type { IoTDevice } from "@/api/rest";
import { Badge, Field, TextInput } from "@/ui/primitives";

import type { LocalDevice } from "@/hooks/useDeviceConfig";
import type { Mode } from "./constants";

/**
 * Input numérico sin spinners nativos (CSS global los oculta), con
 * clamp opcional a min/max y guard contra NaN cuando el user borra todo.
 */
export function NumInput({
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

/**
 * Botoncito de "quick-pick" — set un valor pre-definido al instante.
 * Usado para frecuencias de update sugeridas según el sensor.
 */
export function QuickPick({
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

/**
 * Chip toggleable para las capabilities del device (on_off / dimmable / rgb).
 * `disabled` lo deja semi-transparente (caso sensor: las caps no aplican).
 */
export function CapChip({
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

/**
 * Badges read-only con las capabilities REALES que el backend reportó.
 * Solo se muestran en modo edit-backend para que el user vea qué
 * conoce el sistema vs qué está editando localmente.
 */
export function ReadOnlyBackendBadges({
  device,
  mode,
}: {
  device: IoTDevice | LocalDevice | undefined;
  mode: Mode;
}) {
  if (mode !== "edit-backend" || !device) return null;
  return (
    <Field label="Capacidades reales del backend (lectura)">
      <div className="flex flex-wrap gap-1.5">
        {device.capabilities.on_off && <Badge tone="info">on/off</Badge>}
        {device.capabilities.dimmable && <Badge tone="accent">dim</Badge>}
        {device.capabilities.rgb && <Badge tone="neutral">rgb</Badge>}
        {device.capabilities.sensor && (
          <Badge tone="info">sensor · {device.capabilities.sensor}</Badge>
        )}
      </div>
    </Field>
  );
}
