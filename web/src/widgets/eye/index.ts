/**
 * @/widgets/eye — el "Ojo de Orion".
 *
 * Feature-folder cohesivo: renderer SVG (`EyeCore`), wrapper de fondo
 * ambiental (`BackgroundEye`), derivación del estado a partir de los
 * stores (`useEyeState`), bridge mundo→pulsos (`useEventPulses`) y el
 * store interno de pulsos. Todo lo público se re-exporta acá.
 *
 * Internals que NO se re-exportan:
 *   - `pulseStore.ts` — el `useEyePulseStore` lo consumen sólo `EyeCore`
 *     y `useEventPulses` adentro del widget. Mantenerlo privado evita
 *     que consumidores externos disparen pulsos directos saltándose la
 *     política de filtrado de `useEventPulses`.
 */

export { BackgroundEye } from "./BackgroundEye";
export { EyeCore, type EyeState, type EyePalette } from "./EyeCore";
export { useEyeState, type DerivedEyeState } from "./useEyeState";
export { useEventPulses } from "./useEventPulses";
