/**
 * CommandPalette — modal estilo Cmd+K que aparece sobre toda la app.
 *
 * Permite:
 *   - Navegar a cualquier vista (Chat, Notas, Memoria, IoT, ...)
 *   - Ejecutar acciones rápidas (Mute, Interrumpir, Limpiar chat)
 *   - Cambiar de tema sin abrir Settings
 *
 * Atajos:
 *   - Cmd/Ctrl + K   → abrir
 *   - Esc            → cerrar
 *   - ↑↓             → navegar
 *   - Enter          → ejecutar
 *   - Tab            → cierra y enfoca el chat (poweruser)
 *
 * Implementación sin dependencias externas. Búsqueda fuzzy mínima:
 * coincidencia case-insensitive de cada token en label/keywords.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { create } from "zustand";

import { api } from "@/api/rest";
import { useOrionStore } from "@/stores/orion";
import { useViewStore, type View } from "@/stores/view";
import { Icon, type IconName } from "@/ui/Icon";
import { toggleLightDark, isLightTheme } from "@/App";
import { zoomIn, zoomOut, zoomReset } from "@/hooks/useZoomShortcuts";

// Store global para que cualquier componente (TopBar, atajos, futuros
// botones) pueda abrir el palette sin tener que pasarse refs/props.
interface PaletteStore {
  open: boolean;
  setOpen: (v: boolean) => void;
  toggle: () => void;
}
export const useCommandPalette = create<PaletteStore>((set, get) => ({
  open: false,
  setOpen: (v) => set({ open: v }),
  toggle: () => set({ open: !get().open }),
}));

type Action = {
  id: string;
  label: string;
  hint?: string;
  icon: IconName | string; // string para emoji
  keywords: string[];
  group: "Navegar" | "Acción" | "Tema";
  run: () => void | Promise<void>;
};

interface Props {
  send: (type: string, payload?: Record<string, unknown>) => void;
}

const VIEW_ACTIONS: {
  view: View;
  label: string;
  icon: IconName;
  hint?: string;
  keywords: string[];
}[] = [
  { view: "chat", label: "Ir al chat", icon: "chat", keywords: ["chat", "conversación", "hablar"] },
  { view: "notes", label: "Ir a notas rápidas", icon: "notes", keywords: ["notas", "apuntes"] },
  {
    view: "memory",
    label: "Ir a la memoria",
    icon: "memory",
    keywords: ["memoria", "recordar", "saber"],
  },
  {
    view: "history",
    label: "Ir al historial",
    icon: "history",
    keywords: ["historial", "conversaciones pasadas"],
  },
  {
    view: "telemetry",
    label: "Ir a telemetría del sistema",
    icon: "telemetry",
    keywords: ["telemetría", "cpu", "ram", "monitoreo"],
  },
  {
    view: "agents",
    label: "Ir a la orquesta de agentes",
    icon: "agents",
    keywords: ["agentes", "orquesta", "tareas"],
  },
  {
    view: "iot",
    label: "Ir a IoT",
    icon: "iot",
    keywords: ["iot", "casa", "sensores", "dispositivos"],
  },
  {
    view: "mcp",
    label: "Ir a MCP servers",
    icon: "plug",
    keywords: ["mcp", "servidores", "integraciones"],
  },
  { view: "skills", label: "Ir a skills", icon: "sparkles", keywords: ["skills", "habilidades"] },
  {
    view: "notifications",
    label: "Ir a notificaciones",
    icon: "bell",
    keywords: ["notificaciones", "gmail", "classroom"],
  },
  {
    view: "settings",
    label: "Ir a ajustes",
    icon: "settings",
    keywords: ["ajustes", "configuración", "settings"],
  },
];

const THEMES: { id: string; label: string }[] = [
  { id: "orion-night", label: "Noche (default)" },
  { id: "orion-light", label: "Claro (día)" },
  { id: "orion-violet", label: "Violeta" },
  { id: "orion-emerald", label: "Esmeralda" },
  { id: "orion-amber", label: "Ámbar" },
  { id: "orion-red", label: "Rojo" },
  { id: "orion-cyan", label: "Cyan HUD" },
  { id: "orion-green", label: "Matrix Green" },
  { id: "orion-purple", label: "Deep Purple" },
];

export function CommandPalette({ send }: Props) {
  const open = useCommandPalette((s) => s.open);
  const setOpen = useCommandPalette((s) => s.setOpen);
  const togglePalette = useCommandPalette((s) => s.toggle);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const setView = useViewStore((s) => s.setView);
  const muted = useOrionStore((s) => s.muted);
  const clearMessages = useOrionStore((s) => s.clear);

  // Atajos globales:
  //   - Cmd/Ctrl + K  → toggle (atajo estándar)
  //   - Ctrl + /      → toggle (fallback por si Ctrl+K está secuestrado por el browser/OS)
  //   - Escape        → cerrar cuando está abierto
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const meta = e.metaKey || e.ctrlKey;
      if (meta && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        e.stopPropagation();
        togglePalette();
        return;
      }
      if (meta && e.key === "/") {
        e.preventDefault();
        e.stopPropagation();
        togglePalette();
        return;
      }
      if (e.key === "Escape" && open) {
        e.preventDefault();
        setOpen(false);
      }
    };
    // capture phase para ganarle al input del chat (si tiene focus)
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [open, setOpen, togglePalette]);

  // Enfoca el input cuando abre y resetea estado.
  useEffect(() => {
    if (open) {
      setQuery("");
      setCursor(0);
      // Defer para que el input ya esté montado.
      const id = window.setTimeout(() => inputRef.current?.focus(), 10);
      return () => window.clearTimeout(id);
    }
  }, [open]);

  const actions = useMemo<Action[]>(() => {
    const out: Action[] = [];

    for (const v of VIEW_ACTIONS) {
      out.push({
        id: `view:${v.view}`,
        label: v.label,
        hint: v.hint,
        icon: v.icon,
        keywords: v.keywords,
        group: "Navegar",
        run: () => setView(v.view),
      });
    }

    out.push({
      id: "act:mute",
      label: muted ? "Activar micrófono" : "Silenciar micrófono",
      hint: muted ? "Volver a escuchar" : "Pausar la entrada de audio",
      icon: muted ? "mic" : "mic-off",
      keywords: ["mute", "silenciar", "micrófono", "callar"],
      group: "Acción",
      run: () => send("mute", { value: !muted }),
    });

    out.push({
      id: "act:interrupt",
      label: "Interrumpir a Orion",
      hint: "Detener la voz actual",
      icon: "stop",
      keywords: ["interrumpir", "parar", "stop", "callar"],
      group: "Acción",
      run: () => send("interrupt"),
    });

    out.push({
      id: "act:clear",
      label: "Limpiar conversación",
      hint: "Borra los mensajes en pantalla (no la memoria)",
      icon: "trash",
      keywords: ["limpiar", "borrar", "clear", "reset"],
      group: "Acción",
      run: () => clearMessages(),
    });

    out.push({
      id: "act:lightdark",
      label: isLightTheme() ? "Cambiar a modo oscuro" : "Cambiar a modo claro",
      hint: "Alterna entre tema claro y oscuro",
      icon: isLightTheme() ? "moon" : "sun",
      keywords: ["tema", "claro", "oscuro", "light", "dark", "modo"],
      group: "Acción",
      run: () => {
        toggleLightDark();
      },
    });

    out.push({
      id: "act:zoom-in",
      label: "Acercar (Zoom +)",
      hint: "Ctrl + (también funciona con Ctrl + rueda del mouse)",
      icon: "search",
      keywords: ["zoom", "acercar", "agrandar", "in", "ctrl+"],
      group: "Acción",
      run: () => zoomIn(),
    });
    out.push({
      id: "act:zoom-out",
      label: "Alejar (Zoom -)",
      hint: "Ctrl -",
      icon: "search",
      keywords: ["zoom", "alejar", "reducir", "out", "ctrl-"],
      group: "Acción",
      run: () => zoomOut(),
    });
    out.push({
      id: "act:zoom-reset",
      label: "Restablecer zoom (100%)",
      hint: "Ctrl 0",
      icon: "search",
      keywords: ["zoom", "reset", "100", "ctrl0"],
      group: "Acción",
      run: () => zoomReset(),
    });

    for (const t of THEMES) {
      out.push({
        id: `theme:${t.id}`,
        label: `Tema: ${t.label}`,
        icon: "sparkles",
        keywords: ["tema", "theme", "color", t.label.toLowerCase()],
        group: "Tema",
        run: async () => {
          try {
            await api.setTheme(t.id);
          } catch {
            /* server propaga el evento; si falla el patch, no nukeamos UI */
          }
        },
      });
    }

    return out;
  }, [muted, setView, send, clearMessages]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return actions;
    const tokens = q.split(/\s+/);
    return actions.filter((a) => {
      const hay = [a.label, a.hint || "", ...a.keywords].join(" ").toLowerCase();
      return tokens.every((tok) => hay.includes(tok));
    });
  }, [actions, query]);

  // Mantén el cursor en rango cuando cambia la lista.
  useEffect(() => {
    if (cursor >= filtered.length) setCursor(Math.max(0, filtered.length - 1));
  }, [filtered.length, cursor]);

  function execute(a: Action) {
    setOpen(false);
    Promise.resolve(a.run()).catch(() => {
      /* swallow — el detalle ya se loguea en cada handler */
    });
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => Math.min(filtered.length - 1, c + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => Math.max(0, c - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const a = filtered[cursor];
      if (a) execute(a);
    }
  }

  if (!open) return null;

  // Agrupa para mostrar separadores.
  const groups = ["Navegar", "Acción", "Tema"] as const;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/55 backdrop-blur-sm animate-fade-in"
      onClick={() => setOpen(false)}
    >
      <div className="mx-auto mt-[12vh] max-w-xl px-4">
        <div
          onClick={(e) => e.stopPropagation()}
          className="rounded-2xl border border-white/[0.08] bg-elevated/95 shadow-2xl
                     overflow-hidden animate-scale-in backdrop-blur-xl"
        >
          {/* search */}
          <div className="flex items-center gap-2.5 px-4 py-3 border-b border-white/[0.06]">
            <Icon name="command" size={16} className="text-pri" />
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setCursor(0);
              }}
              onKeyDown={onKeyDown}
              placeholder="Buscar acciones, vistas, temas…"
              className="flex-1 bg-transparent text-[15px] placeholder-muted focus:outline-none text-text"
            />
            <span className="text-[10px] uppercase tracking-[0.22em] text-muted">ESC</span>
          </div>

          {/* results */}
          <div className="max-h-[55vh] overflow-y-auto scrollbar-thin">
            {filtered.length === 0 && (
              <div className="px-4 py-10 text-center text-sm text-text-dim">
                Sin coincidencias para <code className="text-text">"{query}"</code>
              </div>
            )}
            {groups.map((g) => {
              const items = filtered.filter((a) => a.group === g);
              if (items.length === 0) return null;
              return (
                <div key={g} className="py-1">
                  <div className="px-4 py-1.5 text-[9px] uppercase tracking-[0.28em] text-muted">
                    {g}
                  </div>
                  {items.map((a) => {
                    const idx = filtered.indexOf(a);
                    const selected = idx === cursor;
                    const isEmoji = typeof a.icon === "string" && !/^[a-z]/.test(a.icon);
                    return (
                      <button
                        key={a.id}
                        onMouseEnter={() => setCursor(idx)}
                        onClick={() => execute(a)}
                        className={[
                          "w-full px-4 py-2 flex items-center gap-3 text-left transition-colors",
                          selected ? "bg-pri/10 text-text" : "text-text-dim hover:bg-white/[0.03]",
                        ].join(" ")}
                      >
                        <span
                          className={`grid place-items-center h-7 w-7 rounded-md ${selected ? "bg-pri/20" : "bg-white/[0.04]"}`}
                        >
                          {isEmoji ? (
                            <span className="text-sm leading-none">{a.icon}</span>
                          ) : (
                            <Icon
                              name={a.icon as IconName}
                              size={14}
                              className={selected ? "text-pri" : ""}
                            />
                          )}
                        </span>
                        <span className="flex-1 min-w-0">
                          <span className="block text-sm truncate">{a.label}</span>
                          {a.hint && (
                            <span className="block text-[11px] text-muted truncate">{a.hint}</span>
                          )}
                        </span>
                        {selected && (
                          <span className="text-[10px] uppercase tracking-[0.22em] text-pri">
                            ↵
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              );
            })}
          </div>

          {/* footer */}
          <div className="flex items-center justify-between px-4 py-2 border-t border-white/[0.06] bg-white/[0.02] text-[10px] uppercase tracking-[0.22em] text-muted">
            <span>↑↓ navegar · ↵ ejecutar</span>
            <span className="flex items-center gap-1">
              <kbd className="px-1.5 py-0.5 rounded bg-white/[0.06] border border-white/[0.08]">
                ⌘
              </kbd>
              <kbd className="px-1.5 py-0.5 rounded bg-white/[0.06] border border-white/[0.08]">
                K
              </kbd>
              <span className="ml-1">para abrir</span>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
