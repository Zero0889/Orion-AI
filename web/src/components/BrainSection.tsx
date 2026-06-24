/**
 * BrainSection — selector del "cerebro" del chat principal.
 *
 * El chat principal puede correr en Gemini Live (modo voz incluido) o en
 * cualquier proveedor OpenAI-compat (DeepSeek, Ollama local/cloud, OpenRouter,
 * Groq, OpenAI, Mistral). Este panel es donde el usuario elige cuál.
 *
 * El voz es Gemini fijo: si el usuario elige otro cerebro, mostramos un
 * aviso explicando que la voz se desactiva pero igual puede agregar una
 * key de Gemini en el switch para reactivarla.
 *
 * Patrón TanStack Query (igual que el resto del SettingsPanel): una sola
 * query a /api/settings/brain trae el snapshot completo (activo +
 * catálogo + ollama + gemini status). Las mutations invalidan la query
 * y el bridge WS también lo hace cuando llega settings.brain.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { api, type BrainProvider, type BrainState, type BrainTestResult } from "@/api/rest";
import { QUERY_KEYS } from "@/query/keys";
import { toast } from "@/stores/toast";
import { Icon } from "@/ui/Icon";
import { Badge, Button, Surface } from "@/ui/primitives";

export function BrainSection() {
  const qc = useQueryClient();
  const { data, error, isLoading } = useQuery<BrainState>({
    queryKey: QUERY_KEYS.settingsBrain,
    queryFn: () => api.getBrain(),
  });

  // ── Estado local del editor (no se persiste hasta que el usuario aplica)
  // Lo inicializamos con el activo de la query y lo dejamos en sync via
  // useEffect cada vez que cambia el snapshot.
  const [provider, setProvider] = useState<string>("");
  const [model, setModel] = useState<string>("");
  const [keyDraft, setKeyDraft] = useState<string>("");
  const [showKey, setShowKey] = useState(false);
  const [testResult, setTestResult] = useState<BrainTestResult | null>(null);

  useEffect(() => {
    if (!data) return;
    setProvider((p) => p || data.active.provider);
    setModel((m) => m || data.active.model);
    // Cada vez que cambia el provider activo limpiamos el draft de la key
    // y el testResult — son del provider anterior.
    setKeyDraft("");
    setTestResult(null);
  }, [data?.active.provider, data?.active.model]); // eslint-disable-line react-hooks/exhaustive-deps

  const selectedProvider: BrainProvider | undefined = useMemo(() => {
    if (!data) return undefined;
    return data.providers.find((p) => p.id === provider);
  }, [data, provider]);

  // Cuando el usuario cambia de provider en el dropdown, pre-elegimos su
  // default_model si lo conocemos y reseteamos el draft de key.
  function onPickProvider(next: string) {
    setProvider(next);
    setKeyDraft("");
    setTestResult(null);
    const meta = data?.providers.find((p) => p.id === next);
    if (meta) {
      // Si el modelo actual no existe para este provider, switcheamos al default.
      const exists = meta.models.some((m) => m.id === model);
      if (!exists) setModel(meta.default_model || meta.models[0]?.id || "");
    }
  }

  // ── Mutations
  const applyBrain = useMutation({
    mutationFn: () => api.setBrain(provider, model),
    onSuccess: () => {
      toast.success(
        "Cerebro actualizado",
        `${selectedProvider?.label ?? provider} / ${model} aplicado al instante.`,
      );
      qc.invalidateQueries({ queryKey: QUERY_KEYS.settingsBrain });
    },
    onError: (e) => toast.error("No pude cambiar el cerebro", String(e)),
  });

  const saveKey = useMutation({
    mutationFn: () => api.setBrainProviderKey(provider, keyDraft),
    onSuccess: (res) => {
      toast.success(
        res.configured ? "API key guardada" : "API key borrada",
        res.configured
          ? "El provider quedó disponible para usarse al instante."
          : "Eliminé la entrada de providers.json.",
      );
      setKeyDraft("");
      qc.invalidateQueries({ queryKey: QUERY_KEYS.settingsBrain });
    },
    onError: (e) => toast.error("No pude guardar la key", String(e)),
  });

  const runTest = useMutation({
    mutationFn: () => api.testBrain(provider, model),
    onSuccess: (res) => setTestResult(res),
    onError: (e) => setTestResult({ ok: false, error: String(e), actionable: false }),
  });

  if (isLoading) {
    return (
      <Section title="Cerebro">
        <div className="space-y-3">
          <div className="skeleton h-24" />
          <div className="skeleton h-32" />
        </div>
      </Section>
    );
  }
  if (error || !data) {
    return (
      <Section title="Cerebro">
        <div className="p-3 rounded-md border border-danger/30 bg-danger/10 text-xs text-danger">
          No pude leer el cerebro. {String(error ?? "")}
        </div>
      </Section>
    );
  }

  const active = data.active;
  const isOllama = provider === "ollama";
  const isGemini = provider === "gemini";
  const ollama = data.ollama;
  const dirtyBrain = provider !== active.provider || model !== active.model;

  return (
    <Section title="Cerebro">
      <p className="text-xs text-text-dim/80 mb-4 leading-relaxed">
        Elegí qué motor LLM contesta en el chat principal. La voz "Hey Orion" sigue siendo Gemini
        Live siempre (es la única API que soporta audio bidireccional en tiempo real). Si el cerebro
        no es Gemini, el chat de texto pasa por el provider elegido — historial, tools y notas se
        comparten igual.
      </p>

      {/* Card del cerebro activo */}
      <Surface level={2} className="p-4 mb-4">
        <div className="flex items-start gap-4">
          <div className="grid place-items-center h-11 w-11 rounded-xl bg-pri/15 text-pri shrink-0">
            <Icon name="orbit" size={20} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h4 className="text-sm font-semibold text-text">Cerebro activo</h4>
              <Badge tone={active.is_live ? "info" : "warn"} dot>
                {active.is_live ? "Gemini Live" : "Chat solo texto"}
              </Badge>
              {active.is_live && data.gemini.configured && (
                <Badge tone="success" dot>
                  Voz activa
                </Badge>
              )}
              {active.is_live && !data.gemini.configured && (
                <Badge tone="warn" dot>
                  Falta key Gemini
                </Badge>
              )}
            </div>
            <p className="text-xs text-text-dim leading-relaxed mt-1">
              <code className="text-acc font-mono">{active.provider}</code> · modelo{" "}
              <code className="text-acc font-mono">{active.model}</code>
            </p>
          </div>
        </div>
      </Surface>

      {/* Selector de provider/model */}
      <Surface level={2} className="p-4 mb-4 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label="Proveedor">
            <select
              value={provider}
              onChange={(e) => onPickProvider(e.target.value)}
              className={inputCls}
            >
              {data.providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                  {p.free ? " · free tier" : ""}
                  {p.available ? " ✓" : ""}
                </option>
              ))}
            </select>
            {selectedProvider && (
              <p className="text-[10px] text-text-dim mt-1.5 leading-snug">
                {selectedProvider.auth_hint}
              </p>
            )}
          </Field>

          <Field label="Modelo">
            <select value={model} onChange={(e) => setModel(e.target.value)} className={inputCls}>
              {selectedProvider?.models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
              {/* Permitimos que el usuario tipee un modelo no listado
                  cuando es Ollama local — los nombres dependen de lo
                  que el usuario tenga descargado. */}
              {isOllama &&
                ollama.models.map((m) => (
                  <option key={`ol-${m.name}`} value={m.name}>
                    {m.name} (descargado)
                  </option>
                ))}
            </select>
            {isOllama && (
              <p className="text-[10px] text-text-dim mt-1.5 leading-snug">
                ¿Modelo distinto? Tipealo en{" "}
                <button
                  type="button"
                  className="underline hover:text-text"
                  onClick={() => {
                    const m = prompt("Nombre exacto del modelo (ej: qwen2.5:7b)");
                    if (m && m.trim()) setModel(m.trim());
                  }}
                >
                  modo manual
                </button>
                .
              </p>
            )}
          </Field>
        </div>

        {/* Status del provider seleccionado */}
        {selectedProvider && (
          <div className="flex items-center gap-2 text-[11px]">
            <Icon
              name={selectedProvider.available ? "check" : "alert"}
              size={12}
              className={selectedProvider.available ? "text-ok" : "text-warn"}
            />
            <span className={selectedProvider.available ? "text-ok" : "text-warn"}>
              {selectedProvider.available
                ? "Disponible y listo para usarse"
                : isOllama
                  ? "Ollama no detectado en localhost:11434 — instalalo abajo"
                  : "Falta API key — agregala abajo y guardá"}
            </span>
          </div>
        )}

        <div className="flex items-center justify-end gap-2 pt-2 border-t border-white/[0.05]">
          <Button
            variant="secondary"
            size="sm"
            icon="bolt"
            onClick={() => runTest.mutate()}
            disabled={runTest.isPending || !selectedProvider?.available}
            title={
              !selectedProvider?.available
                ? "Configura primero el provider"
                : "Manda 'pong' al modelo y verifica conectividad"
            }
          >
            {runTest.isPending ? "Probando…" : "Probar"}
          </Button>
          <Button
            variant="primary"
            size="sm"
            icon="check"
            onClick={() => applyBrain.mutate()}
            disabled={applyBrain.isPending || !dirtyBrain || !provider || !model}
          >
            {applyBrain.isPending ? "Aplicando…" : "Aplicar"}
          </Button>
        </div>

        {testResult && (
          <div
            className={[
              "text-[11px] leading-relaxed p-2.5 rounded-md border font-mono",
              testResult.ok
                ? "text-ok      border-ok/30    bg-ok/5"
                : "text-danger  border-danger/30 bg-danger/5",
            ].join(" ")}
          >
            {testResult.ok
              ? `✓ ${testResult.provider}/${testResult.model} respondió: "${testResult.text}"`
              : `× ${testResult.error}`}
          </div>
        )}
      </Surface>

      {/* API key del provider seleccionado (excepto Ollama local) */}
      {selectedProvider?.needs_key && (
        <Surface level={2} className="p-4 mb-4">
          <div className="text-[11px] uppercase tracking-[0.18em] text-text-dim mb-2">
            API key — {selectedProvider.label}
          </div>
          <p className="text-xs text-text-dim/80 mb-3 leading-relaxed">
            {selectedProvider.available
              ? "Ya hay una key guardada. Podés sobrescribirla con una nueva o borrarla."
              : "Pegá tu API key del proveedor para activar el chat con este cerebro."}
          </p>
          <div className="flex items-center gap-2">
            <input
              type={showKey ? "text" : "password"}
              value={keyDraft}
              onChange={(e) => setKeyDraft(e.target.value)}
              placeholder={
                selectedProvider.available
                  ? "(key actual oculta — pegá una nueva para reemplazarla)"
                  : "sk-..."
              }
              className={`${inputCls} flex-1 font-mono text-xs`}
              spellCheck={false}
            />
            <button
              type="button"
              onClick={() => setShowKey((v) => !v)}
              className="px-2 h-9 text-[11px] text-text-dim hover:text-text rounded-md border border-white/[0.08] hover:border-white/[0.18]"
              title={showKey ? "Ocultar key" : "Mostrar key"}
            >
              {showKey ? "Ocultar" : "Ver"}
            </button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => saveKey.mutate()}
              disabled={saveKey.isPending || !keyDraft.trim()}
            >
              {saveKey.isPending ? "Guardando…" : "Guardar"}
            </Button>
            {selectedProvider.available && (
              <Button
                variant="ghost"
                size="sm"
                icon="close"
                onClick={() => {
                  if (confirm(`¿Borrar la key de ${selectedProvider.label} de providers.json?`)) {
                    api
                      .setBrainProviderKey(provider, "")
                      .then(() => {
                        toast.warn("Key borrada");
                        qc.invalidateQueries({
                          queryKey: QUERY_KEYS.settingsBrain,
                        });
                      })
                      .catch((e) => toast.error("Error", String(e)));
                  }
                }}
              >
                Borrar
              </Button>
            )}
          </div>
        </Surface>
      )}

      {/* Detector de Ollama */}
      {isOllama && <OllamaCard ollama={ollama} />}

      {/* Aviso sobre voz cuando no es Gemini */}
      {!isGemini && (
        <div className="mt-3 flex items-start gap-2.5 p-3 rounded-md border border-warn/30 bg-warn/5">
          <Icon name="mic" size={14} className="text-warn shrink-0 mt-0.5" />
          <div className="text-[11px] text-warn leading-relaxed">
            La voz en tiempo real exige Gemini Live (DeepSeek/Ollama no tienen API equivalente). Si
            querés voz, agregá una API key de Gemini en{" "}
            <code className="font-mono">config/api_keys.json</code> o en la pestaña de Voz — el chat
            puede seguir usando este cerebro y la voz arranca aparte.
          </div>
        </div>
      )}
    </Section>
  );
}

