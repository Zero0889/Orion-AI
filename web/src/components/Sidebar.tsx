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
  id: View;
  label: string;
  icon: IconName;
}
interface Section {
  label: string;
  items: Item[];
}

const SECTIONS: Section[] = [
  {
    label: "Espacio",
    items: [
      { id: "home", label: "Inicio", icon: "orbit" },
      { id: "chat", label: "Conversación", icon: "chat" },
    ],
  },
  {
    label: "Conocimiento",
    items: [
      { id: "notes", label: "Notas", icon: "notes" },
      { id: "memory", label: "Memoria", icon: "memory" },
      { id: "history", label: "Historial", icon: "history" },
    ],
  },
  {
    label: "Herramientas",
    items: [{ id: "circuit", label: "Circuitos", icon: "cpu" }],
  },
  {
    label: "Sistema",
    items: [
      { id: "telemetry", label: "Telemetría", icon: "telemetry" },
      { id: "agents", label: "Agentes", icon: "agents" },
      { id: "iot", label: "IoT", icon: "iot" },
      { id: "mcp", label: "MCP", icon: "plug" },
      { id: "skills", label: "Skills", icon: "sparkles" },
      { id: "notifications", label: "Notificaciones", icon: "bell" },
      { id: "settings", label: "Ajustes", icon: "settings" },
    ],
  },
];

interface Props {
  collapsed?: boolean;
}

export function Sidebar({ collapsed = false }: Props) {
  const view = useViewStore((s) => s.view);
  const setView = useViewStore((s) => s.setView);

  return (
    <nav className="flex flex-col gap-5 w-full">
      {SECTIONS.map((sec) => (
        <div key={sec.label} className="flex flex-col gap-0.5">
          {!collapsed && (
            <div className="px-3 mb-1.5 flex items-center gap-2">
              <span className="h-1 w-1 rounded-full bg-pri/70 shadow-[0_0_4px_rgb(var(--orion-pri-glow))]" />
              <div className="text-[9px] uppercase tracking-[0.28em] text-pri/85 font-semibold">
                {sec.label}
              </div>
              <span className="h-1 w-1 rounded-full bg-pri/40" />
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
                  "group relative flex items-center rounded-md overflow-hidden",
                  collapsed ? "justify-center h-10 w-10 mx-auto" : "gap-3 px-3 h-9",
                  "text-sm transition-all duration-150 ease-out-expo",
                  "border",
                  active
                    ? "text-text border-pri/40"
                    : "text-text-dim border-transparent hover:text-text hover:bg-pri/[0.035]",
                ].join(" ")}
              >
                {/* Estado activo refinado:
                    · gradiente horizontal sutil (sin grid pattern)
                    · barra accent izquierda con glow
                    · highlight superior interior (sello visionOS)
                    · corner brackets discretos arriba */}
                {active && (
                  <>
                    <span
                      aria-hidden
                      className="absolute inset-0 pointer-events-none rounded-md"
                      style={{
                        background:
                          "linear-gradient(90deg, rgb(var(--orion-pri)/0.16) 0%, rgb(var(--orion-pri)/0.06) 60%, transparent 100%)",
                        boxShadow:
                          "inset 0 1px 0 rgb(255 255 255 / 0.04), inset 0 0 0 1px rgb(var(--orion-pri) / 0.12)",
                      }}
                    />
                    <span
                      aria-hidden
                      className="absolute left-0 top-0 h-full w-[2px] bg-pri rounded-r-full
                                 shadow-[0_0_10px_rgb(var(--orion-pri-glow)/0.85),0_0_22px_rgb(var(--orion-pri-glow)/0.35)]"
                    />
                    <span
                      aria-hidden
                      className="absolute top-0 left-0 h-1.5 w-1.5 border-t border-l border-pri/60"
                    />
                    <span
                      aria-hidden
                      className="absolute top-0 right-0 h-1.5 w-1.5 border-t border-r border-pri/60"
                    />
                  </>
                )}
                {/* Indicador hover sutil — barra izquierda que asoma. */}
                {!active && (
                  <span
                    aria-hidden
                    className="absolute left-0 top-1/2 -translate-y-1/2 h-0 w-[2px] bg-pri/0
                               group-hover:h-4 group-hover:bg-pri/40 rounded-r-full
                               transition-all duration-200"
                  />
                )}

                <Icon
                  name={it.icon}
                  size={collapsed ? 18 : 16}
                  className={[
                    "relative shrink-0 transition-all duration-150",
                    active
                      ? "text-pri drop-shadow-[0_0_6px_rgb(var(--orion-pri-glow)/0.85)]"
                      : "text-pri/55 group-hover:text-pri/90",
                  ].join(" ")}
                />
                {!collapsed && (
                  <span
                    className={[
                      "relative truncate font-medium tracking-tight",
                      active ? "" : "group-hover:text-text",
                    ].join(" ")}
                  >
                    {it.label}
                  </span>
                )}
                {/* Dot a la derecha del item activo. */}
                {!collapsed && active && (
                  <span
                    aria-hidden
                    className="relative ml-auto h-1.5 w-1.5 rounded-full bg-pri shadow-[0_0_8px_rgb(var(--orion-pri-glow))]"
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
