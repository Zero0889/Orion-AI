import { useEyePulseStore } from "./pulseStore";

/**
 * EyeCore — el "ojo" cinemático de Orion.
 *
 * Reemplaza la antigua bolita del FullOrb. Reacciona a 5 estados:
 *   - idle       (observando)  → cian, anillos lentos, mirada robótica
 *   - listening  (escuchando)  → cian intensificado, micro-pulso del iris
 *   - thinking   (pensando)    → magenta, giro rápido, iris contraído
 *   - speaking   (hablando)    → verde-cian, dilatado, destellos de voz
 *   - error      (crítico)     → rojo intenso, triángulo de alerta
 *
 * El mismo componente sirve para:
 *   • Inicio (centerpiece, tamaño fijo)
 *   • Resto de vistas (background: gigante, baja opacidad, recortado)
 *
 * El detalle visual (gradientes, capas, anillos) vive en SVG.
 * Las animaciones por estado viven en `styles.css` bajo `.ec-*`.
 */

export type EyeState = "idle" | "listening" | "thinking" | "speaking" | "error";

/** Override de paleta — sobrescribe las variables CSS del ojo. Útil
 *  cuando el sitio quiere fijar un color (ej. sidebar siempre blanco-
 *  azul) independientemente del estado real de Orion. */
export interface EyePalette {
  main: string;
  second: string;
  glow: string;
}

interface Props {
  state?: EyeState;
  /** Cuando true, se renderiza como fondo gigante recortado a la derecha. */
  background?: boolean;
  /** "Sin conexión": congela todas las animaciones Y apaga la paleta
   *  a un azul sobrio. Para sólo congelar el movimiento sin alterar el
   *  color, usa `paused`. */
  frozen?: boolean;
  /** Congela TODAS las animaciones pero conserva la paleta del estado.
   *  Pensado para el mini-ojo del top-bar (no se mueve, sólo cambia
   *  de color). */
  paused?: boolean;
  /** Fija una paleta explícita ignorando el color del estado. Pensado
   *  para el icono del sidebar (mismo color siempre). */
  palette?: EyePalette;
  className?: string;
  /** Tamaño en px cuando NO es background. */
  size?: number;
}

const STATE_CLASS: Record<EyeState, string> = {
  idle: "",
  listening: "ec-state-listening",
  thinking: "ec-state-thinking",
  speaking: "ec-state-responding",
  error: "ec-state-error",
};

