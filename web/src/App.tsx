/**
 * App — shell principal del frontend Orion (Fase 3).
 *
 * Layout 3 columnas:
 *   - sidebar (88 px):  navegación entre vistas
 *   - orb     (380 px): estado del asistente + controles globales
 *   - main:   ChatPanel | NotesPanel | MemoryPanel | HistoryPanel | SettingsPanel
 *
 * El WebSocket se monta una sola vez en App; cada panel reacciona a su
 * propio contador en useOrionStore.rev (notes / memory / convs / theme).
 */

import { useEffect, useState } from "react";

import { ChatPanel } from "@/components/ChatPanel";
import { HistoryPanel } from "@/components/HistoryPanel";
import { MemoryPanel } from "@/components/MemoryPanel";
import { NotesPanel } from "@/components/NotesPanel";
import { OrbHUD } from "@/components/OrbHUD";
import { SettingsPanel } from "@/components/SettingsPanel";
import { Sidebar } from "@/components/Sidebar";
import { useOrionSocket } from "@/hooks/useOrionSocket";
import { useOrionStore } from "@/stores/orion";
import { useViewStore } from "@/stores/view";
import { inferBackendUrl } from "@/api/ws";

export default function App() {
  const send       = useOrionSocket();
  const view       = useViewStore((s) => s.view);
  const muted      = useOrionStore((s) => s.muted);
  const connected  = useOrionStore((s) => s.connected);
  const [version, setVersion] = useState<string>("");

  useEffect(() => {
    const { http } = inferBackendUrl();
    fetch(`${http}/api/health`)
      .then((r) => r.json())
      .then((d) => setVersion(d.version))
      .catch(() => setVersion("?"));
  }, []);

  return (
    <div className="h-screen w-screen grid grid-cols-[88px_380px_1fr] bg-bg">
      {/* Sidebar de navegación */}
      <aside className="flex flex-col items-stretch justify-between p-3 border-r border-border-b">
        <div>
          <div className="text-center mb-4">
            <div className="text-[10px] font-mono tracking-[0.3em] text-pri">ORION</div>
          </div>
          <Sidebar />
        </div>
        <div className="text-[9px] uppercase tracking-widest text-text-dim text-center">
          v{version || "…"}
          <br />
          {connected ? <span className="text-pri">● online</span> : <span>○ offline</span>}
        </div>
      </aside>

      {/* Orb + controles globales */}
      <section className="flex flex-col items-center justify-between p-8 border-r border-border-b">
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
      </section>

      {/* Vista activa */}
      <main className="flex flex-col overflow-hidden">
        {view === "chat"     && <ChatPanel onSend={(t) => send("text", { text: t })} />}
        {view === "notes"    && <NotesPanel />}
        {view === "memory"   && <MemoryPanel />}
        {view === "history"  && <HistoryPanel />}
        {view === "settings" && <SettingsPanel />}
      </main>
    </div>
  );
}
