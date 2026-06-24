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

import { lazy, Suspense, useEffect, useState } from "react";

import { DropZone } from "@/components/DropZone";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { HomePanel } from "@/components/HomePanel";
import { NeuralBackground } from "@/components/NeuralBackground";
import { Onboarding } from "@/components/Onboarding";
import { Sidebar } from "@/components/Sidebar";
import { Toaster } from "@/components/Toaster";
import { TopBar } from "@/components/TopBar";
import { WallpaperLayer } from "@/components/WallpaperLayer";

// ── Paneles bajo demanda ──────────────────────────────────────────────
// Home es eager (es la vista por defecto al abrir Orion). Todo lo demás
// se carga sólo cuando el usuario navega ahí. Vite genera un chunk
// independiente por cada lazy() — la página inicial baja ~150 kB menos.
// La mayoría de los paneles pesan 15-50 kB cada uno; juntos sumaban una
// carga inicial que el 80 % de las sesiones nunca necesita.
const ChatPanel = lazy(() =>
  import("@/components/ChatPanel").then((m) => ({ default: m.ChatPanel })),
);
const NotesPanel = lazy(() =>
  import("@/components/NotesPanel").then((m) => ({ default: m.NotesPanel })),
);
const MemoryPanel = lazy(() =>
  import("@/components/MemoryPanel").then((m) => ({ default: m.MemoryPanel })),
);
const HistoryPanel = lazy(() =>
  import("@/components/HistoryPanel").then((m) => ({ default: m.HistoryPanel })),
);
const TelemetryPanel = lazy(() =>
  import("@/components/TelemetryPanel").then((m) => ({ default: m.TelemetryPanel })),
);
const AgentsPanel = lazy(() =>
  import("@/components/AgentsPanel").then((m) => ({ default: m.AgentsPanel })),
);
const IoTPanel = lazy(() => import("@/components/IoTPanel").then((m) => ({ default: m.IoTPanel })));
const MCPPanel = lazy(() => import("@/components/MCPPanel").then((m) => ({ default: m.MCPPanel })));
const SkillsPanel = lazy(() =>
  import("@/components/SkillsPanel").then((m) => ({ default: m.SkillsPanel })),
);
const NotificationsPanel = lazy(() =>
  import("@/components/NotificationsPanel").then((m) => ({ default: m.NotificationsPanel })),
);
const CircuitPanel = lazy(() =>
  import("@/components/CircuitPanel").then((m) => ({ default: m.CircuitPanel })),
);
const DiagnosticsPanel = lazy(() =>
  import("@/components/DiagnosticsPanel").then((m) => ({ default: m.DiagnosticsPanel })),
);
const SettingsPanel = lazy(() =>
  import("@/components/SettingsPanel").then((m) => ({ default: m.SettingsPanel })),
);
import { useQuery } from "@tanstack/react-query";

import { useOrionSocket } from "@/hooks/useOrionSocket";
import { useZoomShortcuts } from "@/hooks/useZoomShortcuts";
import { QUERY_KEYS } from "@/query/keys";
import { useOrionStore } from "@/stores/orion";
import { usePersonalization } from "@/stores/personalization";
import { useViewStore } from "@/stores/view";
import { Icon } from "@/ui/Icon";
import { CommandPalette } from "@/widgets/command-palette";
import {
  BackgroundEye,
  EyeCore,
  useEventPulses,
  useEyeState,
  type EyePalette,
} from "@/widgets/eye";
import { api, type ThemeInfo } from "@/api/rest";
import { inferBackendUrl } from "@/api/ws";

const RAIL_KEY = "orion.sidebar.collapsed";
const THEME_KEY = "orion.theme";

/**
 * Maps a backend theme id to its frontend CSS data-theme variant.
 * The backend ships 15+ themes; we collapse them into our 8 CSS palettes.
 */
