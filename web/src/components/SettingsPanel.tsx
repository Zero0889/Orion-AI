/**
 * SettingsPanel — Raycast-style settings with categories.
 *
 * For now the only configurable surface is theming (the backend ships a
 * theme contract via /api/settings/theme + the WS bus). We render every
 * available theme as a card with a live swatch.
 */

import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api, type NotebookLMStatus, type SharingState, type ThemeInfo } from "@/api/rest";
import { BrainSection } from "@/components/BrainSection";
import { GogAccountsCard } from "@/components/GogAccountsCard";
import { deriveAccent, extractDominantColor } from "@/lib/imageColor";
import { QUERY_KEYS } from "@/query/keys";
import { usePersonalization } from "@/stores/personalization";
import { toast } from "@/stores/toast";
import { Icon, type IconName } from "@/ui/Icon";
import { Badge, Button, Empty, SectionHeader, Surface, Switch } from "@/ui/primitives";
import { resolveTheme, toggleLightDark, isLightTheme } from "@/App";

type Tab = "appearance" | "brain" | "network" | "integrations" | "voice" | "data" | "about";
const TABS: { id: Tab; label: string; icon: IconName }[] = [
  { id: "appearance", label: "Apariencia", icon: "sun" },
  // El "cerebro" arriba de Red porque es lo que un usuario nuevo va a
  // querer tocar primero (elegir Gemini vs DeepSeek vs Ollama).
  { id: "brain", label: "Cerebro", icon: "orbit" },
  { id: "network", label: "Red", icon: "wifi" },
  { id: "integrations", label: "Integraciones", icon: "plug" },
  { id: "voice", label: "Voz", icon: "mic" },
  { id: "data", label: "Datos", icon: "memory" },
  { id: "about", label: "Acerca de", icon: "info" },
];

// Tabs que pueden navegarse via evento custom `orion:settings:tab`. El
// BrainChip del ChatPanel lo dispara para llevar al usuario directo a
// la pestaña Cerebro sin que tenga que clickearla manualmente.
const VALID_TABS = new Set<Tab>([
  "appearance",
  "brain",
  "network",
  "integrations",
  "voice",
  "data",
  "about",
]);

