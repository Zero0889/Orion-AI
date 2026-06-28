/**
 * TopBar — workspace context bar.
 *
 * Left  : sidebar collapse toggle + workspace title (current view label).
 * Right : global controls (mute / interrupt), mini-orb status, version
 *         chip + connection chip.
 *
 * Pure presentation — actions come in as props from the shell.
 */

import { useInteractionStore } from "@/stores/interaction";
import { useOrionStore } from "@/stores/orion";
import { useViewStore, type View } from "@/stores/view";
import { Icon } from "@/ui/Icon";
import { Button, Kbd } from "@/ui/primitives";
import { useCommandPalette } from "@/widgets/command-palette";
import { EyeCore, type EyeState } from "@/widgets/eye";

const VIEW_TITLE: Record<View, { eyebrow: string; title: string }> = {
  home: { eyebrow: "Espacio", title: "Inicio" },
  chat: { eyebrow: "Espacio", title: "Conversación" },
  notes: { eyebrow: "Conocimiento", title: "Notas rápidas" },
  memory: { eyebrow: "Conocimiento", title: "Memoria" },
  history: { eyebrow: "Conocimiento", title: "Historial" },
  telemetry: { eyebrow: "Sistema", title: "Telemetría" },
  agents: { eyebrow: "Sistema", title: "Agentes autónomos" },
  iot: { eyebrow: "Sistema", title: "IoT" },
  access: { eyebrow: "Sistema", title: "Acceso por huella" },
  mcp: { eyebrow: "Sistema", title: "Servidores MCP" },
  skills: { eyebrow: "Sistema", title: "Skills" },
  notifications: { eyebrow: "Sistema", title: "Notificaciones" },
  circuit: { eyebrow: "Herramientas", title: "Circuitos" },
  diagnostics: { eyebrow: "Sistema", title: "Diagnóstico" },
  settings: { eyebrow: "Sistema", title: "Ajustes" },
};

interface Props {
  version: string;
  collapsed: boolean;
  onToggleRail: () => void;
  onToggleMute: () => void;
  onInterrupt: () => void;
}

/**
 * Mapea el estado real de Orion al EyeState que entiende EyeCore.
 * tool/agent reusan "thinking" — mismo magenta.
 */
function deriveEyeState({
  state,
  tool,
  agentRunning,
}: {
  state: string;
  tool: boolean;
  agentRunning: boolean;
}): EyeState {
  if (tool || agentRunning) return "thinking";
  if (state === "ESCUCHANDO") return "listening";
  if (state === "PENSANDO") return "thinking";
  if (state === "HABLANDO") return "speaking";
  return "idle";
}

