/**
 * App — Orion shell.
 *
 * Layout:
 *   [Sidebar 264|72] [Main column = TopBar + active view]
 *
 * Overlays: Onboarding modal + global DropZone.
 *
 * Theme application: when the backend ships a settings.theme event the
 * store bumps rev.theme; we re-fetch the active theme name and apply it
 * by setting `data-theme` on <html>. CSS variables defined in styles.css
 * handle the rest, so we don't need to mutate tailwind at runtime.
 */

import { useEffect, useState } from "react";

import { AgentsPanel } from "@/components/AgentsPanel";
import { ChatPanel } from "@/components/ChatPanel";
import { CommandPalette } from "@/components/CommandPalette";
import { DropZone } from "@/components/DropZone";
import { HistoryPanel } from "@/components/HistoryPanel";
import { HomePanel } from "@/components/HomePanel";
import { IoTPanel } from "@/components/IoTPanel";
import { MCPPanel } from "@/components/MCPPanel";
import { MemoryPanel } from "@/components/MemoryPanel";
import { NotesPanel } from "@/components/NotesPanel";
import { NotificationsPanel } from "@/components/NotificationsPanel";
import { Onboarding } from "@/components/Onboarding";
import { SettingsPanel } from "@/components/SettingsPanel";
import { Sidebar } from "@/components/Sidebar";
import { SkillsPanel } from "@/components/SkillsPanel";
import { TelemetryPanel } from "@/components/TelemetryPanel";
import { TopBar } from "@/components/TopBar";
import { useOrionSocket } from "@/hooks/useOrionSocket";
import { useOrionStore } from "@/stores/orion";
import { useViewStore } from "@/stores/view";
import { Icon } from "@/ui/Icon";
import { api } from "@/api/rest";
import { inferBackendUrl } from "@/api/ws";

const RAIL_KEY = "orion.sidebar.collapsed";
const THEME_KEY = "orion.theme";

/**
 * Maps a backend theme id to its frontend CSS data-theme variant.
 * The backend ships 15+ themes; we collapse them into our 8 CSS palettes.
 */
export function resolveTheme(id: string): string {
  const n = id.toLowerCase();
  if (n.includes("light") || n.includes("glass_white") || n === "blanco")  return "orion-light";
  if (n.includes("violet"))                                                  return "orion-violet";
  if (n.includes("emerald") || n.includes("matrix"))                        return "orion-emerald";
  if (n.includes("amber")  || n.includes("crt"))                            return "orion-amber";
  if (n.includes("red")    || n.includes("alert") || n === "black_red")     return "orion-red";
  if (n.includes("cyan")   || n.includes("arctic") || n.includes("orion_blue") || n.includes("cyber")) return "orion-cyan";
  if (n.includes("green"))                                                   return "orion-green";
  if (n.includes("purple") || n.includes("deep_purple") || n.includes("cyberpunk")) return "orion-purple";
  return "orion-night";
}

/**
 * Toggles between light and dark mode, persisting to localStorage.
 * Call this from any component — it updates the DOM immediately.
 */
export function toggleLightDark(): "orion-light" | "orion-night" {
  const current = document.documentElement.getAttribute("data-theme");
  const next = current === "orion-light" ? "orion-night" : "orion-light";
  document.documentElement.setAttribute("data-theme", next);
  window.localStorage.setItem(THEME_KEY, next);
  return next;
}

/**
 * Returns whether the light theme is active.
 */
export function isLightTheme(): boolean {
  return document.documentElement.getAttribute("data-theme") === "orion-light";
}

export default function App() {
  const send       = useOrionSocket();
  const view       = useViewStore((s) => s.view);
  const muted      = useOrionStore((s) => s.muted);
  const revTheme   = useOrionStore((s) => s.rev.theme);
  const [version, setVersion] = useState<string>("");
  const [collapsed, setCollapsed] = useState<boolean>(
    () => typeof window !== "undefined" && window.localStorage.getItem(RAIL_KEY) === "1",
  );

  useEffect(() => {
    const { http } = inferBackendUrl();
    fetch(`${http}/api/health`)
      .then((r) => r.json())
      .then((d) => setVersion(d.version))
      .catch(() => setVersion("?"));
  }, []);

  // React to backend theme switches by setting data-theme on <html>.
  useEffect(() => {
    api.getTheme()
      .then((info) => {
        const name = (info?.name ?? "").toLowerCase();
        const slug = resolveTheme(name);
        document.documentElement.setAttribute("data-theme", slug);
        window.localStorage.setItem(THEME_KEY, slug);
      })
      .catch(() => { /* leave default */ });
  }, [revTheme]);

  // restore saved light/dark preference on mount
  useEffect(() => {
    const saved = window.localStorage.getItem(THEME_KEY);
    if (saved) {
      document.documentElement.setAttribute("data-theme", saved);
    }
  }, []);

  // persist rail state
  useEffect(() => {
    window.localStorage.setItem(RAIL_KEY, collapsed ? "1" : "0");
  }, [collapsed]);

  const railW = collapsed ? "72px" : "264px";

  return (
    <div
      className="h-screen w-screen grid overflow-hidden bg-bg text-text noise"
      style={{ gridTemplateColumns: `${railW} 1fr` }}
    >
      {/* ── Sidebar ───────────────────────────────────────────────── */}
      <aside className="relative flex flex-col p-3 border-r border-white/[0.06] bg-sunken/50 backdrop-blur-sm">
        {/* brand */}
        <div className={collapsed ? "flex justify-center py-2 mb-3" : "flex items-center gap-2.5 px-2 py-2 mb-4"}>
          <BrandMark />
          {!collapsed && (
            <div className="leading-tight">
              <div className="text-[13px] font-semibold tracking-[0.18em] text-text">ORION</div>
              <div className="text-[9px] uppercase tracking-[0.22em] text-muted">OS · v{version || "…"}</div>
            </div>
          )}
        </div>

        <Sidebar collapsed={collapsed} />

        <div className="flex-1" />

        {/* status footer */}
        <div className="flex flex-col gap-2">
          {!collapsed && <ThemeToggle />}
          <FooterStatus collapsed={collapsed} muted={muted} />
        </div>
      </aside>

      {/* ── Main column ───────────────────────────────────────────── */}
      <div className="flex flex-col overflow-hidden">
        <TopBar
          version={version}
          collapsed={collapsed}
          onToggleRail={() => setCollapsed((v) => !v)}
          onToggleMute={() => send("mute", { value: !muted })}
          onInterrupt={() => send("interrupt")}
        />

        <main key={view} className="flex-1 overflow-hidden bg-bg animate-fade-in">
          {view === "home"      && <HomePanel />}
          {view === "chat"      && <ChatPanel onSend={(t) => send("text", { text: t })} />}
          {view === "notes"     && <NotesPanel />}
          {view === "memory"    && <MemoryPanel />}
          {view === "history"   && <HistoryPanel />}
          {view === "telemetry" && <TelemetryPanel />}
          {view === "agents"    && <AgentsPanel />}
          {view === "iot"       && <IoTPanel />}
          {view === "mcp"       && <MCPPanel />}
          {view === "skills"    && <SkillsPanel />}
          {view === "notifications" && <NotificationsPanel />}
          {view === "settings"  && <SettingsPanel />}
        </main>
      </div>

      {/* overlays */}
      <Onboarding />
      <DropZone />
      <CommandPalette send={send} />
    </div>
  );
}

