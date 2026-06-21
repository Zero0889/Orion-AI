/**
 * useEyeState — deriva el estado actual del ojo de Orion (idle / listening
 * / thinking / speaking / error) leyendo los stores de Orion + interacción.
 *
 * Antes esta misma lógica vivía duplicada en `BackgroundEye.tsx` y
 * `TopBar.tsx`. Acá vive una sola vez. App.tsx la usa para escribir el
 * estado en `<html data-eye-state="...">` y que el CSS pueda teñir el
 * chrome (sidebar + topbar) al ritmo del ojo.
 */

import { useInteractionStore } from "@/stores/interaction";
import { useOrionStore } from "@/stores/orion";

export type DerivedEyeState = "idle" | "listening" | "thinking" | "speaking" | "error";

export function useEyeState(): DerivedEyeState {
  const state = useOrionStore((s) => s.state);
  const muted = useOrionStore((s) => s.muted);
  const connected = useOrionStore((s) => s.connected);
  const activeTool = useInteractionStore((s) => s.tool);
  const activeAgent = useInteractionStore((s) => s.agent);

  if (!connected || muted) return "idle";
  if (activeTool || activeAgent?.status === "running") return "thinking";
  if (state === "ESCUCHANDO") return "listening";
  if (state === "PENSANDO") return "thinking";
  if (state === "HABLANDO") return "speaking";
  return "idle";
}
