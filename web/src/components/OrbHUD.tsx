/**
 * OrbHUD — el ojo cinemático de Orion (centerpiece de Inicio).
 *
 * State system:
 *   - idle      (muted / disconnected): ojo "observando" tranquilo
 *   - listening (ESCUCHANDO):           cian más vivo, iris pulsando
 *   - thinking  (PENSANDO):              magenta, giro vertiginoso
 *   - speaking  (HABLANDO):              verde-cian, dilatado, destellos
 *   - tool      (override):              se pinta como pensando
 *   - agent     (override):              se pinta como pensando
 *   - error     (override):              rojo crítico con alerta
 *
 * El componente lee el `OrionState` público del store y deja al shell
 * pasar un `mode` override de prioridad superior. Dos tamaños:
 *   - default ("full"): centerpiece — usa <EyeCore>
 *   - "mini":           top-bar avatar — mini bolita estilizada
 */

import { useInteractionStore } from "@/stores/interaction";
import { useOrionStore } from "@/stores/orion";
import { EyeCore, type EyeState } from "@/widgets/eye";

export type OrbMode = "idle" | "listening" | "thinking" | "speaking" | "tool" | "agent" | "error";

const PALETTE: Record<OrbMode, { core: string; ring: string; glow: string; accent: string }> = {
  idle: { core: "#6D7CFF", ring: "#6D7CFF", glow: "rgba(109,124,255,0.18)", accent: "#7EE7FF" },
  listening: {
    core: "#7EE7FF",
    ring: "#7EE7FF",
    glow: "rgba(126,231,255,0.32)",
    accent: "#6D7CFF",
  },
  thinking: { core: "#A78BFA", ring: "#A78BFA", glow: "rgba(167,139,250,0.32)", accent: "#7EE7FF" },
  speaking: { core: "#22E5A0", ring: "#22E5A0", glow: "rgba(34,229,160,0.30)", accent: "#7EE7FF" },
  tool: { core: "#FBBF24", ring: "#FBBF24", glow: "rgba(251,191,36,0.28)", accent: "#F59E0B" },
  agent: { core: "#F472B6", ring: "#F472B6", glow: "rgba(244,114,182,0.30)", accent: "#A78BFA" },
  error: { core: "#EF4444", ring: "#EF4444", glow: "rgba(239,68,68,0.32)", accent: "#F472B6" },
};

const LABEL: Record<OrbMode, string> = {
  idle: "Inactivo",
  listening: "Escuchando",
  thinking: "Pensando",
  speaking: "Hablando",
  tool: "Ejecutando",
  agent: "Agente activo",
  error: "Error",
};

interface Props {
  size?: "full" | "mini";
  /** override (highest priority) — for tool/agent/error visuals driven by the shell */
  mode?: OrbMode;
}

/**
 * Mapea el `OrbMode` (incluye tool/agent) al subconjunto que entiende
 * el `EyeCore`. tool/agent reusan la animación de pensando.
 */
export function modeToEyeState(mode: OrbMode): EyeState {
  if (mode === "listening") return "listening";
  if (mode === "speaking") return "speaking";
  if (mode === "thinking" || mode === "tool" || mode === "agent") return "thinking";
  if (mode === "error") return "error";
  return "idle";
}

export function OrbHUD({ size = "full", mode: override }: Props) {
  const state = useOrionStore((s) => s.state);
  const muted = useOrionStore((s) => s.muted);
  const connected = useOrionStore((s) => s.connected);

  // Overrides automáticos: una tool en ejecución o un agente activo
  // hacen al ojo pintar "pensando" (mismo magenta que PENSANDO). El
  // `override` explícito por prop tiene aún más prioridad.
  const activeTool = useInteractionStore((s) => s.tool);
  const activeAgent = useInteractionStore((s) => s.agent);

  const mode: OrbMode =
    override ??
    (!connected
      ? "idle"
      : muted
        ? "idle"
        : activeTool
          ? "tool"
          : activeAgent?.status === "running"
            ? "agent"
            : state === "ESCUCHANDO"
              ? "listening"
              : state === "PENSANDO"
                ? "thinking"
                : state === "HABLANDO"
                  ? "speaking"
                  : "idle");

  return size === "mini" ? (
    <MiniOrb mode={mode} />
  ) : (
    <FullOrb mode={mode} muted={muted} connected={connected} />
  );
}

