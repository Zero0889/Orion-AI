/**
 * SettingsPanel — Raycast-style settings with categories.
 *
 * For now the only configurable surface is theming (the backend ships a
 * theme contract via /api/settings/theme + the WS bus). We render every
 * available theme as a card with a live swatch.
 */

import { useEffect, useState } from "react";

import { api, type SharingState, type ThemeInfo } from "@/api/rest";
import { useOrionStore } from "@/stores/orion";
import { Icon, type IconName } from "@/ui/Icon";
import { Badge, Button, Empty, SectionHeader, Surface, Switch } from "@/ui/primitives";

interface Palette { PRI?: string; PANEL?: string; BG?: string; ACC?: string }

type Tab = "appearance" | "network" | "voice" | "data" | "about";
const TABS: { id: Tab; label: string; icon: IconName }[] = [
  { id: "appearance", label: "Apariencia", icon: "sun"   },
  { id: "network",    label: "Red",        icon: "wifi"  },
  { id: "voice",      label: "Voz",        icon: "mic"   },
  { id: "data",       label: "Datos",      icon: "memory" },
  { id: "about",      label: "Acerca de",  icon: "info"  },
];

export function SettingsPanel() {
  const rev = useOrionStore((s) => s.rev.theme);
  const [tab, setTab]       = useState<Tab>("appearance");
  const [info, setInfo]     = useState<ThemeInfo | null>(null);
  const [error, setError]   = useState<string | null>(null);
  const [palettes, setPalettes] = useState<Record<string, Palette>>({});

  useEffect(() => {
    let alive = true;
    api.getTheme()
      .then((i) => {
        if (!alive) return;
        setInfo(i);
        setPalettes({ [i.name]: i.theme as Palette });
      })
      .catch((e) => { if (alive) setError(String(e)); });
    return () => { alive = false; };
  }, [rev]);

  async function pick(name: string) {
    if (!info || info.name === name) return;
    try {
      const r = await api.setTheme(name);
      setPalettes((p) => ({ ...p, [name]: r.theme as Palette }));
    } catch (e) { setError(String(e)); }
  }

  return (
    <div className="flex flex-col h-full">
      <SectionHeader
        eyebrow="Sistema"
        title="Ajustes"
        hint="Personaliza Orion. Los cambios se aplican al instante."
        action={info ? <Badge tone="info" dot>{info.name}</Badge> : null}
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
                <Icon name={t.icon} size={15}
                      className={isActive ? "text-pri" : "text-text-dim group-hover:text-text"} />
                <span className="font-medium tracking-tight">{t.label}</span>
              </button>
            );
          })}
        </nav>

        {/* content */}
        <div className="overflow-y-auto scrollbar-thin px-6 py-6">
          {error && (
            <div className="mb-4 flex items-start gap-2 p-3 rounded-md border border-danger/30 bg-danger/10 text-xs text-danger">
              <Icon name="alert" size={14} className="mt-0.5 shrink-0" /><span>{error}</span>
            </div>
          )}

          {tab === "appearance" && (
            <Appearance info={info} palettes={palettes} onPick={pick} />
          )}

          {tab === "network" && <Network onError={setError} />}

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
                <code className="text-acc font-mono">memory/</code> dentro del proyecto.
                Para exportarlos o moverlos, copia esa carpeta.
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
                    <div className="text-[10px] uppercase tracking-[0.22em] text-pri/80">Sistema</div>
                    <div className="text-base font-semibold tracking-tight text-text">O.R.I.O.N</div>
                  </div>
                </div>
                <p className="text-sm text-text-dim leading-relaxed">
                  Operador de Redes Inteligentes y Optimización Neural. Tu sistema operativo
                  asistido por IA — voz, agentes, IoT, telemetría y memoria persistente en
                  un solo espacio local.
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

