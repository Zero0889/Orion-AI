/**
 * Onboarding — wizard multipaso para primer arranque.
 *
 * Steps:
 *   0. Welcome        — qué es Orion y qué necesita.
 *   1. Brain picker   — elige Gemini / DeepSeek / Ollama como cerebro.
 *   2. Brain setup    — content distinto por brain:
 *                         · Gemini   → pide API key + valida contra Gemini
 *                         · DeepSeek → pide key + aplica brain en caliente
 *                         · Ollama   → detecta + instrucciones de instalación
 *   3. Integraciones  — opcional (Google OAuth, IoT, Skills).
 *   4. Done           — quick start.
 *
 * El paso 2 es bloqueante solo si el usuario quiere usar ese cerebro de
 * forma efectiva. Puede volver atrás y cambiar. Si el backend dice
 * `status.ready` ya antes (env var Gemini o brain ya configurado), saltamos
 * directo a Integraciones.
 */

import { useEffect, useMemo, useState } from "react";

import { api, type BrainProvider, type BrainState, type OnboardingStatus } from "@/api/rest";
import { useOrionStore } from "@/stores/orion";
import { Icon, type IconName } from "@/ui/Icon";
import { Button } from "@/ui/primitives";

const STATUS_POLL_MS = 1500;

// Flag persistido: una vez que el usuario terminó el wizard (o arrancó
// con todo ya configurado), no volvemos a mostrarlo en próximas sesiones.
// Vive en localStorage para que sobreviva F5 y reinicios sin tocar el
// backend. Reseteable manualmente borrando la entrada (DevTools) si
// alguien quiere ver el wizard de nuevo.
const ONBOARDING_DONE_KEY = "orion.onboarding_done";

function readOnboardingDone(): boolean {
  try {
    return window.localStorage.getItem(ONBOARDING_DONE_KEY) === "1";
  } catch {
    return false;
  }
}

function markOnboardingDone(): void {
  try {
    window.localStorage.setItem(ONBOARDING_DONE_KEY, "1");
  } catch {
    /* localStorage no disponible (modo privado) — sin persistencia. */
  }
}

type Step = 0 | 1 | 2 | 3 | 4;
type BrainChoice = "gemini" | "deepseek" | "ollama";