/* ─── brand mark — minimal orbit glyph ─────────────────────────────── */
function BrandMark() {
  return (
    <div className="relative h-9 w-9 grid place-items-center">
      <div className="absolute inset-0 rounded-full bg-pri/15 blur-md" />
      <svg viewBox="0 0 40 40" className="relative h-9 w-9 animate-breath">
        <defs>
          <radialGradient id="brandCore" cx="50%" cy="40%" r="55%">
            <stop offset="0%"   stopColor="#FFFFFF" stopOpacity="0.95" />
            <stop offset="45%"  stopColor="rgb(var(--orion-pri))" stopOpacity="0.95" />
            <stop offset="100%" stopColor="#000" stopOpacity="0.85" />
          </radialGradient>
        </defs>
        <circle cx="20" cy="20" r="11" fill="url(#brandCore)" />
        <ellipse cx="20" cy="20" rx="17" ry="6" fill="none"
                 stroke="rgb(var(--orion-pri))" strokeOpacity="0.55" strokeWidth="0.9"
                 transform="rotate(-22 20 20)" />
        <circle cx="36" cy="14" r="1.3" fill="rgb(var(--orion-acc))" />
      </svg>
    </div>
  );
}

/* ─── theme toggle — quick light/dark switch in sidebar ───────────── */
function ThemeToggle() {
  const [light, setLight] = useState(() => isLightTheme());

  function flip() {
    const next = toggleLightDark();
    setLight(next === "orion-light");
  }

  return (
    <button
      onClick={flip}
      title={light ? "Cambiar a modo oscuro" : "Cambiar a modo claro"}
      className="flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg
                 border border-white/[0.05] bg-elevated/40
                 hover:bg-elevated/70 hover:border-pri/30
                 transition-all duration-200 ease-out-expo group"
    >
      <span className="grid place-items-center h-6 w-6 rounded-md bg-pri/15 text-pri
                       group-hover:bg-pri/25 transition-colors">
        <Icon name={light ? "sun" : "moon"} size={13} />
      </span>
      <div className="leading-tight min-w-0">
        <div className="text-[10px] uppercase tracking-[0.18em] text-text-dim">Tema</div>
        <div className="text-[10px] text-text truncate font-medium">
          {light ? "Claro" : "Oscuro"}
        </div>
      </div>
      <Icon name="sun" size={12} className="ml-auto text-text-dim opacity-50 group-hover:opacity-100" />
    </button>
  );
}

/* ─── footer status — system signal + a tiny shortcut hint ─────────── */
function FooterStatus({ collapsed, muted }: { collapsed: boolean; muted: boolean }) {
  const connected = useOrionStore((s) => s.connected);
  return collapsed ? (
    <div className="grid place-items-center pb-1">
      <span
        className={`h-2 w-2 rounded-full ${connected ? "bg-ok shadow-[0_0_10px_rgb(var(--orion-ok))]" : "bg-muted"}`}
        title={connected ? "Conectado" : "Sin conexión"}
      />
    </div>
  ) : (
    <div className="flex items-center justify-between px-2 py-2 rounded-lg border border-white/[0.05] bg-elevated/40">
      <div className="flex items-center gap-2 min-w-0">
        <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${connected ? "bg-ok shadow-[0_0_10px_rgb(var(--orion-ok))]" : "bg-muted"}`} />
        <div className="leading-tight min-w-0">
          <div className="text-[10px] uppercase tracking-[0.2em] text-text-dim">Sistema</div>
          <div className="text-[10px] text-text truncate">
            {connected ? (muted ? "En silencio" : "Operativo") : "Reconectando…"}
          </div>
        </div>
      </div>
      <Icon name="bolt" size={14} className="text-pri/70 shrink-0" />
    </div>
  );
}
