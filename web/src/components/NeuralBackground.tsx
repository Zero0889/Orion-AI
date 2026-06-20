/**
 * NeuralBackground — fondo tecnológico global "neural core".
 *
 * Capas (de fondo a frente):
 *   1. Glow radial central + viñeta cinemática.
 *   2. Grilla de puntos sutil.
 *   3. 4 anillos concéntricos rotando opuestos (sólo en intensity=full).
 *   4. Nodos pulsantes distribuidos en órbita (sólo en intensity=full).
 *
 * En modo `ambient` (vistas != home) se renderizan SÓLO las capas 1 y 2
 * — sin anillos, sin nodos, sin crosshair, sin líneas de energía. Esto
 * evita que aparezcan fragmentos de anillos / cruces / nodos clipeados
 * en los bordes del viewport en vistas como chat, notas o ajustes.
 *
 * Toda la capa es `pointer-events-none`. El sistema de colores reusa los
 * tokens del tema (--orion-pri / --orion-pri-glow), por lo que cambiar
 * tema cambia el fondo también.
 */

interface Props {
  intensity?: "full" | "ambient";
}

const RING_NODES = [
  // anillo externo
  { r: 480, deg: 0 },
  { r: 480, deg: 60 },
  { r: 480, deg: 120 },
  { r: 480, deg: 180 },
  { r: 480, deg: 240 },
  { r: 480, deg: 300 },
  // anillo medio
  { r: 360, deg: 30 },
  { r: 360, deg: 110 },
  { r: 360, deg: 210 },
  { r: 360, deg: 320 },
  // anillo interno
  { r: 240, deg: 70 },
  { r: 240, deg: 250 },
];

