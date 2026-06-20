/**
 * AgentEditorModal — crear / editar / borrar un agente.
 *
 * Reutilizado tanto para "Crear" (con `newDraft` pre-rellenado por el
 * padre) como para "Editar" (con `agent` real). El estado local de la
 * forma se inicializa desde `agent ?? newDraft`.
 *
 * Acciones:
 *   - Guardar → POST /api/orchestra (create) o PATCH (update). Elimina
 *     `id` del patch (no se reasigna por update).
 *   - Eliminar → confirm two-step + DELETE /api/orchestra/{id}.
 *   - Fallback collapsible: opcional, para definir provider/model
 *     alternativo si el principal no responde.
 */

import { useMemo, useState } from "react";

import { api, type AgentSpec, type OrchestraAgent, type ProviderCatalog } from "@/api/rest";
import { Icon, type IconName } from "@/ui/Icon";
import { Button, Modal, Switch } from "@/ui/primitives";

const inputCls = [
  "w-full px-3 h-9 text-sm rounded-md bg-surface border border-white/[0.08]",
  "focus:outline-none focus:border-pri/50 focus:shadow-glow-soft",
  "placeholder-muted transition-colors",
].join(" ");

const ICONS: { id: string; label: string }[] = [
  { id: "sparkles", label: "Sparkles" },
  { id: "search", label: "Buscar" },
  { id: "code", label: "Código" },
  { id: "sigma", label: "Sigma" },
  { id: "feather", label: "Pluma" },
  { id: "chart", label: "Gráfico" },
  { id: "folder", label: "Carpeta" },
  { id: "sensors", label: "Sensor" },
  { id: "compass", label: "Brújula" },
];

interface Props {
  agent: OrchestraAgent | null;
  isNew: boolean;
  newDraft: OrchestraAgent | null;
  providers: ProviderCatalog[];
  onClose: () => void;
  onSaved: () => void;
  onError: (e: string) => void;
}