export function resolveTheme(id: string): string {
  const n = id.toLowerCase();
  if (n.includes("light") || n.includes("glass_white") || n === "blanco") return "orion-light";
  if (n.includes("violet")) return "orion-violet";
  if (n.includes("emerald") || n.includes("matrix")) return "orion-emerald";
  if (n.includes("amber") || n.includes("crt")) return "orion-amber";
  if (n.includes("red") || n.includes("alert") || n === "black_red") return "orion-red";
  if (n.includes("cyan") || n.includes("arctic") || n.includes("orion_blue") || n.includes("cyber"))
    return "orion-cyan";
  if (n.includes("green")) return "orion-green";
  if (n.includes("purple") || n.includes("deep_purple") || n.includes("cyberpunk"))
    return "orion-purple";
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
  const send = useOrionSocket();
  const view = useViewStore((s) => s.view);
  const muted = useOrionStore((s) => s.muted);
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

  // Theme via useQuery — comparte cache con SettingsPanel: ambos leen
  // QUERY_KEYS.settingsTheme, así que se fetchea UNA vez por sesión y
  // se re-fetchea solo cuando el bridge WS invalida (case "settings.theme").
  const { data: themeInfo } = useQuery<ThemeInfo>({
    queryKey: QUERY_KEYS.settingsTheme,
    queryFn: () => api.getTheme(),
  });

  // React to backend theme switches by setting data-theme on <html>.
  useEffect(() => {
    if (!themeInfo) return;
    const name = (themeInfo.name ?? "").toLowerCase();
    const slug = resolveTheme(name);
    document.documentElement.setAttribute("data-theme", slug);
    window.localStorage.setItem(THEME_KEY, slug);
  }, [themeInfo]);

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

  // ── Chrome reactivo: escribe el estado del ojo en <html data-eye-state>
  // para que el CSS pueda teñir los bordes del sidebar/topbar con el color
  // del estado actual. El CSS hace la transición suave (~600ms).
  const eyeState = useEyeState();
  useEffect(() => {
    document.documentElement.dataset.eyeState = eyeState;
  }, [eyeState]);

  // ── Personalización del usuario ─────────────────────────────────────
  // Eye color override: si el usuario picó un swatch en Ajustes,
  // escribimos en <html> inline:
  //   · `--orion-pri` / `--orion-pri-glow` / `--orion-acc` — tinta TODO
  //     el chrome (sidebar, badges, agent borders, focus rings, etc).
  //   · `--ec-base-main` / `--ec-base-second` / `--ec-base-glow` — tinta
  //     el Ojo en estado IDLE. Los estados activos (listening, thinking,
  //     speaking, error) redeclaran sus vars directo en eye-core.css así
  //     que mantienen su DNA de marca (cyan / magenta / verde-cian / rojo)
  //     pase lo que pase con el override.
  // Wallpaper override: si hay un wallpaper subido, ocultamos el
  // NeuralBackground (sino el grid + anillos compiten con la imagen).
  const eyeColorPri = usePersonalization((s) => s.eyeColorPri);
  const eyeColorAcc = usePersonalization((s) => s.eyeColorAcc);
  const hasWallpaper = usePersonalization((s) => s.wallpaper !== null);
  useEffect(() => {
    const root = document.documentElement;
    if (eyeColorPri) {
      root.style.setProperty("--orion-pri", eyeColorPri);
      root.style.setProperty("--orion-pri-glow", eyeColorPri);
      // Color del Ojo base (idle). Convertimos el triplete "R G B" en
      // `rgb(R G B)` para que la cascada CSS lo trate como color real.
      root.style.setProperty("--ec-base-main", `rgb(${eyeColorPri})`);
      root.style.setProperty("--ec-base-glow", `rgb(${eyeColorPri} / 0.6)`);
    } else {
      root.style.removeProperty("--orion-pri");
      root.style.removeProperty("--orion-pri-glow");
      root.style.removeProperty("--ec-base-main");
      root.style.removeProperty("--ec-base-glow");
    }
    if (eyeColorAcc) {
      root.style.setProperty("--orion-acc", eyeColorAcc);
      root.style.setProperty("--ec-base-second", `rgb(${eyeColorAcc})`);
    } else {
      root.style.removeProperty("--orion-acc");
      root.style.removeProperty("--ec-base-second");
    }
  }, [eyeColorPri, eyeColorAcc]);

  // Bisagra mundo→ojo: dispara pulsos radiales por sensores nuevos,
  // notifs, tools, etc. Sin filtros se vuelve ruido — la lógica de
  // qué amerita pulso vive en useEventPulses.
  useEventPulses();

  // Atajos Ctrl + / Ctrl - / Ctrl 0 (+ Ctrl + wheel) para escalar todo
  // el chrome. Persiste el factor en localStorage.
  useZoomShortcuts();

  // Prefetch del panel "Conversación" cuando el browser está idle. Es
  // de lejos la siguiente vista más probable después de Inicio (el
  // input del Home redirige ahí). Con requestIdleCallback no robamos
  // ciclos del primer paint — sólo se dispara cuando la main thread
  // queda libre. Si el navegador no soporta rIC (Safari < 17),
  // fallback a setTimeout 1500ms.
  useEffect(() => {
    const prefetch = () => {
      void import("@/components/ChatPanel");
    };
    const ric = (window as unknown as { requestIdleCallback?: (cb: () => void) => number })
      .requestIdleCallback;
    const handle = ric ? ric(prefetch) : window.setTimeout(prefetch, 1500);
    return () => {
      const cic = (window as unknown as { cancelIdleCallback?: (h: number) => void })
        .cancelIdleCallback;
      if (ric && cic) cic(handle);
      else window.clearTimeout(handle as number);
    };
  }, []);

  const railW = collapsed ? "72px" : "264px";

  return (
    <div className="relative h-full w-full overflow-hidden bg-bg text-text noise">
      {/* ── Fondo del sistema — orden de capas (de atrás hacia adelante):
          · Wallpaper del usuario (si subió uno) en z-0.
          · NeuralBackground en z-0 (cae al fondo cuando no hay wallpaper;
            si hay wallpaper lo ocultamos para que no compita visualmente).
          · Overlay G1 en z-[1] sólo en paneles que no son Home/Conversación,
            cuando NO hay wallpaper (el wallpaper ya trae su propio
            overlay configurable + blur). */}
      <WallpaperLayer />
      {!hasWallpaper && (
        <div className="absolute inset-0 z-0">
          <NeuralBackground intensity={view === "home" || view === "chat" ? "full" : "ambient"} />
        </div>
      )}
      {!hasWallpaper && view !== "home" && view !== "chat" && (
        <div
          aria-hidden
          className="absolute inset-0 z-[1] pointer-events-none
                     bg-bg/85 backdrop-blur-[28px]
                     transition-opacity duration-300 ease-out-expo"
        />
      )}

      <div
        className="relative z-10 h-full w-full grid overflow-hidden"
        style={{ gridTemplateColumns: `${railW} 1fr` }}
      >
        {/* ── Sidebar ───────────────────────────────────────────────── */}
        {/* min-h-0 + flex column con un scroller interno: brand pinned arriba,
          footer (tema + sistema) pinned abajo, y los items navegables hacen
          scroll cuando crecen — esto sobrevive a cualquier nivel de zoom.
          bg translúcido para que el NeuralBackground se vea atrás. */}
        <aside className="relative flex flex-col p-3 border-r border-white/[0.06] bg-sunken/25 backdrop-blur-md chrome-edge-right min-h-0 overflow-hidden">
          {/* brand */}
          <div
            className={
              collapsed
                ? "flex justify-center py-2 mb-3 shrink-0"
                : "flex items-center gap-2.5 px-2 py-2 mb-4 shrink-0"
            }
          >
            <BrandMark />
            {!collapsed && (
              <div className="leading-tight">
                <div className="text-[13px] font-semibold tracking-[0.18em] text-text">ORION</div>
                <div className="text-[9px] uppercase tracking-[0.22em] text-muted numeric">
                  OS · v{version || "…"}
                </div>
              </div>
            )}
          </div>

          {/* scroll area: ocupa todo el espacio entre brand y footer; si los
            items no caben, scrollea acá sin tapar el footer. */}
          <div className="flex-1 min-h-0 overflow-y-auto scrollbar-thin -mx-1 px-1">
            <Sidebar collapsed={collapsed} />
          </div>

          {/* status footer — sticky por estructura (flex column con el scroller
            arriba), con un fade superior que sugiere que hay más por scrollear. */}
          <div className="relative flex flex-col gap-2 pt-3 shrink-0">
            <div
              aria-hidden
              className="pointer-events-none absolute -top-4 left-0 right-0 h-4
                       bg-gradient-to-b from-transparent to-[rgb(var(--orion-sunken)/0.9)]"
            />
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

          <main
            key={view}
            className="relative flex-1 overflow-hidden bg-transparent animate-view-enter"
          >
            {/* Capa 0 — ojo ambiental detrás de las vistas != home,
              reacciona al estado real del backend. El NeuralBackground
              vive a nivel raíz, debajo de todo. */}
            {view !== "home" && <BackgroundEye />}

            {/* Capa 1 — las vistas viven sobre el fondo, en su propio plano.
              Home es eager (sin Suspense); el resto va dentro del
              Suspense con un fallback minimalista para el primer paint
              mientras Vite trae el chunk del panel. Después del primer
              load el panel queda cacheado en memoria por React.lazy.
              ErrorBoundary captura tanto fallos de descarga del chunk
              como crashes de render dentro del panel — el `key={view}`
              resetea el boundary al cambiar de vista. */}
            <div className="relative z-10 h-full">
              {view === "home" && (
                <ErrorBoundary key="home">
                  <HomePanel />
                </ErrorBoundary>
              )}
              {view !== "home" && (
                <ErrorBoundary key={view}>
                  <Suspense fallback={<PanelLoader />}>
                    {view === "chat" && <ChatPanel send={send} />}
                    {view === "notes" && <NotesPanel />}
                    {view === "memory" && <MemoryPanel />}
                    {view === "history" && <HistoryPanel />}
                    {view === "telemetry" && <TelemetryPanel />}
                    {view === "agents" && <AgentsPanel />}
                    {view === "iot" && <IoTPanel />}
                    {view === "mcp" && <MCPPanel />}
                    {view === "skills" && <SkillsPanel />}
                    {view === "notifications" && <NotificationsPanel />}
                    {view === "circuit" && <CircuitPanel />}
                    {view === "diagnostics" && <DiagnosticsPanel />}
                    {view === "settings" && <SettingsPanel />}
                  </Suspense>
                </ErrorBoundary>
              )}
            </div>
          </main>
        </div>
      </div>

      {/* overlays */}
      <Onboarding />
      <DropZone />
      <CommandPalette send={send} />
      <Toaster />

      {/* HUD scanlines — capa CRT global. Va detrás del noise overlay
          (z-9999) pero por encima de toda la UI. pointer-events:none. */}
      <div className="scanlines" aria-hidden />
    </div>
  );
}

