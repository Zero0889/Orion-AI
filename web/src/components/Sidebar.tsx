/**
 * Sidebar — premium navigation with sections, SVG icons, glow on active.
 *
 * Sections:
 *   workspace  → chat
 *   knowledge  → notes / memory / history
 *   system     → telemetry / agents / iot / settings
 *
 * Collapsed mode hides the labels and shrinks the rail; the parent shell
 * toggles it via the `collapsed` prop.
 */

import { useViewStore, type View } from "@/stores/view";
import { Icon, type IconName } from "@/ui/Icon";

interface Item {
  id:    View;
  label: string;
  icon:  IconName;
}
interface Section {
  label: string;
  items: Item[];
}

const SECTIONS: Section[] = [
  {
    label: "Espacio",
    items: [
      { id: "home", label: "Inicio",        icon: "orbit" },
      { id: "chat", label: "Conversación",  icon: "chat" },
    ],
  },
  {
    label: "Conocimiento",
    items: [
      { id: "notes",   label: "Notas",     icon: "notes" },
      { id: "memory",  label: "Memoria",   icon: "memory" },
      { id: "history", label: "Historial", icon: "history" },
    ],
  },
  {
    label: "Herramientas",
    items: [
      { id: "circuit",   label: "Circuitos",  icon: "cpu" },
    ],
  },
  {
    label: "Sistema",
    items: [
      { id: "telemetry", label: "Telemetría", icon: "telemetry" },
      { id: "agents",    label: "Agentes",    icon: "agents" },
      { id: "iot",       label: "IoT",        icon: "iot" },
      { id: "mcp",       label: "MCP",        icon: "plug" },
      { id: "skills",    label: "Skills",     icon: "sparkles" },
      { id: "notifications", label: "Notificaciones", icon: "bell" },
      { id: "settings",  label: "Ajustes",    icon: "settings" },
    ],
  },
];

interface Props {
  collapsed?: boolean;
}

export function Sidebar({ collapsed = false }: Props) {
  const view    = useViewStore((s) => s.view);
  const setView = useViewStore((s) => s.setView);

  return (
    <nav className="flex flex-col gap-5 w-full">
      {SECTIONS.map((sec) => (
        <div key={sec.label} className="flex flex-col gap-0.5">
          {!collapsed && (
            <div className="px-3 mb-1 text-micro uppercase tracking-[0.24em] text-muted">
              {sec.label}
            </div>
          )}
          {sec.items.map((it) => {
            const active = view === it.id;
            return (
              <button
                key={it.id}
                onClick={() => setView(it.id)}
                title={collapsed ? it.label : undefined}
                className={[
                  "group relative flex items-center rounded-lg",
                  collapsed ? "justify-center h-10 w-10 mx-auto" : "gap-3 px-3 h-9",
                  "text-sm transition-all duration-200 ease-out-expo",
                  "border border-transparent",
                  active
                    ? "bg-elevated text-text border-white/[0.06] shadow-rim"
                    : "text-text-dim hover:text-text hover:bg-white/[0.03]",
                ].join(" ")}
              >
                {/* left rail glow when active */}
                <span
                  aria-hidden
                  className={[
                    "absolute left-0 top-1.5 bottom-1.5 w-[2px] rounded-full",
                    "transition-all duration-300 ease-out-expo",
                    active
                      ? "bg-pri shadow-[0_0_10px_rgb(var(--orion-pri)/0.7)] opacity-100"
                      : "bg-pri opacity-0 group-hover:opacity-30",
                  ].join(" ")}
                />
                <Icon
                  name={it.icon}
                  size={collapsed ? 18 : 16}
                  className={[
                    "shrink-0 transition-colors duration-200",
                    active ? "text-pri" : "text-text-dim group-hover:text-text",
                  ].join(" ")}
                />
                {!collapsed && (
                  <span className="truncate font-medium tracking-tight">{it.label}</span>
                )}

                {/* subtle hover halo */}
                {!active && (
                  <span
                    aria-hidden
                    className="absolute inset-0 rounded-lg opacity-0 group-hover:opacity-100
                               transition-opacity duration-300 pointer-events-none
                               bg-[radial-gradient(circle_at_left,rgb(var(--orion-pri)/0.10),transparent_60%)]"
                  />
                )}
              </button>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
