/**
 * notificationSource — metadatos visuales por fuente de notificación.
 *
 * El backend hoy sólo manda `source: "gmail" | "classroom"`. A medida que
 * sumemos adapters (drive, calendar, sheets, notebooklm, mcp, extensiones)
 * basta con agregar el slug aquí — el panel los pinta solo.
 *
 * `group` permite tabs como Google / Sistema / Otros sin tener que
 * enumerar cada source en el componente.
 */

export type SourceGroup = "google" | "system" | "extension" | "other";

export interface SourceMeta {
  /** Path absoluto al SVG en /public/icons. */
  logo: string;
  /** Nombre legible para mostrar en el card. */
  label: string;
  /** Tinte para halo/avatar. Tailwind acepta rgb(... / alpha). */
  color: string;
  /** Para los filtros del panel. */
  group: SourceGroup;
}

const TABLE: Record<string, SourceMeta> = {
  gmail: { logo: "/icons/gmail.svg", label: "Gmail", color: "#EA4335", group: "google" },
  classroom: {
    logo: "/icons/classroom.svg",
    label: "Classroom",
    color: "#0F9D58",
    group: "google",
  },
  drive: { logo: "/icons/drive.svg", label: "Drive", color: "#FBBC04", group: "google" },
  calendar: { logo: "/icons/calendar.svg", label: "Calendar", color: "#1A73E8", group: "google" },
  sheets: { logo: "/icons/sheets.svg", label: "Sheets", color: "#0F9D58", group: "google" },
  notebooklm: {
    logo: "/icons/notebooklm.svg",
    label: "NotebookLM",
    color: "#9B72F2",
    group: "google",
  },
  google: { logo: "/icons/google.svg", label: "Google", color: "#4285F4", group: "google" },

  mcp: { logo: "/icons/mcp.svg", label: "MCP", color: "#7EE7FF", group: "system" },
  tool: { logo: "/icons/orion.svg", label: "Herramienta", color: "#F472B6", group: "system" },
  agent: { logo: "/icons/orion.svg", label: "Agente", color: "#A78BFA", group: "system" },
  system: { logo: "/icons/orion.svg", label: "Sistema", color: "#94A3B8", group: "system" },

  extension: {
    logo: "/icons/extension.svg",
    label: "Extensión",
    color: "#60A5FA",
    group: "extension",
  },
};

const FALLBACK: SourceMeta = {
  logo: "/icons/orion.svg",
  label: "Otro",
  color: "#64748B",
  group: "other",
};

export function sourceMeta(source: string | undefined | null): SourceMeta {
  if (!source) return FALLBACK;
  const key = source.toLowerCase();
  return TABLE[key] ?? { ...FALLBACK, label: capitalize(source) };
}

function capitalize(s: string): string {
  return s.length === 0 ? s : s[0].toUpperCase() + s.slice(1);
}

/** Limpia el emoji guía que el backend mete al inicio de algunos títulos
 *  ("✉️ Asunto", "📚 Tarea") — el avatar ya comunica la fuente. */
export function stripLeadingEmoji(s: string): string {
  return s.replace(/^[\p{Extended_Pictographic}️‍\s]+/u, "");
}

/** "hace 5 min" / "hace 2 h" / "ayer 22:14" / "mié 18 jun" / etc.
 *  Wrapper de `humanizeUnix` para no romper consumidores que importan
 *  `formatRelative` desde acá. La implementación canónica vive en
 *  `lib/humanTime.ts` (BRIEF G6 — un único helper para toda la UI). */
export { humanizeUnix as formatRelative } from "@/lib/humanTime";