export function AgentEditorModal({
  agent,
  isNew,
  newDraft,
  providers,
  onClose,
  onSaved,
  onError,
}: Props) {
  const creating = isNew && !!newDraft;
  const show = !!agent || creating;
  const effectiveAgent = agent ?? newDraft;

  const [id, setId] = useState(effectiveAgent?.id ?? "");
  const [role, setRole] = useState(effectiveAgent?.role ?? "");
  const [icon, setIcon] = useState(effectiveAgent?.icon ?? "sparkles");
  const [description, setDesc] = useState(effectiveAgent?.description ?? "");
  const [provider, setProvider] = useState(effectiveAgent?.provider ?? "gemini");
  const [model, setModel] = useState(effectiveAgent?.model ?? "");
  const [temperature, setTemp] = useState(effectiveAgent?.temperature ?? 0.7);
  const [tools, setTools] = useState((effectiveAgent?.tools ?? []).join(", "));
  const [system, setSystem] = useState(effectiveAgent?.system ?? "");
  const [enabled, setEnabled] = useState(effectiveAgent?.enabled ?? true);
  const [fallbackProvider, setFbP] = useState(effectiveAgent?.fallback_provider ?? "");
  const [fallbackModel, setFbM] = useState(effectiveAgent?.fallback_model ?? "");
  const [showFallback, setShowFb] = useState(!!effectiveAgent?.fallback_provider);

  const [busy, setBusy] = useState(false);
  const [deleteConfirm, setDelConf] = useState(false);

  // Suggested models from the selected provider
  const suggestedModels = useMemo(() => {
    const p = providers.find((p) => p.id === provider);
    return p?.models ?? [];
  }, [provider, providers]);

  async function save() {
    if (!id || !provider || !model) return;
    setBusy(true);
    try {
      const spec: AgentSpec = {
        id,
        role,
        icon,
        description,
        provider,
        model,
        temperature,
        tools: tools
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        system,
        enabled,
        fallback_provider: fallbackProvider || undefined,
        fallback_model: fallbackModel || undefined,
      };
      if (creating) {
        await api.createAgent(spec);
      } else {
        const patch = { ...spec };
        delete patch.id;
        await api.updateAgent(agent!.id, patch);
      }
      onSaved();
    } catch (e) {
      onError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!agent) return;
    setBusy(true);
    try {
      await api.deleteAgent(agent.id);
      onSaved();
    } catch (e) {
      onError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={show}
      onClose={onClose}
      title={creating ? "Nuevo agente" : `Editar: ${agent?.role ?? agent?.id}`}
      eyebrow="Orquesta"
      size="lg"
      footer={
        <div className="flex items-center justify-between w-full gap-2">
          <div>
            {!creating && !deleteConfirm && (
              <Button variant="danger" size="sm" icon="trash" onClick={() => setDelConf(true)}>
                Eliminar
              </Button>
            )}
            {deleteConfirm && (
              <span className="flex items-center gap-2">
                <span className="text-xs text-danger">¿Seguro?</span>
                <Button variant="danger" size="sm" onClick={remove} loading={busy}>
                  Sí
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setDelConf(false)}>
                  No
                </Button>
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={onClose}>
              Cancelar
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={save}
              loading={busy}
              disabled={!id || !provider || !model}
            >
              {creating ? "Crear" : "Guardar"}
            </Button>
          </div>
        </div>
      }
    >
      <div className="space-y-4">
        {/* ID + Role */}
        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="text-[10px] uppercase tracking-[0.18em] text-muted">
              ID (snake_case)
            </span>
            <input
              className={inputCls}
              value={id}
              onChange={(e) => setId(e.target.value)}
              placeholder="mi_agente"
              disabled={!creating}
            />
          </label>
          <label className="block">
            <span className="text-[10px] uppercase tracking-[0.18em] text-muted">Nombre / Rol</span>
            <input
              className={inputCls}
              value={role}
              onChange={(e) => setRole(e.target.value)}
              placeholder="Matemático"
            />
          </label>
        </div>

        {/* Description */}
        <label className="block">
          <span className="text-[10px] uppercase tracking-[0.18em] text-muted">Descripción</span>
          <input
            className={inputCls}
            value={description}
            onChange={(e) => setDesc(e.target.value)}
            placeholder="Qué hace este agente…"
          />
        </label>

        {/* Icon picker */}
        <div>
          <span className="text-[10px] uppercase tracking-[0.18em] text-muted block mb-2">
            Icono
          </span>
          <div className="flex flex-wrap gap-1.5">
            {ICONS.map((ic) => (
              <button
                key={ic.id}
                onClick={() => setIcon(ic.id)}
                title={ic.label}
                className={`h-8 w-8 grid place-items-center rounded-lg border transition-all ${
                  icon === ic.id
                    ? "bg-pri/15 border-pri/40 text-pri shadow-glow-soft"
                    : "border-white/[0.06] text-text-dim hover:border-white/[0.14] hover:text-text"
                }`}
              >
                <Icon name={ic.id as IconName} size={14} />
              </button>
            ))}
          </div>
        </div>

        {/* Provider + Model */}
        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="text-[10px] uppercase tracking-[0.18em] text-muted">Proveedor</span>
            <select
              className={inputCls}
              value={provider}
              onChange={(e) => {
                setProvider(e.target.value);
                setModel("");
              }}
            >
              {providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label} {p.free ? "(gratis)" : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-[10px] uppercase tracking-[0.18em] text-muted">Modelo</span>
            <input
              className={inputCls}
              value={model}
              onChange={(e) => setModel(e.target.value)}
              list="suggested-models"
              placeholder="gemini-2.5-flash"
            />
            <datalist id="suggested-models">
              {suggestedModels.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </datalist>
          </label>
        </div>

        {/* Temperature slider */}
        <label className="block">
          <div className="flex items-baseline justify-between mb-1.5">
            <span className="text-[10px] uppercase tracking-[0.18em] text-muted">Temperatura</span>
            <span className="text-[10px] font-mono text-acc">{temperature.toFixed(1)}</span>
          </div>
          <input
            type="range"
            min="0"
            max="2"
            step="0.1"
            value={temperature}
            onChange={(e) => setTemp(parseFloat(e.target.value))}
            className="w-full accent-pri h-2"
          />
          <div className="flex justify-between text-[9px] text-muted mt-0.5">
            <span>Preciso (0)</span>
            <span>Creativo (2)</span>
          </div>
        </label>

        {/* Tools */}
        <label className="block">
          <span className="text-[10px] uppercase tracking-[0.18em] text-muted">
            Tools (* = todas)
          </span>
          <input
            className={inputCls}
            value={tools}
            onChange={(e) => setTools(e.target.value)}
            placeholder="web_search, file_controller"
          />
        </label>

        {/* System prompt */}
        <label className="block">
          <span className="text-[10px] uppercase tracking-[0.18em] text-muted">System prompt</span>
          <textarea
            className={`${inputCls} min-h-[80px] resize-y`}
            value={system}
            onChange={(e) => setSystem(e.target.value)}
            rows={3}
            placeholder="Eres el Matemático de O.R.I.O.N…"
          />
        </label>

        {/* Enabled */}
        <div className="flex items-center justify-between">
          <div>
            <span className="text-sm text-text">Habilitado</span>
            <p className="text-[11px] text-text-dim">
              Si está deshabilitado, no aparece en la orquesta
            </p>
          </div>
          <Switch on={enabled} onClick={() => setEnabled((v) => !v)} />
        </div>

        {/* Fallback (collapsible) */}
        <div className="border-t border-white/[0.06] pt-4">
          <button
            onClick={() => setShowFb((v) => !v)}
            className="flex items-center gap-2 text-xs text-text-dim hover:text-text transition-colors"
          >
            <Icon name={showFallback ? "arrow-down" : "arrow-right"} size={12} />
            Fallback (opcional)
          </button>
          {showFallback && (
            <div className="grid grid-cols-2 gap-3 mt-3">
              <label className="block">
                <span className="text-[10px] uppercase tracking-[0.18em] text-muted">
                  Proveedor alternativo
                </span>
                <input
                  className={inputCls}
                  value={fallbackProvider}
                  onChange={(e) => setFbP(e.target.value)}
                  placeholder="openrouter"
                />
              </label>
              <label className="block">
                <span className="text-[10px] uppercase tracking-[0.18em] text-muted">
                  Modelo alternativo
                </span>
                <input
                  className={inputCls}
                  value={fallbackModel}
                  onChange={(e) => setFbM(e.target.value)}
                  placeholder="deepseek/deepseek-r1:free"
                />
              </label>
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
