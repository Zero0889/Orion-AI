/**
 * OrbHUD — cinematic, multi-state SVG orb. The visual identity of Orion.
 *
 * State system:
 *   - idle      (muted / disconnected): slow breath + ambient halo
 *   - listening (ESCUCHANDO):           expanding pulse rings, reactive
 *   - thinking  (PENSANDO):              rotating orbital rings + particles
 *   - speaking  (HABLANDO):              rhythmic wave + voice burst
 *   - tool      (override):              progress ring + directional flow
 *   - agent     (override):              multi-orbit parallel processes
 *   - error     (override):              controlled red pulse
 *
 * The component reads the public OrionState from the store and lets the
 * shell pass a higher-priority `mode` override (used when there's an
 * active tool/agent execution surfaced by the bus). Two render sizes:
 *   - default ("full"): centerpiece
 *   - "mini":           top-bar avatar
 */

import { useEffect, useMemo, useRef, useState } from "react";

import { useInteractionStore } from "@/stores/interaction";
import { useOrionStore } from "@/stores/orion";

export type OrbMode =
  | "idle" | "listening" | "thinking" | "speaking"
  | "tool" | "agent" | "error";

const PALETTE: Record<OrbMode, { core: string; ring: string; glow: string; accent: string }> = {
  idle:      { core: "#6D7CFF", ring: "#6D7CFF", glow: "rgba(109,124,255,0.18)", accent: "#7EE7FF" },
  listening: { core: "#7EE7FF", ring: "#7EE7FF", glow: "rgba(126,231,255,0.32)", accent: "#6D7CFF" },
  thinking:  { core: "#A78BFA", ring: "#A78BFA", glow: "rgba(167,139,250,0.32)", accent: "#7EE7FF" },
  speaking:  { core: "#22E5A0", ring: "#22E5A0", glow: "rgba(34,229,160,0.30)",  accent: "#7EE7FF" },
  tool:      { core: "#FBBF24", ring: "#FBBF24", glow: "rgba(251,191,36,0.28)",  accent: "#F59E0B" },
  agent:     { core: "#F472B6", ring: "#F472B6", glow: "rgba(244,114,182,0.30)", accent: "#A78BFA" },
  error:     { core: "#EF4444", ring: "#EF4444", glow: "rgba(239,68,68,0.32)",   accent: "#F472B6" },
};

const LABEL: Record<OrbMode, string> = {
  idle:      "Inactivo",
  listening: "Escuchando",
  thinking:  "Pensando",
  speaking:  "Hablando",
  tool:      "Ejecutando",
  agent:     "Agente activo",
  error:     "Error",
};

interface Props {
  size?: "full" | "mini";
  /** override (highest priority) — for tool/agent/error visuals driven by the shell */
  mode?: OrbMode;
}

export function OrbHUD({ size = "full", mode: override }: Props) {
  const state     = useOrionStore((s) => s.state);
  const muted     = useOrionStore((s) => s.muted);
  const connected = useOrionStore((s) => s.connected);

  // Estos overrides automáticos hacen al orbe reaccionar de verdad a lo
  // que pasa abajo, no solo al estado de audio. Una tool en ejecución
  // pinta el orbe amarillo con anillo girando rápido; un agente activo
  // lo pinta rosa con múltiples órbitas. El `override` explícito (prop)
  // tiene aún más prioridad — útil para previews o demos.
  const activeTool  = useInteractionStore((s) => s.tool);
  const activeAgent = useInteractionStore((s) => s.agent);

  const mode: OrbMode = override
    ?? (!connected ? "idle"
    :    muted     ? "idle"
    :    activeTool                            ? "tool"
    :    activeAgent?.status === "running"     ? "agent"
    :    state === "ESCUCHANDO" ? "listening"
    :    state === "PENSANDO"   ? "thinking"
    :    state === "HABLANDO"   ? "speaking"
    :    "idle");

  return size === "mini"
    ? <MiniOrb mode={mode} />
    : <FullOrb mode={mode} muted={muted} connected={connected} />;
}

/* ─────────────────────────────────────────────────────────────────────
   FULL ORB — workspace centerpiece, 320×320 visual.
   ───────────────────────────────────────────────────────────────────── */
