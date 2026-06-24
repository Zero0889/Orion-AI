/**
 * Onboarding — wizard multipaso para primer arranque.
 *
 * Steps:
 *   0. Welcome        — que es Orion y que necesita.
 *   1. Gemini API key — REQUIRED. Valida contra Gemini antes de persistir.
 *   2. Integraciones  — OPTIONAL. Explica Google OAuth + link a guia.
 *   3. Done           — quick start.
 *
 * Solo el paso 1 es obligatorio para desbloquear el modal. Los demas se
 * pueden saltear y configurar despues desde Ajustes.
 */

import { useEffect, useRef, useState } from "react";

import { api, type OnboardingStatus } from "@/api/rest";
import { useOrionStore } from "@/stores/orion";
import { Icon, type IconName } from "@/ui/Icon";
import { Button } from "@/ui/primitives";

const STATUS_POLL_MS = 1500;

type Step = 0 | 1 | 2 | 3;

export function Onboarding() {
  const setConfigured = useOrionStore((s) => s.setApiKeyConfigured);

  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [reachable, setReachable] = useState<boolean | null>(null);
  const [step, setStep] = useState<Step>(0);
  // Flag explicito: el usuario llego al final del wizard y lo dismisseo.
  // Hace falta porque no podemos depender solo de status.ready (la key
  // puede haber estado seteada desde antes y entonces el modal nunca se
  // mostraria).
  const [dismissed, setDismissed] = useState(false);

  // Auto-jump al paso 2 si el backend ya tiene API key cuando el wizard se
  // monta (caso env var). Lo hacemos UNA SOLA VEZ via ref para no pisar al
  // usuario que va avanzando manualmente.
  const initialJumpDoneRef = useRef(false);

  // Poll del status del backend mientras el modal este montado.
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      try {
        const s = await api.onboardingStatus();
        if (!alive) return;
        setStatus(s);
        setReachable(true);
        if (s.ready && !initialJumpDoneRef.current) {
          // Primera vez que detectamos ready=true: si la key venia ya
          // configurada (env var), saltamos a Integraciones. Si el user
          // la pego en el paso 1, este branch tambien dispara pero como
          // GeminiStep ya hizo setStep(2), el setStep aca es idempotente.
          initialJumpDoneRef.current = true;
          setConfigured(true);
          setStep((cur) => (cur < 2 ? 2 : cur));
        }
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
  }, [setConfigured]);

  // Modal cerrado si:
  //   - el usuario clickeo "Empezar a usar Orion" en el ultimo paso, o
  //   - todavia no sabemos el status (primer fetch en curso).
  if (dismissed) return null;
  if (!status) return null;

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-bg/80 backdrop-blur-md animate-fade-in">
      <div className="absolute h-[480px] w-[480px] rounded-full bg-pri/15 blur-3xl pointer-events-none animate-halo" />

      <div className="relative w-full max-w-lg surface-glass rounded-2xl p-7 shadow-lift animate-scale-in">
        <Header step={step} />

        {step === 0 && <WelcomeStep onNext={() => setStep(1)} />}
        {step === 1 && (
          <GeminiStep
            status={status}
            reachable={reachable}
            onSaved={(fresh) => {
              setStatus(fresh);
              setConfigured(true);
              setStep(2);
            }}
          />
        )}
        {step === 2 && <IntegrationsStep onNext={() => setStep(3)} />}
        {step === 3 && (
          <DoneStep
            onClose={() => {
              setConfigured(true);
              setDismissed(true);
            }}
          />
        )}
        {/* Marca de version del wizard. Util cuando el .msi se reinstala
            sobre una version vieja y queremos verificar a simple vista que
            el bundle nuevo si cargo. */}
        <div className="mt-4 text-center text-[9px] uppercase tracking-[0.18em] text-muted/60">
          Wizard v0.1.1
        </div>
      </div>
    </div>
  );
}

// ── Header ─────────────────────────────────────────────────────────────

function Header({ step }: { step: Step }) {
  const labels = ["Bienvenida", "Gemini", "Google", "Listo"];
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
          <div className="text-[10px] uppercase tracking-[0.24em] text-pri/80">Configura Orion</div>
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
        Orion es un asistente personal con voz, vision y control de tu PC. Funciona localmente
        usando Gemini Live como cerebro.
      </p>
      <ul className="space-y-2 mb-6 text-[13px] text-text-dim">
        <li className="flex items-start gap-2">
          <Icon name="check" size={13} className="text-pri mt-0.5 shrink-0" />
          <span>
            Charlar por voz en tiempo real, abrir apps, leer notas, controlar IoT en casa.
          </span>
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
        Para empezar solo necesitas una API key de Gemini (gratis). Las integraciones con Google son
        opcionales y se configuran despues.
      </p>
      <div className="flex justify-end">
        <Button variant="primary" size="md" iconRight="chevron-right" onClick={onNext}>
          Empezar
        </Button>
      </div>
    </div>
  );
}

// ── Step 1: Gemini ─────────────────────────────────────────────────────

function GeminiStep({
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
        setError(r.message || "Algo fallo guardando la API key.");
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
          Abri{" "}
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
          Tocá <span className="text-text">Create API key</span> → elegí un proyecto (o crea uno
          nuevo).
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
        <code className="text-acc/90 break-all">{status.api_keys_path}</code>. Si preferis usar la
        variable <code className="text-acc/90">ORION_GEMINI_KEY</code>, cerra esta ventana, seteala
        y reinicia.
      </p>

      {reachable === false && (
        <p className="mt-4 text-[11px] text-warn flex items-start gap-1.5">
          <Icon name="alert" size={13} className="mt-0.5 shrink-0" />
          <span>
            No estoy pudiendo contactar al backend. Si recien abriste Orion, espera unos segundos.
          </span>
        </p>
      )}
    </div>
  );
}

// ── Step 2: Integraciones (opcional) ────────────────────────────────────

function IntegrationsStep({ onNext }: { onNext: () => void }) {
  return (
    <div>
      <p className="text-sm text-text-dim leading-relaxed mb-4">
        Estas integraciones son <span className="text-text font-medium">opcionales</span>. Las podes
        configurar ahora o despues desde el panel de Ajustes.
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
          subtitle="Custom tools que Gemini puede invocar"
          description="Agregá habilidades nuevas en formato Markdown (.md) desde el panel Skills."
          doc={null}
        />
      </div>

      <div className="flex items-center justify-between">
        <p className="text-[11px] text-muted">Estas listo para usar Orion ahora mismo.</p>
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
            Guia: <code className="text-acc/90">{doc}</code>
          </p>
        )}
      </div>
    </div>
  );
}

// ── Step 3: Done ────────────────────────────────────────────────────────

function DoneStep({ onClose }: { onClose: () => void }) {
  return (
    <div>
      <div className="grid place-items-center h-14 w-14 mx-auto mb-5 rounded-full bg-pri/15 text-pri animate-scale-in">
        <Icon name="check" size={26} />
      </div>
      <h3 className="text-center text-base font-medium text-text mb-2">Listo para arrancar</h3>
      <p className="text-center text-sm text-text-dim leading-relaxed mb-5">
        Podes hablarle a Orion por voz tocando el orbe central, o escribir desde el panel de Chat.
      </p>
      <ul className="text-[12px] text-text-dim space-y-1.5 mb-6 ml-4 list-disc">
        <li>
          <span className="text-text">Ctrl+K</span> abre la paleta de comandos.
        </li>
        <li>
          <span className="text-text">Ajustes</span> tiene tema, atajos y deps externas.
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