export function Onboarding() {
  const setConfigured = useOrionStore((s) => s.setApiKeyConfigured);

  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [reachable, setReachable] = useState<boolean | null>(null);
  const [step, setStep] = useState<Step | null>(null);
  // Inicia ya "dismissed" si el usuario completó el wizard alguna vez.
  // Así no parpadea ni siquiera por un frame.
  const [dismissed, setDismissed] = useState<boolean>(() => readOnboardingDone());
  // Cerebro que el usuario eligió en el step 1. Hasta entonces queda en
  // null y el step 2 muestra el placeholder.
  const [brainChoice, setBrainChoice] = useState<BrainChoice | null>(null);

  // ── Polling del status ──────────────────────────────────────────────
  // Idéntico al previo: SOLO toca status/reachable. Step lo maneja el
  // useEffect siguiente, una vez al inicio.
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      try {
        const s = await api.onboardingStatus();
        if (!alive) return;
        setStatus(s);
        setReachable(true);
      } catch {
        if (!alive) return;
        setReachable(false);
      }
      if (alive) timer = setTimeout(tick, STATUS_POLL_MS);
    };
    tick();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, []);

  // ── Decisión del step inicial ──────────────────────────────────────
  // Una sola vez cuando el primer status llega:
  //   - ready → el cerebro ya está configurado (Gemini key, DeepSeek u
  //     Ollama). Persistimos el flag y dismiss → el usuario va directo a
  //     la app sin pasar por el wizard. Esto cubre el caso "ya me
  //     onboardié antes" y también el caso "tengo env var Gemini
  //     pre-configurada" donde el wizard nunca debería aparecer.
  //   - no ready → arrancamos en welcome (primer arranque real).
  useEffect(() => {
    if (status === null) return;
    if (step !== null) return;
    if (status.ready) {
      setConfigured(true);
      markOnboardingDone();
      setDismissed(true);
    } else {
      setStep(0);
    }
  }, [status, step, setConfigured]);

  if (dismissed) return null;
  if (status === null || step === null) return null;

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-bg/80 backdrop-blur-md animate-fade-in">
      <div className="absolute h-[480px] w-[480px] rounded-full bg-pri/15 blur-3xl pointer-events-none animate-halo" />

      <div className="relative w-full max-w-lg surface-glass rounded-2xl p-7 shadow-lift animate-scale-in">
        <Header step={step} />

        {step === 0 && <WelcomeStep onNext={() => setStep(1)} />}
        {step === 1 && (
          <BrainPickerStep
            onPick={(choice) => {
              setBrainChoice(choice);
              setStep(2);
            }}
            onBack={() => setStep(0)}
          />
        )}
        {step === 2 && brainChoice && (
          <BrainSetupStep
            choice={brainChoice}
            status={status}
            reachable={reachable}
            onBack={() => setStep(1)}
            onReady={(fresh) => {
              setStatus(fresh);
              setConfigured(true);
              setStep(3);
            }}
          />
        )}
        {step === 3 && <IntegrationsStep onNext={() => setStep(4)} />}
        {step === 4 && (
          <DoneStep
            onClose={() => {
              setConfigured(true);
              markOnboardingDone();
              setDismissed(true);
            }}
          />
        )}
        <div className="mt-4 text-center text-[9px] uppercase tracking-[0.18em] text-muted/60">
          Wizard v0.2.0 (cerebro configurable)
        </div>
      </div>
    </div>
  );
}

// ── Header ─────────────────────────────────────────────────────────────

function Header({ step }: { step: Step }) {
  const labels = ["Bienvenida", "Cerebro", "Setup", "Google", "Listo"];
  return (
    <div className="mb-6">
      <div className="flex items-center gap-3 mb-4">
        <div className="relative h-10 w-10">
          <div className="absolute inset-0 rounded-full bg-pri/25 blur-md animate-breath" />
          <svg viewBox="0 0 40 40" className="relative h-10 w-10">
            <defs>
              <radialGradient id="onbCore" cx="50%" cy="40%" r="55%">
                <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.95" />
                <stop offset="50%" stopColor="rgb(var(--orion-pri))" stopOpacity="0.95" />
                <stop offset="100%" stopColor="#000" stopOpacity="0.85" />
              </radialGradient>
            </defs>
            <circle cx="20" cy="20" r="13" fill="url(#onbCore)" />
          </svg>
        </div>
        <div className="leading-tight">
          <div className="text-[10px] uppercase tracking-[0.24em] text-pri/80">Configurá Orion</div>
          <h2 className="text-lg font-semibold tracking-tight text-text">{labels[step]}</h2>
        </div>
      </div>
      {/* Progress dots */}
      <div className="flex items-center gap-1.5">
        {labels.map((label, i) => (
          <div
            key={label}
            className={[
              "h-1.5 rounded-full transition-all duration-300",
              i === step ? "w-8 bg-pri" : i < step ? "w-4 bg-pri/60" : "w-4 bg-white/[0.08]",
            ].join(" ")}
            aria-label={`Paso ${i + 1} de ${labels.length}: ${label}`}
          />
        ))}
      </div>
    </div>
  );
}

// ── Step 0: Welcome ────────────────────────────────────────────────────