function FullOrb({ mode, muted, connected }: { mode: OrbMode; muted: boolean; connected: boolean }) {
  const p = PALETTE[mode];

  return (
    <div className="relative flex flex-col items-center gap-7 select-none animate-fade-in">
      {/* outer ambient halo + drift */}
      <div className="relative h-[320px] w-[320px] grid place-items-center">

        {/* ambient blur halo, far reach */}
        <div
          className="absolute h-[300px] w-[300px] rounded-full blur-3xl animate-halo"
          style={{ background: p.glow, transition: "background 600ms ease" }}
        />
        {/* secondary tint (acc) */}
        <div
          className="absolute h-[260px] w-[260px] rounded-full blur-2xl opacity-50 animate-drift-slow"
          style={{ background: p.glow }}
        />

        {/* expanding pulse rings — listening / speaking */}
        {(mode === "listening" || mode === "speaking") && (
          <>
            <PulseRing color={p.ring} delay="0s"   />
            <PulseRing color={p.ring} delay="0.9s" />
            <PulseRing color={p.ring} delay="1.7s" />
          </>
        )}

        {/* main SVG — layered orb */}
        <svg
          viewBox="0 0 320 320"
          className="relative h-[320px] w-[320px] animate-breath"
          style={{ filter: `drop-shadow(0 0 24px ${p.glow})`, transition: "filter 600ms ease" }}
        >
          <defs>
            <radialGradient id="orbCore" cx="50%" cy="42%" r="58%">
              <stop offset="0%"   stopColor="#FFFFFF" stopOpacity="0.95" />
              <stop offset="22%"  stopColor={p.core}  stopOpacity="0.92" />
              <stop offset="68%"  stopColor={p.core}  stopOpacity="0.30" />
              <stop offset="100%" stopColor="#000000" stopOpacity="0.85" />
            </radialGradient>
            <radialGradient id="orbInner" cx="50%" cy="38%" r="40%">
              <stop offset="0%"   stopColor="#FFFFFF" stopOpacity="0.7" />
              <stop offset="100%" stopColor="#FFFFFF" stopOpacity="0" />
            </radialGradient>
            <linearGradient id="orbRim" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor={p.accent} stopOpacity="0.6" />
              <stop offset="100%" stopColor={p.ring}   stopOpacity="0" />
            </linearGradient>
            <filter id="softGlow">
              <feGaussianBlur stdDeviation="2" />
            </filter>
          </defs>

          {/* outermost wire ring — thinking/agent rotate */}
          <g
            style={{ transformOrigin: "160px 160px", transition: "opacity 400ms" }}
            className={
              mode === "thinking" ? "animate-spin-slow"
              : mode === "agent"   ? "animate-spin-mid"
              : mode === "tool"    ? "animate-spin-fast"
              : ""
            }
          >
            <circle
              cx="160" cy="160" r="148"
              fill="none" stroke={p.ring}
              strokeOpacity="0.18" strokeWidth="0.8"
              strokeDasharray={
                mode === "thinking" ? "2 6"
                : mode === "tool"    ? "10 4"
                : mode === "agent"   ? "1 5"
                : "1 0"
              }
            />
            {/* orbital marker */}
            <circle cx="160" cy="12" r="2.5" fill={p.accent} opacity="0.9" filter="url(#softGlow)" />
          </g>

          {/* mid ring counter-rotation (thinking/agent) */}
          {(mode === "thinking" || mode === "agent") && (
            <g style={{ transformOrigin: "160px 160px" }} className="animate-spin-rev">
              <circle
                cx="160" cy="160" r="128"
                fill="none" stroke={p.accent}
                strokeOpacity="0.20" strokeWidth="0.6"
                strokeDasharray="1 8"
              />
              <circle cx="160" cy="32" r="1.6" fill={p.accent} opacity="0.7" />
              {mode === "agent" && (
                <circle cx="160" cy="288" r="1.6" fill={p.accent} opacity="0.7" />
              )}
            </g>
          )}

          {/* tool progress arc */}
          {mode === "tool" && (
            <g style={{ transformOrigin: "160px 160px" }} className="animate-spin-fast">
              <circle
                cx="160" cy="160" r="138"
                fill="none" stroke={p.accent}
                strokeWidth="1.6" strokeLinecap="round"
                strokeDasharray="180 700"
              />
            </g>
          )}

          {/* core orb */}
          <circle
            cx="160" cy="160" r="92"
            fill="url(#orbCore)"
            stroke={p.ring} strokeOpacity="0.45" strokeWidth="1"
            style={{ transition: "stroke 400ms" }}
          />
          {/* specular highlight */}
          <ellipse cx="135" cy="125" rx="42" ry="22" fill="url(#orbInner)" />
          {/* rim soft */}
          <circle cx="160" cy="160" r="92" fill="none" stroke="url(#orbRim)" strokeWidth="1.2" />

          {/* inner ring */}
          <circle
            cx="160" cy="160" r="72"
            fill="none" stroke={p.ring} strokeOpacity="0.18" strokeWidth="0.6"
          />

          {/* speaking waveform overlay */}
          {mode === "speaking" && <Waveform color={p.accent} />}

          {/* error sigil */}
          {mode === "error" && (
            <g opacity="0.9">
              <circle cx="160" cy="160" r="32" fill="none" stroke={p.ring} strokeWidth="1.2" />
              <path d="M160 144v22M160 174v2" stroke={p.ring} strokeWidth="2" strokeLinecap="round" />
            </g>
          )}
        </svg>

        {/* muted overlay */}
        {muted && (
          <div className="absolute inset-0 grid place-items-center">
            <div className="rounded-full bg-bg/55 backdrop-blur-sm p-3 border border-white/10 animate-scale-in">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
                   stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" className="text-text-dim">
                <path d="m3 3 18 18" />
                <path d="M9 9v3a3 3 0 0 0 5.12 2.12" />
                <path d="M15 9.34V6a3 3 0 0 0-5.94-.6" />
                <path d="M5 11a7 7 0 0 0 12 5M19 11a7 7 0 0 1-.34 2.16" />
                <path d="M12 18v3" />
              </svg>
            </div>
          </div>
        )}
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
          <span className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-ok shadow-[0_0_8px_rgb(var(--orion-ok))]" : "bg-muted"}`} />
          <span>{connected ? "Conectado" : "Sin conexión"}</span>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────
   MINI ORB — used in the top bar, 36×36.
   ───────────────────────────────────────────────────────────────────── */
function MiniOrb({ mode }: { mode: OrbMode }) {
  const p = PALETTE[mode];
  return (
    <div className="relative h-9 w-9 grid place-items-center" title={LABEL[mode]}>
      <div className="absolute inset-0 rounded-full blur-md opacity-60"
           style={{ background: p.glow }} />
      <svg viewBox="0 0 40 40" className="relative h-9 w-9 animate-breath"
           style={{ filter: `drop-shadow(0 0 6px ${p.glow})` }}>
        <defs>
          <radialGradient id={`miniCore-${mode}`} cx="50%" cy="42%" r="56%">
            <stop offset="0%"   stopColor="#FFFFFF" stopOpacity="0.9" />
            <stop offset="40%"  stopColor={p.core}  stopOpacity="0.9" />
            <stop offset="100%" stopColor="#000000" stopOpacity="0.85" />
          </radialGradient>
        </defs>
        <circle cx="20" cy="20" r="14" fill={`url(#miniCore-${mode})`}
                stroke={p.ring} strokeOpacity="0.5" strokeWidth="0.7" />
        {(mode === "thinking" || mode === "agent" || mode === "tool") && (
          <g style={{ transformOrigin: "20px 20px" }}
             className={mode === "tool" ? "animate-spin-fast" : "animate-spin-slow"}>
            <circle cx="20" cy="20" r="18" fill="none"
                    stroke={p.ring} strokeOpacity="0.35" strokeWidth="0.7"
                    strokeDasharray="1 4" />
          </g>
        )}
      </svg>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────
   PulseRing — single expanding ring with delayed start.
   ───────────────────────────────────────────────────────────────────── */
function PulseRing({ color, delay }: { color: string; delay: string }) {
  return (
    <span
      className="absolute h-[200px] w-[200px] rounded-full border animate-pulse-ring"
      style={{ borderColor: color, animationDelay: delay }}
    />
  );
}

/* ─────────────────────────────────────────────────────────────────────
   Waveform — voice-reactive bars for HABLANDO. Uses random base heights
   refreshed every 110ms to mimic an audio envelope without real audio.
   Each <rect> still animates via CSS (`animate-wave`) for smooth pulse.
   ───────────────────────────────────────────────────────────────────── */
function Waveform({ color }: { color: string }) {
  const BARS = 11;
  const [seeds, setSeeds] = useState<number[]>(() =>
    Array.from({ length: BARS }, () => 0.4 + Math.random() * 0.6));

  const tick = useRef<number | null>(null);
  useEffect(() => {
    const loop = () => {
      setSeeds(Array.from({ length: BARS }, () => 0.4 + Math.random() * 0.6));
      tick.current = window.setTimeout(loop, 110);
    };
    loop();
    return () => { if (tick.current) clearTimeout(tick.current); };
  }, []);

  const W = 90, H = 38, X0 = 160 - W / 2, Y0 = 160;
  const gap = W / BARS;

  return useMemo(() => (
    <g style={{ transformOrigin: "160px 160px" }}>
      {seeds.map((h, i) => {
        const barH = h * H;
        return (
          <rect
            key={i}
            x={X0 + i * gap + gap * 0.18}
            y={Y0 - barH / 2}
            width={gap * 0.64}
            height={barH}
            rx={1.5}
            fill={color}
            opacity="0.85"
            style={{
              transformOrigin: `${X0 + i * gap + gap * 0.5}px ${Y0}px`,
              transition: "height 120ms cubic-bezier(0.16,1,0.3,1), y 120ms",
            }}
          />
        );
      })}
    </g>
  ), [seeds, color]);
}