/* ── Sub-componentes ─────────────────────────────────────────────────── */

function OllamaCard({ ollama }: { ollama: BrainState["ollama"] }) {
  if (ollama.running) {
    return (
      <Surface level={2} className="p-4 mb-3">
        <div className="flex items-center gap-2 mb-2">
          <Badge tone="success" dot>
            Ollama corriendo
          </Badge>
          <code className="text-[10px] font-mono text-text-dim">{ollama.base_url}</code>
        </div>
        <div className="text-[11px] text-text-dim">
          {ollama.models.length === 0 ? (
            <>
              No tenés modelos descargados todavía. En una terminal corré:{" "}
              <code className="font-mono text-acc">ollama pull llama3.1:8b</code>
            </>
          ) : (
            <>Modelos descargados: {ollama.models.map((m) => m.name).join(", ")}</>
          )}
        </div>
      </Surface>
    );
  }
  return (
    <Surface level={2} className="p-4 mb-3 border-warn/30 bg-warn/5">
      <div className="flex items-start gap-2.5">
        <Icon name="alert" size={14} className="text-warn shrink-0 mt-0.5" />
        <div className="text-[11px] text-warn leading-relaxed space-y-2">
          <div>
            <strong>Ollama no detectado</strong> en{" "}
            <code className="font-mono">{ollama.base_url}</code>. Pasos:
          </div>
          <ol className="list-decimal pl-4 space-y-1">
            <li>
              Descargá Ollama:{" "}
              <a
                href="https://ollama.com/download"
                target="_blank"
                rel="noopener noreferrer"
                className="underline"
              >
                ollama.com/download
              </a>
            </li>
            <li>Ejecutalo (se queda corriendo como servicio en background).</li>
            <li>
              Descargá un modelo: <code className="font-mono">ollama pull llama3.1:8b</code> (≈5
              GB).
            </li>
            <li>Refrescá esta pestaña.</li>
          </ol>
          <div className="text-text-dim text-[10px]">
            Con 16 GB de RAM corren bien los modelos 7B-8B. Modelos 13B+ ya empiezan a tirar swap.
          </div>
        </div>
      </div>
    </Surface>
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-[10px] uppercase tracking-[0.18em] text-text-dim mb-1.5 block">
        {label}
      </span>
      {children}
    </label>
  );
}

const inputCls =
  "w-full h-9 px-3 rounded-md bg-elevated border border-white/[0.08] " +
  "text-sm text-text focus:border-pri/50 focus:outline-none transition-colors";
