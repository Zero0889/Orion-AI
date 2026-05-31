/**
 * SettingsPanel — selector de tema (Fase 3a).
 *
 * Lista los temas disponibles en GET /api/settings/theme y permite
 * cambiarlo con PATCH. El bus emite settings.theme y el frontend
 * refresca; los swatches reflejan la paleta del tema (vista previa
 * en vivo).
 */

import { useEffect, useState } from "react";

import { api, type ThemeInfo } from "@/api/rest";
import { useOrionStore } from "@/stores/orion";

interface Palette { PRI: string; PANEL: string; BG: string; ACC: string; }

export function SettingsPanel() {
  const rev = useOrionStore((s) => s.rev.theme);
  const [info, setInfo]    = useState<ThemeInfo | null>(null);
  const [error, setError]  = useState<string | null>(null);
  const [palettes, setPalettes] = useState<Record<string, Palette>>({});

  useEffect(() => {
    let alive = true;
    api.getTheme()
      .then(async (i) => {
        if (!alive) return;
        setInfo(i);
        // Tomamos las paletas embedded en el GET; no hay endpoint
        // para resolver cada theme por separado, así que vamos a fetch
        // de uno en uno solo si nos hace falta (Fase 3a: nos contentamos
        // con extraer el activo, los demás se previsualizan con info
        // estática si la añadimos en backend más adelante).
        setPalettes({ [i.name]: i.theme as unknown as Palette });
      })
      .catch((e) => { if (alive) setError(String(e)); });
    return () => { alive = false; };
  }, [rev]);

  async function pick(name: string) {
    if (!info || info.name === name) return;
    try {
      const r = await api.setTheme(name);
      setPalettes((p) => ({ ...p, [name]: r.theme as unknown as Palette }));
    } catch (e) { setError(String(e)); }
  }

  if (!info) {
    return (
      <div className="p-6 text-text-dim text-sm">Cargando ajustes…</div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto scrollbar-thin">
      <header className="px-6 py-4 border-b border-border-b">
        <h2 className="text-sm uppercase tracking-[0.3em] text-text-dim">Ajustes</h2>
        <p className="text-xs text-text-dim/70 mt-1">Personaliza la apariencia de Orion.</p>
      </header>

      {error && (
        <div className="mx-6 mt-3 p-2 text-xs rounded border border-pri bg-pri/10 text-pri">
          {error}
        </div>
      )}

      <section className="p-6">
        <h3 className="text-xs uppercase tracking-widest text-text-dim mb-3">Tema</h3>
        <p className="text-xs text-text-dim/70 mb-4">
          Tema activo: <span className="text-pri font-medium">{info.name}</span>.
          La UI Qt actualiza al reiniciar; el frontend web reaccionará en caliente
          al evento <code className="text-acc">settings.theme</code>.
        </p>

        <div className="grid grid-cols-2 gap-2">
          {info.available.map((t) => {
            const active = t.id === info.name;
            const palette = palettes[t.id];
            return (
              <button
                key={t.id}
                onClick={() => pick(t.id)}
                className={`flex items-center gap-3 rounded-lg border px-3 py-2 text-left transition
                  ${active
                    ? "border-pri bg-pri-dim/20"
                    : "border-border-b bg-panel2 hover:border-pri/40"}`}
              >
                <div className="flex gap-0.5">
                  <Swatch color={palette?.PRI   ?? "#666"} />
                  <Swatch color={palette?.ACC   ?? "#444"} />
                  <Swatch color={palette?.PANEL ?? "#222"} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm truncate">{t.name}</div>
                  <div className="text-[10px] uppercase tracking-widest text-text-dim font-mono">{t.id}</div>
                </div>
                {active && <span className="text-pri text-xs">●</span>}
              </button>
            );
          })}
        </div>
      </section>
    </div>
  );
}

function Swatch({ color }: { color: string }) {
  return (
    <span
      className="block w-4 h-6 rounded border border-border-b"
      style={{ background: color }}
    />
  );
}