function WelcomeStep({ onNext }: { onNext: () => void }) {
  return (
    <div>
      <p className="text-sm text-text leading-relaxed mb-4">
        Orion es un asistente personal con voz, visión y control de tu PC. Funciona localmente y vos
        elegís qué motor de IA lo impulsa.
      </p>
      <ul className="space-y-2 mb-6 text-[13px] text-text-dim">
        <li className="flex items-start gap-2">
          <Icon name="check" size={13} className="text-pri mt-0.5 shrink-0" />
          <span>Charlá por voz en tiempo real, abrí apps, leé notas, controlá IoT en casa.</span>
        </li>
        <li className="flex items-start gap-2">
          <Icon name="check" size={13} className="text-pri mt-0.5 shrink-0" />
          <span>Notificaciones de Gmail y Classroom unificadas (opcional, OAuth con Google).</span>
        </li>
        <li className="flex items-start gap-2">
          <Icon name="check" size={13} className="text-pri mt-0.5 shrink-0" />
          <span>Memoria a largo plazo, skills personalizables, automatizaciones.</span>
        </li>
      </ul>
      <p className="text-[12px] text-muted mb-6">
        Vas a elegir el cerebro: Gemini (voz incluida), DeepSeek (chat barato) u Ollama (local,
        privado, sin internet). Las integraciones con Google son opcionales.
      </p>
      <div className="flex justify-end">
        <Button variant="primary" size="md" iconRight="chevron-right" onClick={onNext}>
          Empezar
        </Button>
      </div>
    </div>
  );
}

// ── Step 1: Brain picker ───────────────────────────────────────────────

function BrainPickerStep({
  onPick,
  onBack,
}: {
  onPick: (choice: BrainChoice) => void;
  onBack: () => void;
}) {
  return (
    <div>
      <p className="text-sm text-text-dim leading-relaxed mb-4">
        ¿Qué motor querés que use Orion para pensar y responderte?{" "}
        <span className="text-text">Podés cambiarlo después</span> en Ajustes → Cerebro.
      </p>

      <div className="space-y-2.5 mb-5">
        <BrainCard
          choice="gemini"
          icon="orbit"
          title="Gemini (Google)"
          tag="Voz incluida · gratis"
          description="El default histórico. Voz en tiempo real, multimodal, free tier generoso. Necesita una API key de Google AI Studio (1 minuto)."
          onClick={() => onPick("gemini")}
        />
        <BrainCard
          choice="deepseek"
          icon="bolt"
          title="DeepSeek (cloud)"
          tag="Chat barato · sin voz"
          description="DeepSeek-V3 / R1, muy fuerte en código y razonamiento. Pago por uso pero muy barato (centavos por día). Solo chat de texto."
          onClick={() => onPick("deepseek")}
        />
        <BrainCard
          choice="ollama"
          icon="cpu"
          title="Ollama (local)"
          tag="100% offline · sin cuenta"
          description="Modelos abiertos en tu PC. Privado, sin internet, sin API keys. Con 16 GB de RAM corre llama3.1:8b cómodo. Solo chat de texto."
          onClick={() => onPick("ollama")}
        />
      </div>

      <div className="flex items-center justify-between">
        <Button variant="ghost" size="sm" icon="arrow-left" onClick={onBack}>
          Atrás
        </Button>
        <p className="text-[11px] text-muted">Elegí una opción para continuar.</p>
      </div>
    </div>
  );
}

function BrainCard({
  icon,
  title,
  tag,
  description,
  onClick,
}: {
  choice: BrainChoice;
  icon: IconName;
  title: string;
  tag: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full text-left p-3.5 rounded-lg border border-white/[0.06] bg-white/[0.02]
                 hover:border-pri/40 hover:bg-pri/[0.04] transition-all duration-200 ease-out-expo
                 group"
    >
      <div className="flex items-start gap-3">
        <span className="grid place-items-center h-10 w-10 rounded-md bg-pri/10 text-pri shrink-0 group-hover:bg-pri/20 transition-colors">
          <Icon name={icon} size={18} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-text">{title}</span>
            <span className="text-[10px] uppercase tracking-[0.18em] text-pri/80 font-mono">
              {tag}
            </span>
          </div>
          <p className="text-[12px] text-text-dim leading-relaxed mt-1">{description}</p>
        </div>
        <Icon
          name="chevron-right"
          size={14}
          className="text-text-dim group-hover:text-text mt-1 shrink-0"
        />
      </div>
    </button>
  );
}

