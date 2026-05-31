/**
 * App — shell principal del frontend Orion.
 *
 * Layout dos columnas:
 *   - izquierda: OrbHUD + controles globales (mute, interrupt)
 *   - derecha:   ChatPanel
 *
 * El estado se hidrata desde el WebSocket via useOrionSocket. Cada
 * componente lee del store de Zustand.
 */

import { useEffect, useState } from "react";

import { ChatPanel } from "@/components/ChatPanel";
import { OrbHUD } from "@/components/OrbHUD";
import { useOrionSocket } from "@/hooks/useOrionSocket";
import { useOrionStore } from "@/stores/orion";
import { inferBackendUrl } from "@/api/ws";

export default function App() {
  const send       = useOrionSocket();
  const muted      = useOrionStore((s) => s.muted);
  const connected  = useOrionStore((s) => s.connected);
  const [version, setVersion] = useState<string>("");

  // Pequeño fetch al endpoint /api/health para mostrar versión del backend.
  useEffect(() => {
    const { http } = inferBackendUrl();
    fetch(`${http}/api/health`)
      .then((r) => r.json())
      .then((d) => setVersion(d.version))
      .catch(() => setVersion("?"));
  }, []);

  return (
    <div className="h-screen w-screen grid grid-cols-[440px_1fr] bg-bg">
      {/* Columna izquierda — orb + controles */}
      <aside className="flex flex-col items-center justify-between p-8 border-r border-border-b">
        <header className="w-full">
          <h1 className="text-lg font-mono tracking-[0.4em]">O.R.I.O.N</h1>
          <p className="text-[10px] uppercase tracking-widest text-text-dim mt-1">
            Operador de Redes Inteligentes y Optimización Neural
          </p>
        </header>

        <OrbHUD />

        <div className="w-full flex flex-col gap-2">
          <button
            onClick={() => send("mute", { value: !muted })}
            className={`w-full text-sm rounded-md border px-3 py-2 transition
              ${muted
                ? "bg-pri/20 border-pri text-pri"
                : "bg-panel2 border-border-b text-text hover:border-pri"}`}
          >
            {muted ? "Activar micrófono" : "Silenciar micrófono"}
          </button>
          <button
            onClick={() => send("interrupt")}
            className="w-full text-sm rounded-md border border-border-b bg-panel2
                       text-text-dim hover:text-pri hover:border-pri transition px-3 py-2"
          >
            Interrumpir
          </button>
        </div>

        <footer className="text-[10px] uppercase tracking-widest text-text-dim">
          backend v{version || "…"} · {connected ? "online" : "offline"}
        </footer>
      </aside>

      {/* Columna derecha — chat */}
      <main className="flex flex-col">
        <ChatPanel onSend={(t) => send("text", { text: t })} />
      </main>
    </div>
  );
}
