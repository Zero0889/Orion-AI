/**
 * BackgroundEye — el ojo de Orion como fondo ambiental.
 *
 * Mismo SVG que el centerpiece de Inicio, pero gigante, recortado a la
 * derecha y al ~13 % de opacidad. Va detrás del contenido en todas las
 * vistas que NO son `home` (en home ya manda el centerpiece).
 *
 * Reacciona al estado real del backend (escuchando / pensando /
 * hablando / error), exactamente igual que el OrbHUD del Inicio, así
 * el usuario nunca pierde feedback visual de qué está haciendo Orion.
 *
 * Performance: la derivación de eyeState vive en `useEyeState` (hook
 * compartido con TopBar/App). La detección de "chat vacío" se hace por
 * **selector boolean** sobre el store de mensajes — antes este componente
 * leía el array completo y se re-renderizaba con cada chunk del stream
 * de Gemini, lo que repintaba el SVG entero (con sus 36 filamentos,
 * partículas y anillos animados) varias veces por segundo durante la
 * conversación.
 */

import { memo } from "react";

import { useOrionStore } from "@/stores/orion";
import { useViewStore } from "@/stores/view";

import { EyeCore } from "./EyeCore";
import { useEyeState } from "./useEyeState";

function selectHasRealMessage(s: ReturnType<typeof useOrionStore.getState>): boolean {
  for (const m of s.messages) {
    if (m.role === "user" || m.role === "ai") return true;
  }
  return false;
}

export const BackgroundEye = memo(function BackgroundEye() {
  const eyeState = useEyeState();
  const connected = useOrionStore((s) => s.connected);
  const view = useViewStore((s) => s.view);
  // Boolean derivado: Zustand sólo re-renderea cuando el bool cambia
  // (no en cada chunk del chat stream).
  const hasRealMessage = useOrionStore(selectHasRealMessage);

  // En la vista "chat", el ojo grande solo aparece después del primer
  // turno real (usuario o IA). En el estado inicial — el Hero — el ojo
  // queda invisible para que la composición empiece limpia y el ojo
  // "cobre vida" recién al enviar el primer mensaje.
  const chatEmpty = view === "chat" && !hasRealMessage;

  return (
    <div
      className="absolute inset-0 overflow-hidden pointer-events-none transition-opacity duration-700 ease-out"
      style={{ opacity: chatEmpty ? 0 : 1 }}
    >
      <EyeCore state={eyeState} background frozen={!connected} />
    </div>
  );
});