// ── Step 2: Brain setup (depende del choice) ───────────────────────────

function BrainSetupStep({
  choice,
  status,
  reachable,
  onBack,
  onReady,
}: {
  choice: BrainChoice;
  status: OnboardingStatus;
  reachable: boolean | null;
  onBack: () => void;
  onReady: (fresh: OnboardingStatus) => void;
}) {
  return (
    <div>
      {choice === "gemini" && (
        <GeminiSetup status={status} reachable={reachable} onSaved={onReady} />
      )}
      {choice === "deepseek" && <DeepSeekSetup onSaved={onReady} />}
      {choice === "ollama" && <OllamaSetup onSaved={onReady} />}

      <div className="flex items-center justify-between mt-5 pt-4 border-t border-white/[0.05]">
        <Button variant="ghost" size="sm" icon="arrow-left" onClick={onBack}>
          Elegir otro cerebro
        </Button>
      </div>
    </div>
  );
}

// ── Gemini setup (idéntico al wizard previo) ───────────────────────────

function GeminiSetup({
  status,
  reachable,
  onSaved,
}: {
  status: OnboardingStatus;
  reachable: boolean | null;
  onSaved: (fresh: OnboardingStatus) => void;
}) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    const k = key.trim();
    if (k.length < 10) {
      setError("La API key parece demasiado corta.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const r = await api.onboardingSave(k, true);
      if (r.ok) {
        const fresh = await api.onboardingStatus();
        onSaved(fresh);
      } else {
        setError(r.message || "Algo falló guardando la API key.");
      }
    } catch (e) {
      setError(String(e).replace(/^Error:\s*/, ""));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <p className="text-sm text-text-dim leading-relaxed mb-2">
        Necesitamos una <span className="text-text font-medium">API key de Gemini</span>. Es gratis
        y tarda 1 minuto.
      </p>
      <ol className="text-[12px] text-text-dim space-y-1.5 mb-4 ml-4 list-decimal">
        <li>
          Abrí{" "}
          <a
            href="https://aistudio.google.com/app/apikey"
            target="_blank"
            rel="noopener noreferrer"
            className="text-pri underline-offset-2 hover:underline"
          >
            aistudio.google.com/app/apikey
          </a>
        </li>
        <li>Iniciá sesión con tu cuenta de Google.</li>
        <li>
          Tocá <span className="text-text">Create API key</span> → elegí un proyecto.
        </li>
        <li>Copiá la key (empieza con AIza…) y pegala abajo.</li>
      </ol>

      <label className="block text-[10px] uppercase tracking-[0.22em] text-text-dim mb-2">
        API key
      </label>
      <div className="relative">
        <input
          value={key}
          onChange={(e) => setKey(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !busy) submit();
          }}
          placeholder="AIza…"
          type="password"
          autoFocus
          disabled={busy}
          className="w-full rounded-lg bg-elevated/80 border border-white/[0.08]
                     px-3.5 h-11 text-sm font-mono placeholder-muted
                     focus:outline-none focus:border-pri/40 focus:shadow-glow-soft
                     transition-all duration-200 ease-out-expo
                     disabled:opacity-50"
        />
        <Icon
          name="shield"
          size={14}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-pri/70"
        />
      </div>

      {error && (
        <p className="mt-3 text-xs text-danger flex items-start gap-1.5">
          <Icon name="alert" size={13} className="mt-0.5 shrink-0" /> <span>{error}</span>
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
          {busy ? "Validando contra Gemini…" : "Guardar y continuar"}
        </Button>
      </div>

      <p className="mt-5 text-[11px] text-muted leading-relaxed">
        Se guarda localmente en{" "}
        <code className="text-acc/90 break-all">{status.api_keys_path}</code>.
      </p>

      {reachable === false && (
        <p className="mt-4 text-[11px] text-warn flex items-start gap-1.5">
          <Icon name="alert" size={13} className="mt-0.5 shrink-0" />
          <span>
            No estoy pudiendo contactar al backend. Si recién abriste Orion, espera unos segundos.
          </span>
        </p>
      )}
    </div>
  );
}

// ── DeepSeek setup ─────────────────────────────────────────────────────

function DeepSeekSetup({ onSaved }: { onSaved: (fresh: OnboardingStatus) => void }) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    const k = key.trim();
    if (k.length < 10) {
      setError("La API key parece demasiado corta.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // 1) Guardamos la key en providers.json
      await api.setBrainProviderKey("deepseek", k);
      // 2) Cambiamos el brain activo. Esto también desbloquea el bus si
      //    estaba esperando una key Gemini (route patch_brain → mark_ready).
      await api.setBrain("deepseek", "deepseek-chat");
      // 3) Re-leemos el status para que el wizard sepa que ya está "ready".
      const fresh = await api.onboardingStatus();
      onSaved(fresh);
    } catch (e) {
      setError(String(e).replace(/^Error:\s*/, ""));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <p className="text-sm text-text-dim leading-relaxed mb-3">
        DeepSeek-V3 es muy potente para chat y código, y muy barato. Necesitás una API key de{" "}
        <a
          href="https://platform.deepseek.com/api_keys"
          target="_blank"
          rel="noopener noreferrer"
          className="text-pri underline-offset-2 hover:underline"
        >
          platform.deepseek.com
        </a>
        .
      </p>
      <ol className="text-[12px] text-text-dim space-y-1.5 mb-4 ml-4 list-decimal">
        <li>Creá una cuenta en platform.deepseek.com (Gmail funciona).</li>
        <li>Cargá U$ 2 de saldo (es muy barato — un dólar dura semanas).</li>
        <li>
          Generá una key en <span className="text-text">API keys</span> y pegala abajo.
        </li>
      </ol>

      <label className="block text-[10px] uppercase tracking-[0.22em] text-text-dim mb-2">
        API key
      </label>
      <input
        value={key}
        onChange={(e) => setKey(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !busy) submit();
        }}
        placeholder="sk-…"
        type="password"
        autoFocus
        disabled={busy}
        className="w-full rounded-lg bg-elevated/80 border border-white/[0.08]
                   px-3.5 h-11 text-sm font-mono placeholder-muted
                   focus:outline-none focus:border-pri/40 focus:shadow-glow-soft
                   transition-all duration-200 ease-out-expo
                   disabled:opacity-50"
      />

      {error && (
        <p className="mt-3 text-xs text-danger flex items-start gap-1.5">
          <Icon name="alert" size={13} className="mt-0.5 shrink-0" /> <span>{error}</span>
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
          {busy ? "Aplicando…" : "Guardar y continuar"}
        </Button>
      </div>

      <p className="mt-5 text-[11px] text-muted leading-relaxed">
        La voz quedará desactivada porque DeepSeek no tiene API de audio en tiempo real. Si querés
        voz, agregá una key Gemini en Ajustes → Cerebro después.
      </p>
    </div>
  );
}

// ── Ollama setup ───────────────────────────────────────────────────────

function OllamaSetup({ onSaved }: { onSaved: (fresh: OnboardingStatus) => void }) {
  const [brain, setBrain] = useState<BrainState | null>(null);
  const [pollErr, setPollErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Poll de status cada 2s para detectar cuando el usuario instala Ollama
  // y/o descarga modelos sin tener que cerrar el wizard.
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      try {
        const b = await api.getBrain();
        if (!alive) return;
        setBrain(b);
        setPollErr(null);
      } catch (e) {
        if (alive) setPollErr(String(e));
      }
      if (alive) timer = setTimeout(tick, 2000);
    };
    tick();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, []);

  const ollama = brain?.ollama;
  const ollamaProvider: BrainProvider | undefined = useMemo(
    () => brain?.providers.find((p) => p.id === "ollama"),
    [brain],
  );

  const hasModel = !!ollama && ollama.running && ollama.models.length > 0;
  const defaultModel = ollama?.models[0]?.name || ollamaProvider?.default_model || "llama3.1:8b";

  async function confirm() {
    setBusy(true);
    try {
      await api.setBrain("ollama", defaultModel);
      const fresh = await api.onboardingStatus();
      onSaved(fresh);
    } catch (e) {
      setPollErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <p className="text-sm text-text-dim leading-relaxed mb-3">
        Ollama corre modelos de IA localmente en tu PC. 100% privado, sin internet, sin keys. Con 16
        GB de RAM van bien los modelos 7B-8B.
      </p>

      <ol className="text-[12px] text-text-dim space-y-2 mb-4 ml-4 list-decimal">
        <li>
          Instalá Ollama desde{" "}
          <a
            href="https://ollama.com/download"
            target="_blank"
            rel="noopener noreferrer"
            className="text-pri underline-offset-2 hover:underline"
          >
            ollama.com/download
          </a>
          . Después de instalarlo queda corriendo en background.
        </li>
        <li>
          Abrí una terminal y descargá un modelo (≈5 GB):{" "}
          <code className="font-mono text-acc">ollama pull llama3.1:8b</code>
        </li>
        <li>Esperá. Cuando el modelo esté listo, este wizard lo detecta solo.</li>
      </ol>

      {/* Status del detector */}
      <div className="p-3 rounded-lg border border-white/[0.06] bg-white/[0.02] mb-4">
        {!ollama && !pollErr && (
          <div className="text-[12px] text-text-dim flex items-center gap-2">
            <Icon name="bolt" size={13} className="animate-pulse" />
            <span>Buscando Ollama en localhost:11434…</span>
          </div>
        )}
        {ollama && !ollama.running && (
          <div className="text-[12px] text-warn flex items-start gap-2">
            <Icon name="alert" size={13} className="shrink-0 mt-0.5" />
            <span>
              Ollama no detectado en <code className="font-mono">{ollama.base_url}</code>. Instalalo
              y abrilo — esto se actualiza solo.
            </span>
          </div>
        )}
        {ollama?.running && ollama.models.length === 0 && (
          <div className="text-[12px] text-warn flex items-start gap-2">
            <Icon name="alert" size={13} className="shrink-0 mt-0.5" />
            <span>
              Ollama corriendo, pero sin modelos descargados. En una terminal corré:{" "}
              <code className="font-mono text-acc">ollama pull llama3.1:8b</code>
            </span>
          </div>
        )}
        {ollama?.running && ollama.models.length > 0 && (
          <div className="text-[12px] text-ok flex items-start gap-2">
            <Icon name="check" size={13} className="shrink-0 mt-0.5" />
            <span>Listo. Modelos detectados: {ollama.models.map((m) => m.name).join(", ")}.</span>
          </div>
        )}
        {pollErr && (
          <div className="text-[12px] text-danger flex items-start gap-2">
            <Icon name="alert" size={13} className="shrink-0 mt-0.5" />
            <span>Error consultando el backend: {pollErr}</span>
          </div>
        )}
      </div>

      <div className="flex justify-end">
        <Button
          variant="primary"
          size="md"
          iconRight="chevron-right"
          disabled={!hasModel || busy}
          loading={busy}
          onClick={confirm}
        >
          {busy ? "Aplicando…" : `Usar ${defaultModel}`}
        </Button>
      </div>

      <p className="mt-5 text-[11px] text-muted leading-relaxed">
        La voz quedará desactivada (Ollama no tiene API de audio en tiempo real). Si querés voz,
        agregá una key Gemini en Ajustes → Cerebro después.
      </p>
    </div>
  );
}

// ── Step 3: Integraciones (opcional) ───────────────────────────────────

function IntegrationsStep({ onNext }: { onNext: () => void }) {
  return (
    <div>
      <p className="text-sm text-text-dim leading-relaxed mb-4">
        Estas integraciones son <span className="text-text font-medium">opcionales</span>. Las podés
        configurar ahora o después desde el panel de Ajustes.
      </p>

      <div className="space-y-3 mb-6">
        <IntegrationCard
          icon="bell"
          title="Notificaciones de Google"
          subtitle="Gmail · Classroom · Drive · Calendar"
          description="Centraliza tu bandeja en el panel de Notificaciones. Requiere OAuth con tu cuenta de Google (5 min de setup)."
          doc="docs/SETUP_GOOGLE_OAUTH.md"
        />
        <IntegrationCard
          icon="iot"
          title="IoT en casa"
          subtitle="ESP32 · Sensores · Escenas"
          description="Controlá tus dispositivos por WiFi/MQTT. Configurable desde el panel IoT."
          doc={null}
        />
        <IntegrationCard
          icon="memory"
          title="Skills personalizadas"
          subtitle="Custom tools que tu cerebro puede invocar"
          description="Agregá habilidades nuevas en formato Markdown (.md) desde el panel Skills."
          doc={null}
        />
      </div>

      <div className="flex items-center justify-between">
        <p className="text-[11px] text-muted">Listo para usar Orion ahora mismo.</p>
        <Button variant="primary" size="md" iconRight="chevron-right" onClick={onNext}>
          Continuar
        </Button>
      </div>
    </div>
  );
}

function IntegrationCard({
  icon,
  title,
  subtitle,
  description,
  doc,
}: {
  icon: IconName;
  title: string;
  subtitle: string;
  description: string;
  doc: string | null;
}) {
  return (
    <div className="flex items-start gap-3 p-3 rounded-lg border border-white/[0.06] bg-white/[0.02]">
      <span className="grid place-items-center h-9 w-9 rounded-md bg-pri/10 text-pri shrink-0">
        <Icon name={icon} size={16} />
      </span>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-text">{title}</div>
        <div className="text-[11px] text-muted mb-1">{subtitle}</div>
        <p className="text-[12px] text-text-dim leading-relaxed">{description}</p>
        {doc && (
          <p className="mt-1.5 text-[11px] text-muted">
            Guía: <code className="text-acc/90">{doc}</code>
          </p>
        )}
      </div>
    </div>
  );
}

// ── Step 4: Done ───────────────────────────────────────────────────────

function DoneStep({ onClose }: { onClose: () => void }) {
  return (
    <div>
      <div className="grid place-items-center h-14 w-14 mx-auto mb-5 rounded-full bg-pri/15 text-pri animate-scale-in">
        <Icon name="check" size={26} />
      </div>
      <h3 className="text-center text-base font-medium text-text mb-2">Listo para arrancar</h3>
      <p className="text-center text-sm text-text-dim leading-relaxed mb-5">
        Podés escribir en el panel de Chat o tocar el orbe central para hablar por voz (si elegiste
        Gemini).
      </p>
      <ul className="text-[12px] text-text-dim space-y-1.5 mb-6 ml-4 list-disc">
        <li>
          <span className="text-text">Ctrl+K</span> abre la paleta de comandos.
        </li>
        <li>
          <span className="text-text">Ajustes → Cerebro</span> cambia el motor LLM cuando quieras.
        </li>
        <li>
          <span className="text-text">Skills</span> te permite agregar habilidades nuevas.
        </li>
      </ul>
      <div className="flex justify-center">
        <Button variant="primary" size="md" icon="check" onClick={onClose}>
          Empezar a usar Orion
        </Button>
      </div>
    </div>
  );
}
