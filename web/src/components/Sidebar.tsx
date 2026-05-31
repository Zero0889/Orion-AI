/**
 * Sidebar — navegación entre las vistas (Chat / Notas / Memoria /
 * Historial / Ajustes). Minimal y vertical; cada item es un botón.
 */

import { useViewStore, type View } from "@/stores/view";

interface Item {
  id:    View;
  label: string;
  icon:  string;  // glifo unicode para no añadir dep
}

const ITEMS: Item[] = [
  { id: "chat",      label: "Chat",       icon: "◉" },
  { id: "notes",     label: "Notas",      icon: "✎" },
  { id: "memory",    label: "Memoria",    icon: "▤" },
  { id: "history",   label: "Historial",  icon: "⟲" },
  { id: "telemetry", label: "Telemetría", icon: "▲" },
  { id: "agents",    label: "Agentes",    icon: "◈" },
  { id: "iot",       label: "IoT",        icon: "⌂" },
  { id: "settings",  label: "Ajustes",    icon: "⚙" },
];

export function Sidebar() {
  const view    = useViewStore((s) => s.view);
  const setView = useViewStore((s) => s.setView);

  return (
    <nav className="flex flex-col gap-1 w-full">
      {ITEMS.map((it) => {
        const active = view === it.id;
        return (
          <button
            key={it.id}
            onClick={() => setView(it.id)}
            className={`group flex items-center gap-3 rounded-md px-3 py-2 text-sm
              border transition
              ${active
                ? "bg-pri-dim/30 border-pri text-text"
                : "bg-transparent border-transparent text-text-dim hover:text-text hover:border-border-b"}`}
          >
            <span className={`text-base ${active ? "text-pri" : "text-text-dim group-hover:text-pri"}`}>
              {it.icon}
            </span>
            <span className="tracking-wide">{it.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