/* ─── brand mark — el MISMO ojo del Inicio, sólo que en miniatura ─────
   En reposo se queda QUIETO. Sólo arranca todas las animaciones del
   diseño (anillos girando, mirada robótica, iris dilatándose) cuando
   el mouse está encima. La paleta queda FIJA en blanco-azul: nunca
   cambia de color con el estado de Orion. */
const SIDEBAR_EYE_PALETTE: EyePalette = {
  main: "rgba(200, 225, 255, 0.95)",
  second: "rgba(120, 165, 230, 0.85)",
  glow: "rgba(200, 225, 255, 0.45)",
};

function BrandMark() {
  const [hover, setHover] = useState(false);
  return (
    <div
      className="relative h-9 w-9 grid place-items-center cursor-default"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <div className="absolute inset-0 rounded-full bg-pri/10 blur-md pointer-events-none" />
      <EyeCore
        size={38}
        state="idle"
        palette={SIDEBAR_EYE_PALETTE}
        paused={!hover}
        className="relative"
      />
    </div>
  );
}

/* ─── theme toggle — card estilo Gemini con icono coloreado ───────── */
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
      className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg
                 border border-pri/20 bg-pri/[0.04]
                 hover:bg-pri/[0.08] hover:border-pri/35
                 transition-all duration-200 ease-out-expo group"
    >
      <span
        className="grid place-items-center h-7 w-7 rounded-lg bg-pri/15 text-pri
                       border border-pri/25
                       group-hover:bg-pri/25 group-hover:shadow-[0_0_12px_rgb(var(--orion-pri-glow)/0.4)]
                       transition-all"
      >
        <Icon name={light ? "sun" : "moon"} size={14} />
      </span>
      <div className="leading-tight min-w-0 flex-1 text-left">
        <div className="text-[9px] uppercase tracking-[0.22em] text-pri/75 font-semibold">Tema</div>
        <div className="text-[11px] text-text truncate font-medium">
          {light ? "Claro" : "Oscuro"}
        </div>
      </div>
      <Icon
        name="sun"
        size={11}
        className="text-pri/50 opacity-60 group-hover:opacity-100 transition-opacity"
      />
    </button>
  );
}