export function SettingsPanel() {
  const [tab, setTab] = useState<Tab>("appearance");

  // Escucha "orion:settings:tab" → salta a esa tab si es válida.
  useEffect(() => {
    function onTabRequest(e: Event) {
      const detail = (e as CustomEvent).detail;
      if (typeof detail === "string" && VALID_TABS.has(detail as Tab)) {
        setTab(detail as Tab);
      }
    }
    window.addEventListener("orion:settings:tab", onTabRequest);
    return () => window.removeEventListener("orion:settings:tab", onTabRequest);
  }, []);

  // Theme info via useQuery. Invalidación del bridge cuando llega
  // settings.theme por WS.
  const { data: info = null, error: queryError } = useQuery<ThemeInfo>({
    queryKey: QUERY_KEYS.settingsTheme,
    queryFn: () => api.getTheme(),
  });

  // Errores: la query expone su propio error; pick() puede fallar aparte.
  // Unificamos en un único string mostrado en la UI.
  const [pickError, setPickError] = useState<string | null>(null);
  const error = pickError ?? (queryError ? String(queryError) : null);

  async function pick(name: string) {
    if (!info || info.name === name) return;
    try {
      await api.setTheme(name);
      setPickError(null);
    } catch (e) {
      setPickError(String(e));
    }
  }

  return (
    <div className="flex flex-col h-full">
      <SectionHeader
        eyebrow="Sistema"
        title="Ajustes"
        hint="Personaliza Orion. Los cambios se aplican al instante."
        action={
          info ? (
            <Badge tone="info" dot>
              {info.name}
            </Badge>
          ) : null
        }
      />

      <div className="grid grid-cols-[220px_1fr] flex-1 overflow-hidden">
        {/* sub-nav */}
        <nav className="border-r border-white/[0.06] p-3 flex flex-col gap-1">
          {TABS.map((t) => {
            const isActive = tab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={[
                  "group flex items-center gap-3 rounded-lg px-3 h-9 text-sm border",
                  "transition-all duration-200 ease-out-expo",
                  isActive
                    ? "bg-elevated text-text border-white/[0.06] shadow-rim"
                    : "border-transparent text-text-dim hover:text-text hover:bg-white/[0.03]",
                ].join(" ")}
              >
                <Icon
                  name={t.icon}
                  size={15}
                  className={isActive ? "text-pri" : "text-text-dim group-hover:text-text"}
                />
                <span className="font-medium tracking-tight">{t.label}</span>
              </button>
            );
          })}
        </nav>

        {/* content */}
        <div className="overflow-y-auto scrollbar-thin px-6 py-6">
          {error && (
            <div className="mb-4 flex items-start gap-2 p-3 rounded-md border border-danger/30 bg-danger/10 text-xs text-danger">
              <Icon name="alert" size={14} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {tab === "appearance" && <Appearance info={info} onPick={pick} />}

          {tab === "brain" && <BrainSection />}

          {tab === "network" && <Network onError={setPickError} />}

          {tab === "integrations" && <Integrations />}

          {tab === "voice" && (
            <Section title="Voz">
              <Surface level={2} className="p-4 text-sm text-text-dim leading-relaxed">
                Los ajustes de voz (TTS, idioma, sensibilidad del micrófono) se gestionan
                directamente en el backend de Orion. Próximamente podrás editarlos desde aquí.
              </Surface>
            </Section>
          )}

          {tab === "data" && (
            <Section title="Datos locales">
              <Surface level={2} className="p-4 text-sm text-text-dim leading-relaxed">
                Las notas, memoria e historial se almacenan en{" "}
                <code className="text-acc font-mono">memory/</code> dentro del proyecto. Para
                exportarlos o moverlos, copia esa carpeta.
              </Surface>
            </Section>
          )}

          {tab === "about" && (
            <Section title="Acerca de Orion">
              <Surface level={2} className="p-5">
                <div className="flex items-center gap-3 mb-3">
                  <div className="h-10 w-10 rounded-xl bg-pri/15 grid place-items-center">
                    <Icon name="orbit" size={20} className="text-pri" />
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-[0.22em] text-pri/80">
                      Sistema
                    </div>
                    <div className="text-base font-semibold tracking-tight text-text">
                      O.R.I.O.N
                    </div>
                  </div>
                </div>
                <p className="text-sm text-text-dim leading-relaxed">
                  Operador de Redes Inteligentes y Optimización Neural. Tu sistema operativo
                  asistido por IA — voz, agentes, IoT, telemetría y memoria persistente en un solo
                  espacio local.
                </p>
              </Surface>
            </Section>
          )}
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="animate-fade-in-up">
      <h3 className="text-[11px] uppercase tracking-[0.24em] text-text-dim mb-3">{title}</h3>
      {children}
    </section>
  );
}

function Appearance({ info, onPick }: { info: ThemeInfo | null; onPick: (name: string) => void }) {
  const [light, setLight] = useState(() => isLightTheme());

  function handleLightDarkToggle() {
    const next = toggleLightDark();
    setLight(next === "orion-light");
  }

  if (!info) {
    return (
      <div className="space-y-3">
        <div className="skeleton h-24" />
        <div className="skeleton h-24" />
      </div>
    );
  }
  if (info.available.length === 0) {
    return <Empty icon="sun" title="Sin temas disponibles" />;
  }

  return (
    <>
      {/* Light / Dark global toggle */}
      <Section title="Modo">
        <p className="text-xs text-text-dim/80 mb-4 leading-relaxed">
          Alterna entre modo claro y oscuro al instante. El cambio es inmediato y se guarda en este
          navegador.
        </p>
        <Surface level={2} className="p-4 mb-6">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="grid place-items-center h-10 w-10 rounded-xl bg-pri/15 text-pri">
                <Icon name={light ? "sun" : "moon"} size={18} />
              </span>
              <div>
                <div className="text-sm font-medium text-text">
                  {light ? "Modo claro" : "Modo oscuro"}
                </div>
                <div className="text-[11px] text-text-dim">
                  {light ? "Fondo claro, texto oscuro" : "Fondo oscuro, texto claro"}
                </div>
              </div>
            </div>
            <Switch on={light} onClick={handleLightDarkToggle} />
          </div>
        </Surface>
      </Section>

      {/* Color del Ojo — sobrescribe --orion-pri / --orion-acc en vivo */}
      <EyeColorPicker />

      {/* Color palette picker con mini-previews + agrupado por familia
          (BRIEF · Ajustes). Cada paleta se ubica en uno de tres grupos
          según la slug resuelta — fallback: Especiales si el backend
          devuelve algo que no caemos en otro. */}
      <Section title="Paleta de color">
        <p className="text-xs text-text-dim/80 mb-4 leading-relaxed">
          Cada miniatura es una versión micro de la interfaz con esa paleta aplicada en tiempo real.
        </p>
        <ThemeGroupedGrid available={info.available} activeId={info.name} onPick={onPick} />
      </Section>

      {/* Fondo personalizado del usuario (subir wallpaper) */}
      <WallpaperSection />
    </>
  );
}

/* ── Agrupador de paletas (BRIEF · Ajustes) ──────────────────────────
   Separa la lista del backend en tres familias:
     · Oscuros    — los temas base / sobrios (night, light)
     · Neón       — alto contraste y saturación (cyan, green, red)
     · Especiales — desviaciones temáticas (violet, emerald, amber, purple)
   El mapping es por slug resuelto, así sobrevive a cambios de nombre
   en el backend. Cualquier slug nuevo cae en "Especiales" por defecto. */
type ThemeGroup = "oscuros" | "neon" | "especiales";

function themeGroup(slug: string): ThemeGroup {
  if (slug === "orion-night" || slug === "orion-light") return "oscuros";
  if (slug === "orion-cyan" || slug === "orion-green" || slug === "orion-red") return "neon";
  return "especiales";
}

const GROUP_ORDER: ThemeGroup[] = ["oscuros", "neon", "especiales"];
const GROUP_LABELS: Record<ThemeGroup, string> = {
  oscuros: "Oscuros",
  neon: "Neón",
  especiales: "Especiales",
};

function ThemeGroupedGrid({
  available,
  activeId,
  onPick,
}: {
  available: ThemeInfo["available"];
  activeId: string;
  onPick: (id: string) => void;
}) {
  // Particiono por grupo manteniendo el orden interno del backend
  // (preserva la lista canónica si el backend ya viene priorizada).
  const buckets: Record<ThemeGroup, typeof available> = {
    oscuros: [],
    neon: [],
    especiales: [],
  };
  for (const t of available) {
    buckets[themeGroup(resolveTheme(t.id))].push(t);
  }

  return (
    <div className="flex flex-col gap-5">
      {GROUP_ORDER.map((group) => {
        const items = buckets[group];
        if (items.length === 0) return null;
        return (
          <div key={group}>
            <div className="orion-label text-text-dim/55 mb-2">{GROUP_LABELS[group]}</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
              {items.map((t, i) => {
                const active = t.id === activeId;
                const slug = resolveTheme(t.id);
                return (
                  <button
                    key={t.id}
                    onClick={() => onPick(t.id)}
                    style={{ animationDelay: `${i * 40}ms` }}
                    className={[
                      "group relative rounded-xl border p-2 text-left animate-fade-in-up",
                      "transition-all duration-200 ease-out-expo",
                      active
                        ? "bg-pri/8 border-pri/40 shadow-glow-soft"
                        : "bg-elevated/40 border-white/[0.06] hover:border-white/[0.14] hover:bg-elevated/70",
                    ].join(" ")}
                  >
                    <ThemeMini slug={slug} />
                    <div className="flex items-center gap-2 px-1.5 pt-2 pb-0.5">
                      <div className="flex-1 min-w-0">
                        <div className="text-[12px] font-medium text-text truncate">{t.name}</div>
                        <code className="text-[9px] font-mono text-muted">{t.id}</code>
                      </div>
                      {active && <Icon name="check" size={14} className="text-pri shrink-0" />}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ── ThemeMini — micro-preview real de la UI con esa paleta aplicada ──
   Usa `data-theme={slug}` para que el CSS resuelva los tokens del tema
   correcto sin tener que fetchear paleta del backend. Muestra un
   sidebar diminuto + glow radial + un "ojo" como bullet central. */
function ThemeMini({ slug }: { slug: string }) {
  return (
    <div
      data-theme={slug}
      style={{
        position: "relative",
        height: 64,
        borderRadius: 8,
        overflow: "hidden",
        background: "rgb(var(--orion-bg))",
        border: "1px solid rgb(var(--orion-border) / 0.1)",
        display: "flex",
      }}
    >
      <div
        style={{
          width: 22,
          height: "100%",
          background: "rgb(var(--orion-surface))",
          borderRight: "1px solid rgb(var(--orion-pri) / 0.2)",
          display: "flex",
          flexDirection: "column",
          gap: 3,
          padding: 5,
          boxSizing: "border-box",
        }}
      >
        <span style={{ height: 3, borderRadius: 2, background: "rgb(var(--orion-pri))" }} />
        <span
          style={{ height: 3, borderRadius: 2, background: "rgb(var(--orion-border) / 0.2)" }}
        />
        <span
          style={{ height: 3, borderRadius: 2, background: "rgb(var(--orion-border) / 0.2)" }}
        />
      </div>
      <div
        style={{
          flex: 1,
          display: "grid",
          placeItems: "center",
          background:
            "radial-gradient(circle at 50% 45%, rgb(var(--orion-pri-glow) / 0.18), transparent 70%)",
        }}
      >
        <span
          style={{
            width: 22,
            height: 22,
            borderRadius: 999,
            background:
              "radial-gradient(circle, #fff 0%, rgb(var(--orion-pri)) 55%, rgb(var(--orion-acc)) 100%)",
            boxShadow: "0 0 12px rgb(var(--orion-pri-glow))",
          }}
        />
      </div>
    </div>
  );
}

/* ── EyeColorPicker — 6 swatches que sobrescriben --orion-pri/acc ─────
   Persiste el override en localStorage via usePersonalization. Pulsar el
   swatch activo lo apaga (vuelve a los colores del tema). */
const EYE_COLORS: { name: string; pri: string; acc: string }[] = [
  { name: "Azur", pri: "96 99 236", acc: "99 102 241" },
  { name: "Cian", pri: "42 255 214", acc: "26 184 255" },
  { name: "Esmeralda", pri: "52 211 153", acc: "110 231 183" },
  { name: "Violeta", pri: "167 139 250", acc: "232 121 249" },
  { name: "Ámbar", pri: "251 191 36", acc: "252 211 77" },
  { name: "Carmín", pri: "255 42 77", acc: "255 107 26" },
];

function EyeColorPicker() {
  const eyeColorPri = usePersonalization((s) => s.eyeColorPri);
  const setEyeColor = usePersonalization((s) => s.setEyeColor);
  const clearEyeColor = usePersonalization((s) => s.clearEyeColor);

  return (
    <Section title="Color del Ojo">
      <p className="text-xs text-text-dim/80 mb-4 leading-relaxed">
        Sobrescribe el acento del tema activo. Afecta al Ojo, al chrome y a cualquier elemento que
        use el color primario. Persiste solo en este navegador.
      </p>
      <Surface level={2} className="p-4 flex flex-wrap items-center gap-2">
        {EYE_COLORS.map((c) => {
          const active = eyeColorPri === c.pri;
          return (
            <button
              key={c.name}
              onClick={() => (active ? clearEyeColor() : setEyeColor(c.pri, c.acc))}
              title={c.name}
              className={[
                "flex items-center gap-2 pl-1.5 pr-3 py-1.5 rounded-full border",
                "bg-elevated transition-all duration-200 ease-out-expo",
                active ? "" : "border-white/[0.08] hover:border-white/[0.18]",
              ].join(" ")}
              style={
                active
                  ? {
                      borderColor: `rgb(${c.pri})`,
                      boxShadow: `0 0 12px -2px rgb(${c.pri} / 0.6)`,
                    }
                  : undefined
              }
            >
              <span
                className="h-5 w-5 rounded-full shrink-0"
                style={{
                  background: `radial-gradient(circle, rgb(${c.pri}), rgb(${c.acc}))`,
                  boxShadow: `0 0 8px rgb(${c.pri} / 0.7)`,
                }}
              />
              <span className="text-[12px] font-medium text-text">{c.name}</span>
            </button>
          );
        })}
        {eyeColorPri && (
          <button
            onClick={clearEyeColor}
            className="ml-auto text-[11px] text-text-dim hover:text-text underline-offset-2 hover:underline"
          >
            Restaurar tema
          </button>
        )}
      </Surface>
    </Section>
  );
}

/* ── WallpaperSection — fondo personalizado del usuario ──────────────
   Carga la imagen como dataURL via FileReader, persiste en localStorage
   (puede fallar por quota si la imagen pesa varios MB → toast de error).
   Dos sliders sobre el wallpaper: blur (legibilidad del contenido) y
   overlay (oscurecido). Preview en vivo dentro del card. */
function WallpaperSection() {
  const wallpaper = usePersonalization((s) => s.wallpaper);
  const blur = usePersonalization((s) => s.wallpaperBlur);
  const overlay = usePersonalization((s) => s.wallpaperOverlay);
  const autoColor = usePersonalization((s) => s.autoColorFromWallpaper);
  const setWallpaper = usePersonalization((s) => s.setWallpaper);
  const setBlur = usePersonalization((s) => s.setWallpaperBlur);
  const setOverlay = usePersonalization((s) => s.setWallpaperOverlay);
  const setAutoColor = usePersonalization((s) => s.setAutoColorFromWallpaper);
  const setEyeColor = usePersonalization((s) => s.setEyeColor);
  const clearWallpaper = usePersonalization((s) => s.clearWallpaper);
  const inputRef = useRef<HTMLInputElement>(null);

  // Extrae el color dominante de un dataURL y lo aplica como override
  // del Ojo (pri + acc derivado). Reusable: lo llamamos automáticamente
  // al subir un wallpaper si autoColor está activo, y manualmente desde
  // el botón "Adoptar color del fondo".
  async function applyAutoColorFromDataUrl(dataUrl: string, silent = false) {
    try {
      const dominant = await extractDominantColor(dataUrl);
      const accent = deriveAccent(dominant);
      setEyeColor(dominant.triplet, accent.triplet);
      if (!silent) {
        toast.success(
          "Ojo sincronizado al fondo",
          "Detecté el color dominante de tu imagen y lo apliqué al Ojo.",
        );
      }
    } catch (e) {
      if (!silent) {
        toast.warn("No pude analizar la imagen", String(e));
      }
    }
  }

  function handleFile(file: File) {
    if (!file.type.startsWith("image/")) {
      toast.error("Tipo de archivo no soportado", "Subí una imagen (PNG, JPG, WebP).");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result);
      try {
        setWallpaper(dataUrl);
        toast.success("Fondo aplicado", "El wallpaper ya está activo en toda la interfaz.");
        // Si el usuario quiere que el Ojo se adapte al wallpaper,
        // extraemos el color dominante en background y lo aplicamos.
        // Es async pero no necesitamos bloquear la UI por esto.
        if (autoColor) {
          void applyAutoColorFromDataUrl(dataUrl, true);
        }
      } catch {
        toast.error(
          "La imagen es demasiado grande",
          "El almacenamiento local no alcanza. Probá con una versión más liviana (<3 MB).",
        );
      }
    };
    reader.onerror = () => toast.error("No pude leer la imagen", String(reader.error));
    reader.readAsDataURL(file);
  }

  return (
    <Section title="Fondo personalizado">
      <p className="text-xs text-text-dim/80 mb-4 leading-relaxed">
        Subí una imagen tuya y la uso como fondo de la interfaz. Si no hay imagen, sigue
        renderizándose el NeuralBackground por defecto.
      </p>
      <Surface level={2} className="p-4">
        {/* Preview en vivo */}
        <div
          className="relative h-32 rounded-lg overflow-hidden border border-white/[0.06] mb-4"
          style={{ background: "rgb(var(--orion-sunken))" }}
        >
          {wallpaper ? (
            <>
              <div
                className="absolute inset-0"
                style={{
                  backgroundImage: `url(${wallpaper})`,
                  backgroundSize: "cover",
                  backgroundPosition: "center",
                  filter: `blur(${Math.min(blur, 24)}px)`,
                  transform: `scale(${1 + blur / 200})`,
                }}
              />
              <div
                className="absolute inset-0"
                style={{ background: `rgb(var(--orion-bg) / ${overlay / 100})` }}
              />
              <div className="absolute inset-0 grid place-items-center">
                <span className="text-[10px] uppercase tracking-[0.22em] text-text-dim/70 font-mono">
                  vista previa
                </span>
              </div>
            </>
          ) : (
            <div className="absolute inset-0 grid place-items-center text-[11px] text-muted">
              Sin fondo · usando NeuralBackground
            </div>
          )}
        </div>

        {/* Acciones */}
        <div className="flex flex-wrap items-center gap-2 mb-4">
          <input
            ref={inputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFile(f);
              e.target.value = "";
            }}
          />
          <Button
            variant="primary"
            size="sm"
            icon="upload"
            onClick={() => inputRef.current?.click()}
          >
            {wallpaper ? "Cambiar imagen" : "Subir imagen"}
          </Button>
          {wallpaper && (
            <>
              <Button
                variant="ghost"
                size="sm"
                icon="sparkles"
                onClick={() => void applyAutoColorFromDataUrl(wallpaper)}
                title="Re-extraer el color dominante del wallpaper y aplicarlo al Ojo"
              >
                Adoptar color del fondo
              </Button>
              <Button variant="ghost" size="sm" icon="close" onClick={clearWallpaper}>
                Quitar fondo
              </Button>
            </>
          )}
        </div>

        {/* Toggle: que el Ojo se adapte automáticamente al subir
            wallpapers nuevos. Independiente del Eye color picker —
            el usuario puede mantener autoColor on Y picar manualmente
            uno de los swatches después; el último gana. */}
        <div className="flex items-center justify-between gap-3 py-3 border-t border-white/[0.05]">
          <div className="min-w-0">
            <div className="text-sm font-medium text-text">Adaptar color del Ojo al fondo</div>
            <div className="text-[11px] text-text-dim leading-snug mt-0.5">
              Cuando subas una imagen detecto su color dominante y lo aplico al Ojo automáticamente.
            </div>
          </div>
          <Switch on={autoColor} onClick={() => setAutoColor(!autoColor)} />
        </div>

        {/* Sliders blur + overlay (solo si hay wallpaper) */}
        {wallpaper && (
          <div className="space-y-3 pt-3 border-t border-white/[0.05]">
            <SliderRow
              label="Desenfoque"
              value={blur}
              min={0}
              max={40}
              unit="px"
              onChange={setBlur}
            />
            <SliderRow
              label="Oscurecido"
              value={overlay}
              min={0}
              max={90}
              unit="%"
              onChange={setOverlay}
            />
          </div>
        )}
      </Surface>
    </Section>
  );
}

function SliderRow({
  label,
  value,
  min,
  max,
  unit,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  unit: string;
  onChange: (n: number) => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-[11px] uppercase tracking-[0.18em] text-text-dim w-24 shrink-0">
        {label}
      </span>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="flex-1 accent-pri"
      />
      <span className="text-xs font-mono tabular-nums w-12 text-right text-text-dim">
        {value}
        {unit}
      </span>
    </div>
  );
}

/* ── Network / Tailscale ─────────────────────────────────────────── */
function Network({ onError }: { onError: (e: string | null) => void }) {
  const [state, setState] = useState<SharingState | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .getSharing()
      .then((s) => {
        if (alive) {
          setState(s);
          onError(null);
        }
      })
      .catch((e) => {
        if (alive) onError(String(e));
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function toggle() {
    if (!state || busy) return;
    setBusy(true);
    try {
      const next = await api.setSharing(!state.enabled);
      setState({ enabled: next.enabled, tailscale_ip: next.tailscale_ip, port: next.port });
      onError(null);
    } catch (e) {
      onError(String(e));
    } finally {
      setBusy(false);
    }
  }

  function copyUrl() {
    if (!state?.tailscale_ip) return;
    const url = `http://${state.tailscale_ip}:${state.port}`;
    navigator.clipboard?.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  async function refresh() {
    setBusy(true);
    try {
      const s = await api.getSharing();
      setState(s);
      onError(null);
    } catch (e) {
      onError(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!state) {
    return (
      <Section title="Red">
        <div className="space-y-3">
          <div className="skeleton h-24" />
        </div>
      </Section>
    );
  }

  const url = state.tailscale_ip ? `http://${state.tailscale_ip}:${state.port}` : null;
  const isOn = state.enabled;

  return (
    <Section title="Compartir vía Tailscale">
      <p className="text-xs text-text-dim/80 mb-4 leading-relaxed">
        Cuando está activado, los dispositivos conectados a tu red privada Tailscale (móvil, otra
        PC) pueden abrir Orion desde la URL de abajo. Tu PC sigue invisible para el resto de
        internet — el filtro acepta solo IPs del rango{" "}
        <code className="text-acc font-mono text-[11px]">100.64.0.0/10</code> y{" "}
        <code className="text-acc font-mono text-[11px]">127.0.0.1</code>.
      </p>

      <Surface level={2} className="p-5">
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Icon name="wifi" size={16} className={isOn ? "text-pri" : "text-text-dim"} />
              <span className="text-sm font-medium text-text">
                {isOn ? "Compartiendo con Tailscale" : "Solo localhost (este PC)"}
              </span>
              {isOn && (
                <Badge tone="info" dot>
                  activo
                </Badge>
              )}
            </div>
            <div className="text-[11px] text-muted mt-0.5">
              {isOn
                ? "Acceso permitido desde dispositivos Tailscale autorizados"
                : "Ningún otro dispositivo puede conectarse"}
            </div>
          </div>
          <Switch on={isOn} onClick={toggle} />
        </div>

        {/* URL para conectarse desde el móvil */}
        <div className="mt-4 pt-4 border-t border-white/[0.06]">
          <div className="text-[10px] uppercase tracking-[0.18em] text-text-dim mb-2">
            URL de acceso desde otros dispositivos
          </div>
          {url ? (
            <div className="flex items-center gap-2">
              <code className="flex-1 px-3 h-9 grid place-items-center rounded-md bg-elevated border border-white/[0.08] font-mono text-sm text-acc truncate">
                {url}
              </code>
              <Button
                variant="secondary"
                size="sm"
                icon={copied ? "check" : "paperclip"}
                onClick={copyUrl}
              >
                {copied ? "Copiado" : "Copiar"}
              </Button>
            </div>
          ) : (
            <div className="px-3 py-2 rounded-md border border-dashed border-white/[0.08] text-[11px] text-text-dim">
              No se detectó IP de Tailscale. ¿Está instalado y conectado? Revisa el ícono en la
              bandeja del sistema y haz click en{" "}
              <button className="text-pri underline" onClick={refresh}>
                Refrescar
              </button>
              .
            </div>
          )}
        </div>

        {/* Aviso de seguridad */}
        {isOn && (
          <div className="mt-4 flex items-start gap-2.5 p-3 rounded-md border border-warn/30 bg-warn/10">
            <Icon name="alert" size={14} className="text-warn shrink-0 mt-0.5" />
            <div className="text-[11px] text-warn leading-relaxed">
              Mientras esté activado, cualquier dispositivo con sesión Tailscale en tu cuenta puede
              controlar Orion. Si pierdes el móvil, revoca su acceso desde{" "}
              <a
                href="https://login.tailscale.com/admin/machines"
                target="_blank"
                rel="noopener noreferrer"
                className="underline"
              >
                tailscale.com/admin/machines
              </a>
              .
            </div>
          </div>
        )}
      </Surface>

      <Surface level={2} className="mt-3 p-4">
        <div className="text-[11px] uppercase tracking-[0.18em] text-text-dim mb-2">
          Cómo conectarte desde el móvil
        </div>
        <ol className="text-xs text-text-dim leading-relaxed list-decimal pl-5 space-y-1">
          <li>Instala Tailscale en el móvil y entra con la misma cuenta que tu PC.</li>
          <li>Asegúrate de que el toggle Tailscale del móvil está en ON.</li>
          <li>Activa el switch de arriba ↑ y copia la URL.</li>
          <li>
            Pégala en el navegador del móvil. Funciona desde cualquier red — WiFi, datos, cualquier
            país.
          </li>
        </ol>
      </Surface>
    </Section>
  );
}

/* ─── INTEGRACIONES ───────────────────────────────────────────────────
   Acá viven los enlaces a servicios externos. Por ahora solo NotebookLM
   pero la sección está armada para crecer (Google Drive, Slack, etc).  */
function Integrations() {
  return (
    <Section title="Integraciones">
      <div className="flex flex-col gap-3">
        <GogAccountsCard />
        <NotebookLMCard />
      </div>
    </Section>
  );
}

function NotebookLMCard() {
  const [status, setStatus] = useState<NotebookLMStatus | null>(null);
  const [loading, setLoading] = useState(true);

  // Poll de status. Más rápido cuando hay login en progreso.
  useEffect(() => {
    let alive = true;
    let timer: number | undefined;

    async function tick() {
      try {
        const s = await api.notebookLMStatus();
        if (!alive) return;
        const prevRunning = status?.login.status === "running";
        setStatus(s);
        setLoading(false);
        // Si el login terminó (running → success/failed), avisamos
        if (prevRunning && s.login.status !== "running") {
          if (s.login.status === "success") {
            toast.success("NotebookLM conectado", "Ya podés volver a investigar.");
          } else {
            toast.error("Login falló", s.login.message);
          }
        }
      } catch {
        if (alive) {
          setLoading(false);
        }
      } finally {
        if (alive) {
          // Poll cada 2s si hay login en progreso, sino cada 15s para
          // no martillar el backend cuando todo está estable.
          const next = status?.login.status === "running" ? 2000 : 15000;
          timer = window.setTimeout(tick, next);
        }
      }
    }
    tick();
    return () => {
      alive = false;
      if (timer) window.clearTimeout(timer);
    };
    // status?.login.status arriba intencional — re-vuelve a programar
    // el siguiente tick con el intervalo correcto.
  }, [status?.login.status]);

  async function login() {
    try {
      await api.notebookLMLogin();
      toast.info(
        "Login iniciado",
        "Se abrirá Chromium en breve. Iniciá sesión con tu cuenta Google.",
      );
      // Forzamos refresh inmediato para mostrar el estado 'running'
      const s = await api.notebookLMStatus();
      setStatus(s);
    } catch (e) {
      toast.error("No se pudo iniciar login", String(e));
    }
  }

  async function cancel() {
    try {
      await api.notebookLMCancel();
      const s = await api.notebookLMStatus();
      setStatus(s);
      toast.warn("Login cancelado");
    } catch (e) {
      toast.error("Cancelación falló", String(e));
    }
  }

  if (loading) {
    return (
      <Surface level={2} className="p-5">
        <div className="skeleton h-20" />
      </Surface>
    );
  }
  if (!status) return null;

  const inProgress = status.login.status === "running";
  const hasSession = status.has_session;

  // Tone + label para el chip de estado de la sesión
  const sessionTone: "ok" | "warn" | "muted" = inProgress ? "warn" : hasSession ? "ok" : "muted";
  const sessionLabel = inProgress ? "Autenticando…" : hasSession ? "Conectado" : "Sin sesión";

  return (
    <Surface level={2} className="p-5">
      <div className="flex items-start gap-4">
        <div className="grid place-items-center h-11 w-11 rounded-xl bg-pri/15 text-pri shrink-0">
          <Icon name="search" size={20} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h4 className="text-sm font-semibold text-text">NotebookLM</h4>
            <SessionBadge tone={sessionTone} label={sessionLabel} pulse={inProgress} />
            {!status.installed && (
              // BRIEF G3: falta de CLI es atención pendiente, no error
              // runtime. Ámbar — el usuario sabe qué hacer (instalar).
              <Badge tone="warn" dot>
                Sin CLI
              </Badge>
            )}
          </div>
          <p className="text-xs text-text-dim leading-relaxed mt-1">
            Investigaciones profundas con auto-import de fuentes via el research agent de Google.
            Requiere login con tu cuenta Google — la sesión se guarda localmente en{" "}
            <code className="font-mono text-acc/80">~/.notebooklm/</code>.
          </p>

          {/* Mensaje del último intento */}
          {status.login.status !== "idle" && status.login.message && (
            <div
              className={[
                "mt-3 text-[11px] leading-relaxed p-2.5 rounded-md border font-mono",
                status.login.status === "success"
                  ? "text-ok      border-ok/30    bg-ok/5"
                  : status.login.status === "failed"
                    ? "text-danger  border-danger/30 bg-danger/5"
                    : "text-warn border-warn/30 bg-warn/5",
              ].join(" ")}
            >
              {status.login.message}
              {inProgress && status.login.elapsed > 0 && (
                <span className="ml-2 opacity-70 tabular-nums">
                  · {Math.floor(status.login.elapsed)}s
                </span>
              )}
            </div>
          )}

          {/* CTA */}
          <div className="mt-4 flex items-center gap-2">
            {inProgress ? (
              <>
                <Button variant="secondary" size="sm" icon="close" onClick={cancel}>
                  Cancelar
                </Button>
                <span className="text-[11px] text-text-dim">
                  Mirá la ventana de Chromium que se abrió.
                </span>
              </>
            ) : (
              <>
                <Button
                  variant="primary"
                  size="sm"
                  icon={hasSession ? "orbit" : "bolt"}
                  onClick={login}
                  disabled={!status.installed}
                >
                  {hasSession ? "Renovar sesión" : "Iniciar sesión"}
                </Button>
                {!status.installed && (
                  <span className="text-[11px] text-danger">
                    Instalá:{" "}
                    <code className="font-mono">
                      .venv\Scripts\pip.exe install "notebooklm-py[browser]"
                    </code>
                  </span>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </Surface>
  );
}

function SessionBadge({
  tone,
  label,
  pulse,
}: {
  tone: "ok" | "warn" | "muted";
  label: string;
  pulse?: boolean;
}) {
  const dotClass =
    tone === "ok"
      ? "bg-ok   shadow-[0_0_8px_rgb(var(--orion-ok))]"
      : tone === "warn"
        ? "bg-warn shadow-[0_0_8px_rgb(var(--orion-warn))]"
        : "bg-muted";
  const textClass = tone === "ok" ? "text-ok" : tone === "warn" ? "text-warn" : "text-text-dim";
  return (
    <span className="inline-flex items-center gap-1.5 text-[10px] uppercase tracking-[0.22em] font-mono">
      <span
        className={`h-1.5 w-1.5 rounded-full ${dotClass} ${pulse ? "animate-pulse-soft" : ""}`}
      />
      <span className={textClass}>{label}</span>
    </span>
  );
}
