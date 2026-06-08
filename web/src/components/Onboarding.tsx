/**
 * Onboarding — cinematic first-boot wizard. Asks for the Gemini API key.
 *
 * Stays as a modal overlay. The backend marks the app as ready by
 * emitting `system.ready`, which flips `apiKeyConfigured` in the store.
 */

import { useEffect, useState } from "react";

import { api } from "@/api/rest";
import { useOrionStore } from "@/stores/orion";
import { Icon } from "@/ui/Icon";
import { Button } from "@/ui/primitives";

export function Onboarding() {
  const configured    = useOrionStore((s) => s.apiKeyConfigured);
  const setConfigured = useOrionStore((s) => s.setApiKeyConfigured);
  const [key,  setKey]   = useState("");
  const [busy, setBusy]  = useState(false);
  const [error,setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.getApiKeyStatus()
      .then((s) => { if (alive) setConfigured(s.configured); })
      .catch(() => { /* connection chip handles offline state */ });
    return () => { alive = false; };
  }, [setConfigured]);

  if (configured) return null;

  async function submit() {
    const k = key.trim();
    if (k.length < 10) { setError("La API key parece demasiado corta."); return; }
    setBusy(true); setError(null);
    try {
      await api.setApiKey(k);
      setConfigured(true);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-bg/80 backdrop-blur-md animate-fade-in">
      {/* ambient halo */}
      <div className="absolute h-[480px] w-[480px] rounded-full bg-pri/15 blur-3xl pointer-events-none animate-halo" />

      <div className="relative w-full max-w-md surface-glass rounded-2xl p-7 shadow-lift animate-scale-in">
        {/* brand */}
        <div className="flex items-center gap-3 mb-5">
          <div className="relative h-10 w-10">
            <div className="absolute inset-0 rounded-full bg-pri/25 blur-md animate-breath" />
            <svg viewBox="0 0 40 40" className="relative h-10 w-10">
              <defs>
                <radialGradient id="onbCore" cx="50%" cy="40%" r="55%">
                  <stop offset="0%"   stopColor="#FFFFFF" stopOpacity="0.95" />
                  <stop offset="50%"  stopColor="rgb(var(--orion-pri))" stopOpacity="0.95" />
                  <stop offset="100%" stopColor="#000" stopOpacity="0.85" />
                </radialGradient>
              </defs>
              <circle cx="20" cy="20" r="13" fill="url(#onbCore)" />
            </svg>
          </div>
          <div className="leading-tight">
            <div className="text-[10px] uppercase tracking-[0.24em] text-pri/80">Bienvenido</div>
            <h2 className="text-lg font-semibold tracking-tight text-text">Configura Orion</h2>
          </div>
        </div>

        <p className="text-sm text-text-dim leading-relaxed mb-5">
          Para empezar necesitamos tu API key de Gemini. Puedes obtener una gratis en{" "}
          <a
            href="https://aistudio.google.com/app/apikey" target="_blank" rel="noreferrer"
            className="text-pri underline-offset-2 hover:underline"
          >
            aistudio.google.com
          </a>.
        </p>

        <label className="block text-[10px] uppercase tracking-[0.22em] text-text-dim mb-2">
          API key
        </label>
        <div className="relative">
          <input
            value={key}
            onChange={(e) => setKey(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
            placeholder="AIza…"
            type="password"
            autoFocus
            className="w-full rounded-lg bg-elevated/80 border border-white/[0.08]
                       px-3.5 h-11 text-sm font-mono placeholder-muted
                       focus:outline-none focus:border-pri/40 focus:shadow-glow-soft
                       transition-all duration-200 ease-out-expo"
          />
          <Icon name="shield" size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-pri/70" />
        </div>

        {error && (
          <p className="mt-3 text-xs text-danger flex items-center gap-1.5">
            <Icon name="alert" size={13} /> {error}
          </p>
        )}

        <div className="flex justify-end mt-5">
          <Button
            variant="primary"
            size="md"
            iconRight="chevron-right"
            loading={busy}
            disabled={!key.trim()}
            onClick={submit}
          >
            {busy ? "Guardando" : "Guardar y continuar"}
          </Button>
        </div>

        <p className="mt-5 text-[11px] text-muted leading-relaxed">
          Se guarda localmente en <code className="text-acc/90">config/api_keys.json</code>.
          Si prefieres usar la variable <code className="text-acc/90">ORION_GEMINI_KEY</code>,
          ciérralo, configúrala y reinicia.
        </p>
      </div>
    </div>
  );
}
