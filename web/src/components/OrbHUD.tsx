/**
 * OrbHUD — esfera reactiva al estado del asistente.
 *
 * Equivalente minimal del orb_widget.py de la UI Qt. En esta primera
 * iteración usa SVG + CSS animaciones; en Fase 3 lo reemplazaremos por
 * Three.js para llegar al nivel de detalle del original.
 */

import { useOrionStore } from "@/stores/orion";

const COLORS = {
  ESCUCHANDO: { ring: "#ff2a4d", glow: "#ff2a4d33" },
  PENSANDO:   { ring: "#ff6b1a", glow: "#ff6b1a33" },
  HABLANDO:   { ring: "#33ff99", glow: "#33ff9933" },
} as const;

const LABEL: Record<string, string> = {
  ESCUCHANDO: "Escuchando",
  PENSANDO:   "Pensando",
  HABLANDO:   "Hablando",
};

export function OrbHUD() {
  const state     = useOrionStore((s) => s.state);
  const muted     = useOrionStore((s) => s.muted);
  const connected = useOrionStore((s) => s.connected);

  const colors = COLORS[state];

  return (
    <div className="relative flex flex-col items-center justify-center gap-6 select-none">
      <div className="relative w-64 h-64">
        {/* Halo */}
        <div
          className="absolute inset-0 rounded-full blur-3xl animate-orb-pulse"
          style={{ background: colors.glow }}
        />
        {/* Orb principal */}
        <svg viewBox="0 0 200 200" className="absolute inset-0 w-full h-full">
          <defs>
            <radialGradient id="orbGrad" cx="50%" cy="42%" r="60%">
              <stop offset="0%" stopColor={colors.ring} stopOpacity="0.95" />
              <stop offset="55%" stopColor={colors.ring} stopOpacity="0.35" />
              <stop offset="100%" stopColor="#000" stopOpacity="0.95" />
            </radialGradient>
          </defs>
          <circle
            cx="100" cy="100" r="78"
            fill="url(#orbGrad)"
            stroke={colors.ring}
            strokeWidth="1.5"
            className="animate-orb-pulse"
            style={{ transformOrigin: "center" }}
          />
          {/* Anillo interno */}
          <circle
            cx="100" cy="100" r="58"
            fill="none"
            stroke={colors.ring}
            strokeOpacity="0.25"
            strokeWidth="0.7"
          />
        </svg>
      </div>

      <div className="text-center">
        <div className="text-xs uppercase tracking-[0.3em] text-text-dim">
          {muted ? "Silenciado" : LABEL[state] ?? state}
        </div>
        <div className="text-[10px] uppercase tracking-widest text-text-dim mt-2">
          {connected ? (
            <span className="text-pri">● conectado</span>
          ) : (
            <span className="text-text-dim">○ desconectado</span>
          )}
        </div>
      </div>
    </div>
  );
}
