import { QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import { queryClient } from "./query/client";
import { useViewStore } from "./stores/view";
import "./styles.css";

// Hook para automatización (scripts/audit_mobile.py, smoke E2E).
// Permite cambiar de vista sin pasar por la UI: window.__orion.setView('mcp').
// Es un escape-hatch barato — no lo uses para features productivas.
declare global {
  interface Window {
    __orion?: { setView: (v: string) => void };
  }
}
if (typeof window !== "undefined") {
  window.__orion = {
    setView: (v: string) =>
      useViewStore.setState({ view: v as ReturnType<typeof useViewStore.getState>["view"] }),
  };
}
// NOTA: el CSS de KaTeX se importa desde `lib/markdown.tsx`. Como
// markdown es lazy-loaded (sólo lo trae ChatPanel cuando se monta),
// Vite emite el CSS de KaTeX en un chunk aparte que sólo se carga
// cuando renderizás Markdown — no en el paint inicial.

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);

// ── Service worker (PWA) ─────────────────────────────────────────────
// Los SW exigen secure context: sólo se registran en HTTPS o sobre
// localhost/127.0.0.1. Sobre Tailscale HTTP plano (100.x.y.z) el
// browser rechaza el registro — el manifest sigue funcionando para
// "Agregar a inicio" desde Safari/Chrome móvil, sólo no hay cache
// offline. Para tener SW desde el móvil hay que usar Tailscale Funnel
// (HTTPS real) o servir el backend detrás de un reverse-proxy TLS.
if ("serviceWorker" in navigator) {
  const isSecure =
    window.isSecureContext ||
    window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1";
  if (isSecure) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        // Silencioso: en dev (vite) o si el host no sirve sw.js bajo /,
        // el registro falla. No afecta funcionalidad — sólo la cache.
      });
    });
  }
}