/* ─────────────────────────────────────────────────────────────────────
   FULL ORB — el ojo cinemático de Inicio, 320 px.
   La bolita anterior se sustituyó por <EyeCore>. Mantengo el halo
   ambiental por detrás (sigue la paleta del modo) y el bloque de
   etiquetas/conexión debajo.
   ───────────────────────────────────────────────────────────────────── */
function FullOrb({
  mode,
  muted,
  connected,
}: {
  mode: OrbMode;
  muted: boolean;
  connected: boolean;
}) {
  const p = PALETTE[mode];
  const eyeState = modeToEyeState(mode);

  return (
    <div className="orb-hud-container relative flex flex-col items-center gap-7 select-none animate-fade-in">
      <div className="relative h-[320px] w-[320px] grid place-items-center">
        {/* halo ambiental por detrás del ojo */}
        <div
          className="absolute h-[320px] w-[320px] rounded-full blur-3xl animate-halo pointer-events-none"
          style={{ background: p.glow, transition: "background 600ms ease" }}
        />

        {/* OJO — sustituye a la bolita anterior. Si Orion está sin
            conexión, frozen=true: el ojo se queda quieto y el cian se
            apaga a un azul sobrio (no parpadea ni gira). El estado
            "silenciado" se comunica vía la etiqueta de abajo + el ojo
            apagado (paleta idle), no con un icono encima — el icono
            ensuciaba la composición. */}
        <EyeCore state={eyeState} size={300} frozen={!connected} />
      </div>

      {/* state label */}
      <div className="text-center -mt-2">
        <div
          key={mode}
          className="text-[10px] uppercase tracking-[0.36em] text-text animate-fade-in-up"
          style={{ color: muted ? "rgb(var(--orion-text-dim))" : p.core }}
        >
          {muted ? "Silenciado" : LABEL[mode]}
        </div>
        <div className="text-[9px] uppercase tracking-[0.32em] text-text-dim mt-2 flex items-center justify-center gap-1.5">
          <span
            className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-ok shadow-[0_0_8px_rgb(var(--orion-ok))]" : "bg-muted"}`}
          />
          <span>{connected ? "Conectado" : "Sin conexión"}</span>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────
   MINI ORB — used in the top bar, 36×36. Sigue siendo la bolita
   estilizada original — el ojo completo no rinde bien a 36 px.
   ───────────────────────────────────────────────────────────────────── */
function MiniOrb({ mode }: { mode: OrbMode }) {
  const p = PALETTE[mode];
  return (
    <div className="relative h-9 w-9 grid place-items-center" title={LABEL[mode]}>
      <div
        className="absolute inset-0 rounded-full blur-md opacity-60"
        style={{ background: p.glow }}
      />
      <svg
        viewBox="0 0 40 40"
        className="relative h-9 w-9 animate-breath"
        style={{ filter: `drop-shadow(0 0 6px ${p.glow})` }}
      >
        <defs>
          <radialGradient id={`miniCore-${mode}`} cx="50%" cy="42%" r="56%">
            <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.9" />
            <stop offset="40%" stopColor={p.core} stopOpacity="0.9" />
            <stop offset="100%" stopColor="#000000" stopOpacity="0.85" />
          </radialGradient>
        </defs>
        <circle
          cx="20"
          cy="20"
          r="14"
          fill={`url(#miniCore-${mode})`}
          stroke={p.ring}
          strokeOpacity="0.5"
          strokeWidth="0.7"
        />
        {(mode === "thinking" || mode === "agent" || mode === "tool") && (
          <g
            style={{ transformOrigin: "20px 20px" }}
            className={mode === "tool" ? "animate-spin-fast" : "animate-spin-slow"}
          >
            <circle
              cx="20"
              cy="20"
              r="18"
              fill="none"
              stroke={p.ring}
              strokeOpacity="0.35"
              strokeWidth="0.7"
              strokeDasharray="1 4"
            />
          </g>
        )}
      </svg>
    </div>
  );
}
