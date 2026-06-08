/**
 * TopBar — workspace context bar.
 *
 * Left  : sidebar collapse toggle + workspace title (current view label).
 * Right : global controls (mute / interrupt), mini-orb status, version
 *         chip + connection chip.
 *
 * Pure presentation — actions come in as props from the shell.
 */

import { useCommandPalette } from "@/components/CommandPalette";
import { OrbHUD } from "@/components/OrbHUD";
import { useOrionStore } from "@/stores/orion";
import { useViewStore, type View } from "@/stores/view";
import { Icon } from "@/ui/Icon";
import { Button, Kbd } from "@/ui/primitives";

const VIEW_TITLE: Record<View, { eyebrow: string; title: string }> = {
  home:      { eyebrow: "Espacio",      title: "Inicio" },
  chat:      { eyebrow: "Espacio",      title: "Conversación" },
  notes:     { eyebrow: "Conocimiento", title: "Notas rápidas" },
  memory:    { eyebrow: "Conocimiento", title: "Memoria" },
  history:   { eyebrow: "Conocimiento", title: "Historial" },
  telemetry: { eyebrow: "Sistema",      title: "Telemetría" },
  agents:    { eyebrow: "Sistema",      title: "Agentes autónomos" },
  iot:       { eyebrow: "Sistema",      title: "IoT" },
  mcp:       { eyebrow: "Sistema",      title: "Servidores MCP" },
  skills:    { eyebrow: "Sistema",      title: "Skills" },
  notifications: { eyebrow: "Sistema",  title: "Notificaciones" },
  settings:  { eyebrow: "Sistema",      title: "Ajustes" },
};

interface Props {
  version:        string;
  collapsed:      boolean;
  onToggleRail:   () => void;
  onToggleMute:   () => void;
  onInterrupt:    () => void;
}

export function TopBar({
  version, collapsed, onToggleRail, onToggleMute, onInterrupt,
}: Props) {
  const view      = useViewStore((s) => s.view);
  const muted     = useOrionStore((s) => s.muted);
  const connected = useOrionStore((s) => s.connected);
  const openPalette = useCommandPalette((s) => s.toggle);
  const { eyebrow, title } = VIEW_TITLE[view];

  return (
    <header className="relative h-14 flex items-center gap-3 px-4 border-b border-white/[0.06]
                          bg-gradient-to-r from-bg/80 via-bg/60 to-bg/80 backdrop-blur-md">
      {/* rail toggle */}
      <button
        onClick={onToggleRail}
        title={collapsed ? "Expandir barra lateral" : "Contraer barra lateral"}
        className="h-8 w-8 grid place-items-center rounded-md text-text-dim
                   hover:text-text hover:bg-white/[0.04] transition-colors"
      >
        <Icon name="panel-left" size={16} />
      </button>

      {/* workspace title */}
      <div className="min-w-0 flex flex-col leading-tight">
        <div className="text-[10px] uppercase tracking-[0.24em] text-pri/70">{eyebrow}</div>
        <div className="text-sm font-semibold tracking-tight text-text truncate">{title}</div>
      </div>

      <div className="flex-1" />

      {/* search → abre el Command Palette */}
      <button
        onClick={openPalette}
        title="Abrir buscador de comandos (Ctrl+K o Ctrl+/)"
        className="flex items-center gap-2 h-8 px-3 rounded-md
                   border border-white/[0.06] bg-elevated/60 text-xs text-text-dim
                   hover:border-pri/40 hover:text-text hover:bg-elevated transition-all"
      >
        <Icon name="search" size={14} />
        <span className="hidden md:inline">Buscar</span>
        <Kbd>⌘K</Kbd>
      </button>

      {/* global voice controls */}
      <Button
        size="icon"
        variant={muted ? "danger" : "ghost"}
        onClick={onToggleMute}
        title={muted ? "Activar micrófono" : "Silenciar micrófono"}
      >
        <Icon name={muted ? "mic-off" : "mic"} size={16} />
      </Button>
      <Button
        size="icon"
        variant="ghost"
        onClick={onInterrupt}
        title="Interrumpir"
      >
        <Icon name="stop" size={16} />
      </Button>

      {/* divider */}
      <span className="h-6 w-px bg-white/[0.08] mx-1" />

      {/* mini orb status */}
      <OrbHUD size="mini" />

      {/* version + connection chip */}
      <div className="hidden lg:flex items-center gap-1.5 h-8 px-2.5 rounded-md
                      border border-white/[0.06] bg-elevated/60 text-[10px] uppercase tracking-[0.16em]">
        <span className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-ok shadow-[0_0_8px_rgb(var(--orion-ok))]" : "bg-muted"}`} />
        <span className="text-text-dim">v{version || "…"}</span>
      </div>
    </header>
  );
}
