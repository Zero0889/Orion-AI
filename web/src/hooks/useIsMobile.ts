/**
 * useIsMobile — true si el viewport es chico (≤ 640 px).
 *
 * Permite skipear React subtrees pesados en mobile (BackgroundEye,
 * NeuralBackground full, partículas, etc.) en vez de sólo apagarlos
 * por CSS — los componentes ni siquiera se montan, así que tampoco
 * cuestan reconciliation ni layout passes.
 *
 * Re-evalúa en resize/orientation change. Hidrata desde un primer
 * matchMedia para evitar parpadeo del render inicial.
 */

import { useEffect, useState } from "react";

const MOBILE_BREAKPOINT = 640;

function readInitial(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT}px)`).matches;
  } catch {
    return false;
  }
}

export function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState<boolean>(readInitial);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const mq = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT}px)`);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    // Safari < 14 usa addListener; el resto addEventListener.
    if ("addEventListener" in mq) {
      mq.addEventListener("change", handler);
      return () => mq.removeEventListener("change", handler);
    }
    const legacy = mq as unknown as {
      addListener: (cb: (e: MediaQueryListEvent) => void) => void;
      removeListener: (cb: (e: MediaQueryListEvent) => void) => void;
    };
    legacy.addListener(handler);
    return () => legacy.removeListener(handler);
  }, []);

  return isMobile;
}