export function NeuralBackground({ intensity = "full" }: Props) {
  const isAmbient = intensity === "ambient";
  return (
    <div
      aria-hidden
      className={[
        "absolute inset-0 overflow-hidden pointer-events-none",
        isAmbient ? "nb-ambient" : "",
      ].join(" ")}
    >
      {/* Plano 1A: glow radial central */}
      <div className="nb-glow absolute inset-0" />

      {/* Plano 1B: viñeta cinemática (oscurece bordes) */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: "radial-gradient(ellipse at center, transparent 50%, rgb(0 0 0 / 0.55) 100%)",
        }}
      />

      {/* Plano 2A: grilla de puntos */}
      <div className="nb-grid absolute inset-0" />

      {/* En vistas != home no rendereamos los anillos / crosshatch /
          nodos / cruz / líneas. Razón: esos elementos están centrados
          en el viewport y al cortarse en bordes se ven como "mira" o
          "líneas flotantes" sueltas. Sólo aparecen en Inicio, donde el
          orb central anchorea la composición. */}
      {isAmbient ? null : (
        <>
          {/* Plano 2B: crosshatch HUD muy sutil */}
          <div
            className="absolute inset-0 opacity-[0.35] mix-blend-screen"
            style={{
              backgroundImage:
                "linear-gradient(rgb(var(--orion-pri) / 0.025) 1px, transparent 1px), linear-gradient(90deg, rgb(var(--orion-pri) / 0.025) 1px, transparent 1px)",
              backgroundSize: "120px 120px",
            }}
          />

          {/* Plano 3-6: SVG con anillos, nodos, líneas, crosshair */}
          <svg
            viewBox="-560 -560 1120 1120"
            preserveAspectRatio="xMidYMid slice"
            className="nb-rings absolute inset-0 w-full h-full"
          >
            <defs>
              <radialGradient id="nb-mid-grad" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="rgb(var(--orion-pri))" stopOpacity="0.0" />
                <stop offset="70%" stopColor="rgb(var(--orion-pri))" stopOpacity="0.20" />
                <stop offset="100%" stopColor="rgb(var(--orion-pri))" stopOpacity="0.0" />
              </radialGradient>
              <radialGradient id="nb-center-glow" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="rgb(var(--orion-pri-glow))" stopOpacity="0.18" />
                <stop offset="100%" stopColor="rgb(var(--orion-pri-glow))" stopOpacity="0.0" />
              </radialGradient>
            </defs>

            {/* Pulso radial central (estático, glow) */}
            <circle cx="0" cy="0" r="200" fill="url(#nb-center-glow)" />

            {/* Anillo más externo — rotación reversa 110s */}
            <g className="nb-rotate-rev" style={{ animationDuration: "110s" }}>
              <circle
                cx="0"
                cy="0"
                r="510"
                fill="none"
                stroke="rgb(var(--orion-pri) / 0.08)"
                strokeWidth="0.6"
                strokeDasharray="1 14"
              />
              <circle
                cx="0"
                cy="0"
                r="500"
                fill="none"
                stroke="rgb(var(--orion-pri) / 0.12)"
                strokeWidth="0.4"
              />
            </g>

            {/* Anillo externo principal — rotación 80s */}
            <g className="nb-rotate-slow" style={{ animationDuration: "80s" }}>
              <circle
                cx="0"
                cy="0"
                r="480"
                fill="none"
                stroke="rgb(var(--orion-pri) / 0.14)"
                strokeWidth="0.8"
                strokeDasharray="3 10"
              />
              {/* Bloque de marcas radiales para sensación de instrumento */}
              {Array.from({ length: 48 }).map((_, i) => {
                const a = (((i * 360) / 48) * Math.PI) / 180;
                const r1 = 480,
                  r2 = i % 4 === 0 ? 466 : 472;
                return (
                  <line
                    key={`tick-${i}`}
                    x1={Math.cos(a) * r1}
                    y1={Math.sin(a) * r1}
                    x2={Math.cos(a) * r2}
                    y2={Math.sin(a) * r2}
                    stroke="rgb(var(--orion-pri) / 0.18)"
                    strokeWidth="0.6"
                  />
                );
              })}
            </g>

            {/* Anillo medio — rotación normal con halo gradient */}
            <g className="nb-rotate-slow">
              <circle
                cx="0"
                cy="0"
                r="360"
                fill="none"
                stroke="rgb(var(--orion-pri) / 0.14)"
                strokeWidth="0.6"
                strokeDasharray="2 6"
              />
              <circle
                cx="0"
                cy="0"
                r="358"
                fill="none"
                stroke="url(#nb-mid-grad)"
                strokeWidth="16"
                opacity="0.4"
              />
            </g>

            {/* Anillo interno — fino, reverso */}
            <g className="nb-rotate-rev" style={{ animationDuration: "50s" }}>
              <circle
                cx="0"
                cy="0"
                r="240"
                fill="none"
                stroke="rgb(var(--orion-pri) / 0.12)"
                strokeWidth="0.5"
                strokeDasharray="1 5"
              />
              {/* segmentos brillantes del anillo interno */}
              {[0, 120, 240].map((deg) => {
                const a = (deg * Math.PI) / 180;
                const sweep = (20 * Math.PI) / 180;
                const x1 = Math.cos(a) * 240;
                const y1 = Math.sin(a) * 240;
                const x2 = Math.cos(a + sweep) * 240;
                const y2 = Math.sin(a + sweep) * 240;
                return (
                  <path
                    key={`seg-${deg}`}
                    d={`M ${x1} ${y1} A 240 240 0 0 1 ${x2} ${y2}`}
                    fill="none"
                    stroke="rgb(var(--orion-pri))"
                    strokeOpacity="0.6"
                    strokeWidth="2"
                    strokeLinecap="round"
                  />
                );
              })}
            </g>

            {/* Nodos pulsantes en los anillos */}
            {RING_NODES.map((n, i) => {
              const a = (n.deg * Math.PI) / 180;
              const x = Math.cos(a) * n.r;
              const y = Math.sin(a) * n.r;
              return (
                <g
                  key={`node-${i}`}
                  className="nb-node"
                  style={{ animationDelay: `${(i * 0.4) % 4.5}s` }}
                >
                  <circle cx={x} cy={y} r="3.2" fill="rgb(var(--orion-pri))" />
                  <circle
                    cx={x}
                    cy={y}
                    r="6"
                    fill="none"
                    stroke="rgb(var(--orion-pri) / 0.4)"
                    strokeWidth="0.8"
                  />
                </g>
              );
            })}

            {/* Líneas de "energía viajando" cruzando el centro */}
            <g opacity="0.55">
              <line
                x1="-500"
                y1="0"
                x2="500"
                y2="0"
                stroke="rgb(var(--orion-pri) / 0.10)"
                strokeWidth="0.6"
                className="orbit-line"
              />
              <line
                x1="0"
                y1="-500"
                x2="0"
                y2="500"
                stroke="rgb(var(--orion-pri) / 0.10)"
                strokeWidth="0.6"
                className="orbit-line"
                style={{ animationDelay: "-9s" }}
              />
              <line
                x1="-353"
                y1="-353"
                x2="353"
                y2="353"
                stroke="rgb(var(--orion-pri) / 0.06)"
                strokeWidth="0.5"
                className="orbit-line"
                style={{ animationDelay: "-4s" }}
              />
              <line
                x1="353"
                y1="-353"
                x2="-353"
                y2="353"
                stroke="rgb(var(--orion-pri) / 0.06)"
                strokeWidth="0.5"
                className="orbit-line"
                style={{ animationDelay: "-13s" }}
              />
            </g>

            {/* Crosshair central muy sutil */}
            <g opacity="0.45">
              <line
                x1="-30"
                y1="0"
                x2="-12"
                y2="0"
                stroke="rgb(var(--orion-pri) / 0.4)"
                strokeWidth="0.6"
              />
              <line
                x1="12"
                y1="0"
                x2="30"
                y2="0"
                stroke="rgb(var(--orion-pri) / 0.4)"
                strokeWidth="0.6"
              />
              <line
                x1="0"
                y1="-30"
                x2="0"
                y2="-12"
                stroke="rgb(var(--orion-pri) / 0.4)"
                strokeWidth="0.6"
              />
              <line
                x1="0"
                y1="12"
                x2="0"
                y2="30"
                stroke="rgb(var(--orion-pri) / 0.4)"
                strokeWidth="0.6"
              />
            </g>
          </svg>
        </>
      )}
    </div>
  );
}
