/**
 * EyePulses — overlay de pulsos del Eye, separado de EyeCore.
 *
 * Antes EyeCore.tsx leía `useEyePulseStore` directamente, así que cada
 * vez que llegaba/expiraba un pulso, React re-rendereaba el SVG entero
 * (36 filamentos + 8 partículas + ~12 anillos animados). Con muchos
 * sensores o herramientas activas eso causaba lag visible.
 *
 * Acá vive sólo el subárbol que depende de los pulsos. EyeCore es
 * estático ahora; el único re-render por pulso ocurre en este componente
 * chiquito. Como se monta como hijo del `<svg>` y `<g clipPath>` del
 * padre, hereda automáticamente el viewBox y el clip del socket — no
 * hace falta duplicar el SVG.
 */

import { useEyePulseStore } from "./pulseStore";

export function EyePulses() {
  const pulses = useEyePulseStore((s) => s.active);
  if (pulses.length === 0) return null;
  return (
    <g className="ec-pulses" pointerEvents="none">
      {pulses.map((p) => (
        /* Tres anillos por pulso con delay escalonado: la onda se ve
           triple, no como un trazo solo. */
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
  );
}