function Appearance({
  info, palettes, onPick,
}: {
  info: ThemeInfo | null;
  palettes: Record<string, Palette>;
  onPick: (name: string) => void;
}) {
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
    <Section title="Tema">
      <p className="text-xs text-text-dim/80 mb-4 leading-relaxed">
        Cambia la paleta global. El frontend reacciona al evento{" "}
        <code className="text-acc font-mono text-[11px]">settings.theme</code>{" "}
        y aplica el nuevo tema en caliente.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
        {info.available.map((t, i) => {
          const active  = t.id === info.name;
          const palette = palettes[t.id];
          return (
            <button
              key={t.id}
              onClick={() => onPick(t.id)}
              style={{ animationDelay: `${i * 40}ms` }}
              className={[
                "group relative rounded-xl border px-4 py-3.5 text-left animate-fade-in-up",
                "transition-all duration-200 ease-out-expo",
                active
                  ? "bg-pri/8 border-pri/40 shadow-glow-soft"
                  : "bg-elevated/40 border-white/[0.06] hover:border-white/[0.14]",
              ].join(" ")}
            >
              <div className="flex items-center gap-3">
                <div className="flex gap-0.5">
                  <Swatch color={palette?.BG    ?? "#0A0B0F"} />
                  <Swatch color={palette?.PANEL ?? "#11131A"} />
                  <Swatch color={palette?.PRI   ?? "#6D7CFF"} />
                  <Swatch color={palette?.ACC   ?? "#7EE7FF"} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-text truncate">{t.name}</div>
                  <code className="text-[10px] font-mono text-muted">{t.id}</code>
                </div>
                {active && <Icon name="check" size={16} className="text-pri shrink-0" />}
              </div>
            </button>
          );
        })}
      </div>
    </Section>
  );
}

function Swatch({ color }: { color: string }) {
  return (
    <span
      className="block w-4 h-8 rounded border border-white/[0.08]"
      style={{ background: color }}
    />
  );
}

/* ── Network / Tailscale ─────────────────────────────────────────── */
function Network({ onError }: { onError: (e: string | null) => void }) {
  const [state, setState] = useState<SharingState | null>(null);
  const [busy, setBusy]   = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let alive = true;
    api.getSharing()
      .then((s) => { if (alive) { setState(s); onError(null); } })
      .catch((e) => { if (alive) onError(String(e)); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function toggle() {
    if (!state || busy) return;
    setBusy(true);
    try {
      const next = await api.setSharing(!state.enabled);
      setState({ enabled: next.enabled, tailscale_ip: next.tailscale_ip, port: next.port });
      onError(null);
    } catch (e) { onError(String(e)); }
    finally { setBusy(false); }
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
    } catch (e) { onError(String(e)); }
    finally { setBusy(false); }
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
        Cuando está activado, los dispositivos conectados a tu red privada Tailscale
        (móvil, otra PC) pueden abrir Orion desde la URL de abajo. Tu PC sigue invisible
        para el resto de internet — el filtro acepta solo IPs del rango{" "}
        <code className="text-acc font-mono text-[11px]">100.64.0.0/10</code>{" "}
        y <code className="text-acc font-mono text-[11px]">127.0.0.1</code>.
      </p>

      <Surface level={2} className="p-5">
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Icon name="wifi" size={16} className={isOn ? "text-pri" : "text-text-dim"} />
              <span className="text-sm font-medium text-text">
                {isOn ? "Compartiendo con Tailscale" : "Solo localhost (este PC)"}
              </span>
              {isOn && <Badge tone="info" dot>activo</Badge>}
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
              <Button variant="secondary" size="sm" icon={copied ? "check" : "paperclip"} onClick={copyUrl}>
                {copied ? "Copiado" : "Copiar"}
              </Button>
            </div>
          ) : (
            <div className="px-3 py-2 rounded-md border border-dashed border-white/[0.08] text-[11px] text-text-dim">
              No se detectó IP de Tailscale.{" "}
              ¿Está instalado y conectado? Revisa el ícono en la bandeja del sistema y haz click en{" "}
              <button className="text-pri underline" onClick={refresh}>Refrescar</button>.
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
              <a href="https://login.tailscale.com/admin/machines" target="_blank" rel="noreferrer"
                 className="underline">tailscale.com/admin/machines</a>.
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
          <li>Pégala en el navegador del móvil. Funciona desde cualquier red — WiFi, datos, cualquier país.</li>
        </ol>
      </Surface>
    </Section>
  );
}