export function EyeCore({
  state = "idle",
  background = false,
  frozen = false,
  paused = false,
  palette,
  className = "",
  size = 300,
}: Props) {
  const pulses = useEyePulseStore((s) => s.active);
  const cls = [
    "ec-canvas",
    background ? "ec-bg" : "",
    // En "Sin conexión" el ojo se congela y vira a azul sobrio,
    // anulando el color del estado para que no parpadee al desconectar.
    frozen ? "ec-frozen" : STATE_CLASS[state],
    paused && !frozen ? "ec-paused" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  // Estilo final: tamaño + (opcional) override de paleta. El override
  // se hace por variables CSS scoped, así no reescribimos la cascada.
  const style: React.CSSProperties = background ? {} : { width: size, height: size };

  if (palette) {
    (style as Record<string, string>)["--ec-neon-main"] = palette.main;
    (style as Record<string, string>)["--ec-neon-second"] = palette.second;
    (style as Record<string, string>)["--ec-neon-glow"] = palette.glow;
  }

  return (
    <div className={cls} style={style} aria-hidden={background || undefined}>
      <svg viewBox="0 0 400 400" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <clipPath id="ec-eye-socket">
            <circle cx="200" cy="200" r="175" />
          </clipPath>

          {/* Esfera del globo ocular: en vez de negro plano, un gradiente
              radial off-centered crea profundidad volumétrica (look "perla
              negra"). El centro tira a azul-noche, el borde a negro puro. */}
          <radialGradient id="ec-sphere-depth" cx="42%" cy="38%" r="78%">
            <stop offset="0%" stopColor="#0a1422" />
            <stop offset="55%" stopColor="#040810" />
            <stop offset="100%" stopColor="#000000" />
          </radialGradient>

          {/* Halo interior del socket (vignette): oscurece los bordes
              internos para acentuar la curvatura esférica del ojo. */}
          <radialGradient id="ec-socket-vignette" cx="50%" cy="50%" r="50%">
            <stop offset="60%" stopColor="#000" stopOpacity="0" />
            <stop offset="100%" stopColor="#000" stopOpacity="0.65" />
          </radialGradient>

          <radialGradient id="ec-core-glow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#fff" />
            <stop offset="20%" stopColor="#fff" />
            <stop offset="50%" stopColor="var(--ec-neon-main)" />
            <stop offset="80%" stopColor="var(--ec-neon-second)" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#000" stopOpacity="0" />
          </radialGradient>

          {/* Filamentos neuronales del iris: 36 líneas radiales finas que
              parten del núcleo (r=42) hacia el borde del iris (r=72).
              Cada 3ra línea es más gruesa para crear "rayos primarios"
              + filamentos secundarios — textura tipo iris humano-HUD. */}
          <g id="ec-iris-filaments">
            {Array.from({ length: 36 }).map((_, i) => {
              const angle = (i * 360) / 36;
              const major = i % 3 === 0;
              return (
                <line
                  key={i}
                  x1="200"
                  y1={major ? 158 : 162}
                  x2="200"
                  y2={major ? 128 : 134}
                  stroke="var(--ec-neon-main)"
                  strokeWidth={major ? 0.85 : 0.4}
                  strokeOpacity={major ? 0.55 : 0.22}
                  strokeLinecap="round"
                  transform={`rotate(${angle} 200 200)`}
                />
              );
            })}
          </g>

          {/* Partículas de datos flotantes: 8 motas pequeñas que orbitan
              dentro del socket. Pinta el "pensamiento" de Orion. */}
          <g id="ec-data-particles">
            {[
              { cx: 145, cy: 130, r: 1.2, dur: "6.5s" },
              { cx: 270, cy: 165, r: 0.9, dur: "8.0s" },
              { cx: 250, cy: 260, r: 1.4, dur: "7.2s" },
              { cx: 130, cy: 245, r: 0.8, dur: "9.0s" },
              { cx: 195, cy: 105, r: 1.0, dur: "10s" },
              { cx: 305, cy: 215, r: 0.7, dur: "7.6s" },
              { cx: 110, cy: 195, r: 1.1, dur: "8.4s" },
              { cx: 215, cy: 295, r: 0.9, dur: "6.0s" },
            ].map((p, i) => (
              <circle
                key={i}
                cx={p.cx}
                cy={p.cy}
                r={p.r}
                fill="var(--ec-neon-main)"
                className="ec-particle"
                style={{ animationDuration: p.dur, animationDelay: `${i * 0.4}s` }}
              />
            ))}
          </g>
        </defs>

        {/* Globo ocular con profundidad volumétrica */}
        <circle
          cx="200"
          cy="200"
          r="185"
          fill="url(#ec-sphere-depth)"
          stroke="#0a0e14"
          strokeWidth="8"
        />
        <circle cx="200" cy="200" r="176" fill="none" stroke="#161c26" strokeWidth="4" />
        {/* Vignette interno — refuerza la curvatura esférica */}
        <circle cx="200" cy="200" r="175" fill="url(#ec-socket-vignette)" pointerEvents="none" />

        <g clipPath="url(#ec-eye-socket)">
          <g className="ec-tracking-group">
            <g
              className="ec-voice-target"
              style={{ filter: "drop-shadow(0 0 10px var(--ec-neon-glow))" }}
            >
              <circle
                className="ec-spin-cw"
                cx="200"
                cy="200"
                r="165"
                fill="none"
                stroke="var(--ec-neon-second)"
                strokeWidth="1"
                strokeDasharray="2 10"
              />
              <circle
                className="ec-spin-cw"
                cx="200"
                cy="200"
                r="160"
                fill="none"
                stroke="var(--ec-neon-main)"
                strokeWidth="0.5"
                strokeDasharray="1 1"
                opacity="0.3"
              />
              <circle
                className="ec-spin-ccw"
                cx="200"
                cy="200"
                r="150"
                fill="none"
                stroke="var(--ec-neon-main)"
                strokeWidth="2.5"
                strokeDasharray="80 15 5 15 30 40"
              />

              <circle
                className="ec-spin-cw-fast"
                cx="200"
                cy="200"
                r="130"
                fill="none"
                stroke="var(--ec-neon-main)"
                strokeWidth="16"
                strokeDasharray="4 6"
                opacity="0.8"
              />
              <circle
                cx="200"
                cy="200"
                r="122"
                fill="none"
                stroke="var(--ec-neon-second)"
                strokeWidth="1"
                strokeDasharray="1 1"
                opacity="0.6"
              />

              {/* Marcas HUD cardinales: en modo background se ocultan
                  vía CSS (.ec-bg .ec-hud-ticks) — al estar el ojo a baja
                  opacidad y clipeado, estos trazos sueltos parecían
                  "miras flotantes" en los bordes de la pantalla. */}
              <g
                className="ec-hud-ticks"
                opacity="0.6"
                stroke="var(--ec-neon-main)"
                strokeWidth="2"
              >
                <path d="M 200 60 L 200 90 M 200 310 L 200 340 M 60 200 L 90 200 M 310 200 L 340 200" />
                <circle cx="160" cy="110" r="1.5" fill="var(--ec-neon-main)" />
                <circle cx="240" cy="110" r="1.5" fill="var(--ec-neon-main)" />
                <circle cx="110" cy="160" r="1.5" fill="var(--ec-neon-main)" />
                <circle cx="110" cy="240" r="1.5" fill="var(--ec-neon-main)" />
              </g>

              <circle
                className="ec-spin-ccw"
                cx="200"
                cy="200"
                r="95"
                fill="none"
                stroke="var(--ec-neon-second)"
                strokeWidth="20"
                strokeDasharray="1 10"
                opacity="0.9"
              />
              <circle
                className="ec-spin-cw"
                cx="200"
                cy="200"
                r="82"
                fill="none"
                stroke="var(--ec-neon-main)"
                strokeWidth="8"
                strokeDasharray="8 16"
              />
              <circle
                cx="200"
                cy="200"
                r="75"
                fill="none"
                stroke="#fff"
                strokeWidth="0.5"
                opacity="0.2"
              />
            </g>

            <g className="ec-pulse-dilate">
              <circle cx="200" cy="200" r="50" fill="url(#ec-core-glow)" />

              {/* Filamentos neuronales del iris — giran junto al iris.
                  Mezcla "screen" para que se fundan con el glow. */}
              <g className="ec-iris-filaments-spin" style={{ mixBlendMode: "screen" }}>
                <use href="#ec-iris-filaments" />
              </g>

              <g className="ec-spin-cw">
                <circle
                  cx="200"
                  cy="160"
                  r="3.5"
                  fill="#fff"
                  style={{ filter: "drop-shadow(0 0 6px #fff)" }}
                />
                <circle cx="200" cy="240" r="2.5" fill="var(--ec-neon-main)" />
              </g>

              {/* Limbo: anillo fino que rodea la pupila — refuerza la
                  lectura "iris real" entre el blanco del centro y los
                  filamentos exteriores. */}
              <circle
                cx="200"
                cy="200"
                r="22"
                fill="none"
                stroke="var(--ec-neon-main)"
                strokeWidth="0.8"
                strokeOpacity="0.55"
              />

              <circle
                cx="200"
                cy="200"
                r="18"
                fill="#ffffff"
                style={{ filter: "drop-shadow(0 0 15px #fff)" }}
              />
              <circle cx="200" cy="200" r="8" fill="#010203" />
              {/* Reflejo especular dentro de la pupila — punto blanco
                  off-center, sugiere una fuente de luz superior. */}
              <circle cx="197" cy="196" r="2" fill="#ffffff" opacity="0.95" />
              <circle cx="200" cy="200" r="3" fill="var(--ec-neon-main)" />
            </g>
          </g>

          {/* Partículas de datos flotando en el socket — siempre por
              detrás del iris, por delante del fondo. Clipeadas al socket
              por estar dentro de <g clipPath>. */}
          <use href="#ec-data-particles" pointerEvents="none" />

          <g className="ec-pulses" pointerEvents="none">
            {pulses.map((p) => (
              /* Por cada pulso renderizamos tres anillos con delay escalonado
                 para que se vea una onda triple, no un trazo solo. */
              <g key={p.id}>
                <circle
                  className={`ec-pulse-ring ec-pulse-${p.kind} ec-pulse-ring-1`}
                  cx="200"
                  cy="200"
                  r="60"
                  fill="none"
                />
                <circle
                  className={`ec-pulse-ring ec-pulse-${p.kind} ec-pulse-ring-2`}
                  cx="200"
                  cy="200"
                  r="60"
                  fill="none"
                />
                <circle
                  className={`ec-pulse-ring ec-pulse-${p.kind} ec-pulse-ring-3`}
                  cx="200"
                  cy="200"
                  r="60"
                  fill="none"
                />
              </g>
            ))}
          </g>

          <circle
            className="ec-dark-overlay"
            cx="200"
            cy="200"
            r="180"
            fill="#000"
            opacity="0"
            pointerEvents="none"
          />

          <g className="ec-error-symbol-group">
            <polygon
              points="200,45 60,285 340,285"
              fill="rgba(255, 0, 17, 0.05)"
              stroke="var(--ec-neon-main)"
              strokeWidth="16"
              strokeLinejoin="round"
            />
            <polygon
              points="200,75 85,270 315,270"
              fill="none"
              stroke="var(--ec-neon-second)"
              strokeWidth="4"
              strokeDasharray="12 12"
              strokeLinejoin="round"
            />
            <line
              x1="200"
              y1="110"
              x2="200"
              y2="210"
              stroke="var(--ec-neon-main)"
              strokeWidth="18"
              strokeLinecap="round"
            />
            <circle cx="200" cy="250" r="14" fill="var(--ec-neon-main)" />
          </g>
        </g>

        {/* Reflejo superior — arco de luz que insinúa el "vidrio bombé"
            del globo ocular. Doble pase: uno sólido más estrecho para el
            highlight especular, otro ancho difuminado para el fall-off. */}
        <path
          className="ec-glass-reflection"
          d="M 60,118 Q 200,32 340,118 Q 200,92 60,118"
          fill="rgba(255, 255, 255, 0.16)"
          style={{ filter: "blur(0.5px)" }}
          pointerEvents="none"
        />
        <path
          className="ec-glass-reflection"
          d="M 90,108 Q 200,42 310,108 Q 200,80 90,108"
          fill="rgba(255, 255, 255, 0.06)"
          style={{ filter: "blur(3px)" }}
          pointerEvents="none"
        />
        {/* Highlight puntual superior-izquierda — punto especular
            preciso, no un wash. Asienta el ojo como esfera. */}
        <ellipse
          className="ec-glass-reflection"
          cx="140"
          cy="105"
          rx="22"
          ry="8"
          fill="rgba(255, 255, 255, 0.22)"
          style={{ filter: "blur(2px)" }}
          transform="rotate(-22 140 105)"
          pointerEvents="none"
        />
        {/* Reflejo inferior — más sutil, indica el rebote ambiental. */}
        <path
          className="ec-glass-reflection"
          d="M 100,348 Q 200,380 300,348 Q 200,365 100,348"
          fill="rgba(255, 255, 255, 0.04)"
          pointerEvents="none"
        />
      </svg>
    </div>
  );
}
