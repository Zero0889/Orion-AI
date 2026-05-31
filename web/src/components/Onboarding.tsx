/**
 * Onboarding — wizard de primer arranque.
 *
 * Pide la API key de Gemini si todavía no está configurada (ni en
 * ``ORION_GEMINI_KEY`` ni en ``config/api_keys.json``). Una vez fijada,
 * el backend emite ``system.ready`` y el wizard se cierra solo.
 *
 * Se renderiza como overlay modal sobre el resto del shell para que el
 * usuario no pueda interactuar con nada hasta tener API key.
 */

import { useEffect, useState } from "react";

import { api } from "@/api/rest";
import { useOrionStore } from "@/stores/orion";

export function Onboarding() {
  const configured = useOrionStore((s) => s.apiKeyConfigured);
  const setConfigured = useOrionStore((s) => s.setApiKeyConfigured);
  const [key, setKey]     = useState("");
  const [busy, setBusy]   = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Comprobación inicial al montar.
  useEffect(() => {
    let alive = true;
    api.getApiKeyStatus()
      .then((s) => { if (alive) setConfigured(s.configured); })
      .catch(() => { /* si el backend está caído, el indicador de
                      conexión ya lo refleja */ });
    return () => { alive = false; };
  }, [setConfigured]);

  if (configured) return null;

  async function submit() {
    const k = key.trim();
    if (k.length < 10) {
      setError("La API key parece demasiado corta.");
      return;
    }
    setBusy(true); setError(null);
    try {
      await api.setApiKey(k);
      setConfigured(true);  // optimismo; system.ready también lo cubrirá
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-bg/85 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-lg border border-pri bg-panel p-6">
        <h2 className="text-sm uppercase tracking-[0.3em] text-pri mb-1">Bienvenido a Orion</h2>
        <p className="text-xs text-text-dim mb-5">
          Para empezar necesitamos tu API key de Gemini. Puedes obtener una
          gratis en{" "}
          <a
            href="https://aistudio.google.com/app/apikey" target="_blank" rel="noreferrer"
            className="text-pri underline"
          >
            aistudio.google.com
          </a>.
        </p>

        <label className="block text-[10px] uppercase tracking-widest text-text-dim mb-2">
          API key
        </label>
        <input
          value={key}
          onChange={(e) => setKey(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
          placeholder="AIza…"
          type="password"
          autoFocus
          className="w-full rounded-md bg-panel2 border border-border-b
                     px-3 py-2 text-sm font-mono
                     focus:outline-none focus:border-pri"
        />

        {error && (
          <p className="mt-3 text-xs text-pri">{error}</p>
        )}

        <div className="flex justify-end gap-2 mt-5">
          <button
            onClick={submit}
            disabled={busy || !key.trim()}
            className="rounded-md bg-pri text-bg text-sm font-medium px-4 py-2
                       disabled:opacity-30 hover:brightness-110 transition"
          >
            {busy ? "Guardando…" : "Guardar y continuar"}
          </button>
        </div>

        <p className="text-[10px] text-text-dim mt-4">
          Se guarda localmente en <code>config/api_keys.json</code>. Si
          prefieres usar la variable de entorno <code>ORION_GEMINI_KEY</code>,
          ciérralo, configúrala y reinicia.
        </p>
      </div>
    </div>
  );
}
