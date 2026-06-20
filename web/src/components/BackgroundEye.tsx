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
 */

import { EyeCore, type EyeState } from "@/components/EyeCore";
import { useInteractionStore } from "@/stores/interaction";
import { useOrionStore } from "@/stores/orion";
import { useViewStore } from "@/stores/view";

export function BackgroundEye() {
  const state = useOrionStore((s) => s.state);
  const muted = useOrionStore((s) => s.muted);
  const connected = useOrionStore((s) => s.connected);
  const messages = useOrionStore((s) => s.messages);
  const view = useViewStore((s) => s.view);

  const activeTool = useInteractionStore((s) => s.tool);
  const activeAgent = useInteractionStore((s) => s.agent);

  const eyeState: EyeState =
    !connected || muted
      ? "idle"
      : activeTool
        ? "thinking"
        : activeAgent?.status === "running"
          ? "thinking"
          : state === "ESCUCHANDO"
            ? "listening"
            : state === "PENSANDO"
              ? "thinking"
              : state === "HABLANDO"
                ? "speaking"
                : "idle";

  // En la vista "chat", el ojo grande solo aparece después del primer
  // turno real (usuario o IA). En el estado inicial — el Hero — el ojo
  // queda invisible para que la composición empiece limpia y el ojo
  // "cobre vida" recién al enviar el primer mensaje.
  const chatEmpty = view === "chat" && !messages.some((m) => m.role === "user" || m.role === "ai");

  return (
    <div
      className="absolute inset-0 overflow-hidden pointer-events-none transition-opacity duration-700 ease-out"
      style={{ opacity: chatEmpty ? 0 : 1 }}
    >
      <EyeCore state={eyeState} background frozen={!connected} />
    </div>
  );
}