/* ─── Loader de paneles lazy ───────────────────────────────────────────
   Fallback minimalista mientras Vite resuelve el chunk del panel.
   Sin texto ni spinner para evitar parpadeo cuando el chunk ya está en
   caché del navegador (típicamente <50 ms). Sólo en la primera carga
   en frío se aprecia algo visible. */
function PanelLoader() {
  return (
    <div className="h-full grid place-items-center animate-fade-in">
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.28em] text-text-dim">
        <span className="h-1.5 w-1.5 rounded-full bg-pri animate-pulse" />
        <span>Cargando…</span>
      </div>
    </div>
  );
}

/* ─── footer status — card con dot animado de conexión ─────────────── */
function FooterStatus({ collapsed, muted }: { collapsed: boolean; muted: boolean }) {
  const connected = useOrionStore((s) => s.connected);
  if (collapsed) {
    return (
      <div className="grid place-items-center pb-1">
        <span
          className={`h-2 w-2 rounded-full ${connected ? "bg-ok shadow-[0_0_10px_rgb(var(--orion-ok))] animate-pulse" : "bg-muted"}`}
          title={connected ? "Conectado" : "Sin conexión"}
        />
      </div>
    );
  }

  const stateText = connected ? (muted ? "En silencio" : "Operativo") : "Reconectando…";

  return (
    <div
      className="flex items-center justify-between px-2.5 py-2 rounded-lg
                    border border-pri/20 bg-pri/[0.04]
                    hover:bg-pri/[0.06] transition-colors"
    >
      <div className="flex items-center gap-2.5 min-w-0">
        <span className="grid place-items-center h-7 w-7 rounded-lg bg-pri/15 border border-pri/25 relative">
          <span
            className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-ok shadow-[0_0_8px_rgb(var(--orion-ok))] animate-pulse" : "bg-muted"}`}
          />
        </span>
        <div className="leading-tight min-w-0">
          <div className="text-[9px] uppercase tracking-[0.22em] text-pri/75 font-semibold">
            Sistema
          </div>
          <div
            className={`text-[11px] truncate font-medium ${connected ? "text-ok" : "text-text-dim"}`}
          >
            {stateText}
          </div>
        </div>
      </div>
      <Icon
        name="bolt"
        size={13}
        className={`shrink-0 ${connected ? "text-ok/80" : "text-muted"}`}
      />
    </div>
  );
}