export function TopBar({ version, collapsed, onToggleRail, onToggleMute, onInterrupt }: Props) {
  const view = useViewStore((s) => s.view);
  const muted = useOrionStore((s) => s.muted);
  const connected = useOrionStore((s) => s.connected);
  const state = useOrionStore((s) => s.state);
  const tool = useInteractionStore((s) => s.tool);
  const agent = useInteractionStore((s) => s.agent);
  const openPalette = useCommandPalette((s) => s.toggle);
  const { eyebrow, title } = VIEW_TITLE[view];

  const eyeState = deriveEyeState({
    state,
    tool: Boolean(tool),
    agentRunning: agent?.status === "running",
  });
  // Sin conexión o silenciado → modo `frozen` (mismo ojo del Inicio:
  // azul sobrio + quieto). Con conexión → `paused` (mismo ojo, cambia
  // de color por estado, sin moverse).
  const eyeFrozen = !connected || muted;

  return (
    <header
      className="relative h-14 flex items-center gap-1.5 sm:gap-3 px-2 sm:px-3 border-b border-white/[0.06]
                          bg-gradient-to-r from-bg/80 via-bg/60 to-bg/80 backdrop-blur-md chrome-edge-bottom"
    >
      {/* rail toggle / drawer trigger en mobile */}
      <button
        onClick={onToggleRail}
        title={collapsed ? "Expandir barra lateral" : "Contraer barra lateral"}
        className="shrink-0 h-8 w-8 grid place-items-center rounded-md text-text-dim
                   hover:text-text hover:bg-white/[0.04] transition-colors"
      >
        <Icon name="panel-left" size={16} />
      </button>

      {/* workspace title — min-w-0 + flex-1 para que pueda encogerse y
          truncar correctamente en mobile en vez de empujar a otros items. */}
      <div className="min-w-0 flex-1 flex flex-col leading-tight">
        <div className="text-[10px] uppercase tracking-[0.24em] text-pri/70 truncate">
          {eyebrow}
        </div>
        <div className="text-sm font-semibold tracking-tight text-text truncate">{title}</div>
      </div>

      {/* search → abre el Command Palette. En mobile: solo icono (sin pill). */}
      <button
        onClick={openPalette}
        title="Abrir buscador de comandos (Ctrl+K o Ctrl+/)"
        aria-label="Buscar"
        className="shrink-0 hidden sm:flex items-center gap-2 h-8 px-3 rounded-md
                   border border-white/[0.06] bg-elevated/60 text-xs text-text-dim
                   hover:border-pri/40 hover:text-text hover:bg-elevated transition-all"
      >
        <Icon name="search" size={14} />
        <span className="hidden md:inline">Buscar</span>
        <Kbd>⌘K</Kbd>
      </button>
      <button
        onClick={openPalette}
        title="Buscar (Ctrl+K)"
        aria-label="Buscar"
        className="shrink-0 sm:hidden h-8 w-8 grid place-items-center rounded-md text-text-dim
                   hover:text-text hover:bg-white/[0.04] transition-colors"
      >
        <Icon name="search" size={16} />
      </button>

      {/* voice controls — el botón de interrumpir se oculta en mobile
          para que el título tenga espacio. El de mic queda siempre. */}
      <Button
        size="icon"
        variant={muted ? "danger" : "ghost"}
        onClick={onToggleMute}
        title={muted ? "Activar micrófono" : "Silenciar micrófono"}
        className="shrink-0"
      >
        <Icon name={muted ? "mic-off" : "mic"} size={16} />
      </Button>
      <Button
        size="icon"
        variant="ghost"
        onClick={onInterrupt}
        title="Interrumpir"
        className="shrink-0 hidden sm:inline-flex"
      >
        <Icon name="stop" size={16} />
      </Button>

      {/* divider — solo desktop */}
      <span className="hidden sm:block h-6 w-px bg-white/[0.08] mx-1" />

      {/* mini eye status — solo desktop. En mobile el ojo del fondo /
          backgrounds ya comunica estado; un segundo mini-ojo en la barra
          le come 34 px de ancho al título y empuja a "M." truncado. */}
      <div title={`Orion: ${state}`} className="hidden sm:grid place-items-center shrink-0">
        <EyeCore size={34} state={eyeState} paused={!eyeFrozen} frozen={eyeFrozen} />
      </div>

      {/* version + connection chip + repo link */}
      <div
        className="hidden lg:flex items-center gap-1 h-8 pl-2.5 pr-1 rounded-md
                      border border-white/[0.06] bg-elevated/60 text-[10px] uppercase tracking-[0.16em]"
      >
        <span
          className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-ok shadow-[0_0_8px_rgb(var(--orion-ok))]" : "bg-muted"}`}
        />
        <span className="text-text-dim numeric">v{version || "…"}</span>
        <span className="mx-1 h-3 w-px bg-white/[0.08]" aria-hidden="true" />
        <a
          href="https://github.com/Zero0889/Orion-AI"
          target="_blank"
          rel="noopener noreferrer"
          title="Orion AI · creado por Zahir Padilla · ver en GitHub"
          aria-label="Abrir repositorio en GitHub"
          className="h-6 w-6 grid place-items-center rounded text-text-dim
                     hover:text-text hover:bg-white/[0.06] transition-colors"
        >
          <Icon name="github" size={13} />
        </a>
      </div>
    </header>
  );
}
