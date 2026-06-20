/**
 * CuratedTab — listado de recipes oficiales no presentes en el registry.
 *
 * Los servers oficiales de Anthropic (Filesystem, Git, Memory, …) viven
 * en su monorepo en lugar del registry público. ORION mantiene un
 * catálogo curado (`api.mcpRecipes()`) con las recipes y este tab las
 * muestra agrupadas por categoría. Click en "Instalar" abre el modal
 * de install que pide los prompts/env vars de la recipe.
 */

import { useEffect, useState } from "react";

import { api, type MCPRecipe, type MCPRecipeCategory, type MCPServerBody } from "@/api/rest";
import { Icon, type IconName } from "@/ui/Icon";
import { Badge, Button, Field, Modal, Surface, TextInput } from "@/ui/primitives";

import { StarBadge } from "./StarBadge";

const CATEGORY_LABEL: Record<MCPRecipeCategory, string> = {
  files: "Archivos",
  dev: "Desarrollo",
  web: "Web / búsqueda",
  ai: "Inteligencia",
  system: "Sistema",
};

const CATEGORY_ICON: Record<MCPRecipeCategory, IconName> = {
  files: "save",
  dev: "cpu",
  web: "search",
  ai: "sparkles",
  system: "bolt",
};

interface Props {
  installedIds: Set<string>;
  onInstalled: () => void;
  onError: (msg: string) => void;
}

export function CuratedTab({ installedIds, onInstalled, onError }: Props) {
  const [recipes, setRecipes] = useState<MCPRecipe[]>([]);
  const [loading, setLoading] = useState(true);
  const [installing, setInstalling] = useState<MCPRecipe | undefined>(undefined);

  useEffect(() => {
    let alive = true;
    api
      .mcpRecipes()
      .then((data) => {
        if (alive) setRecipes(data);
      })
      .catch((e) => {
        if (alive) onError(String(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [onError]);

  // Agrupar por categoría
  const grouped = recipes.reduce<Record<string, MCPRecipe[]>>((acc, r) => {
    (acc[r.category] ||= []).push(r);
    return acc;
  }, {});

  return (
    <>
      <section className="p-6 flex flex-col gap-6">
        <div
          className="flex items-start gap-2 p-3 rounded-md
                        border border-acc/20 bg-acc/[0.04] text-xs text-text-dim"
        >
          <Icon name="info" size={14} className="mt-0.5 shrink-0 text-acc" />
          <div>
            Los servers oficiales de Anthropic (Filesystem, Git, Memory…) NO están en el registry —
            viven en su monorepo. Los curamos acá para instalarlos con un click.
          </div>
        </div>

        {loading ? (
          <div className="text-xs text-text-dim">Cargando…</div>
        ) : (
          (Object.keys(grouped) as MCPRecipeCategory[]).map((cat) => (
            <div key={cat} className="flex flex-col gap-2">
              <div
                className="flex items-center gap-2 text-[11px] uppercase
                              tracking-[0.18em] text-pri/80"
              >
                <Icon name={CATEGORY_ICON[cat]} size={12} />
                {CATEGORY_LABEL[cat]}
                <span className="text-text-dim normal-case tracking-normal">
                  · {grouped[cat].length}
                </span>
              </div>
              <ul className="flex flex-col gap-2">
                {grouped[cat].map((r) => (
                  <RecipeCard
                    key={r.recipe_id}
                    recipe={r}
                    alreadyInstalled={installedIds.has(r.suggested_id)}
                    onInstall={() => setInstalling(r)}
                  />
                ))}
              </ul>
            </div>
          ))
        )}
      </section>

      <RecipeInstallModal
        recipe={installing}
        existingIds={installedIds}
        onClose={() => setInstalling(undefined)}
        onInstalled={() => {
          setInstalling(undefined);
          onInstalled();
        }}
        onError={onError}
      />
    </>
  );
}

function RecipeCard({
  recipe,
  alreadyInstalled,
  onInstall,
}: {
  recipe: MCPRecipe;
  alreadyInstalled: boolean;
  onInstall: () => void;
}) {
  const [stars, setStars] = useState<number | null>(null);
  // Lazy fetch de estrellas (best-effort).
  useEffect(() => {
    let alive = true;
    if (recipe.repo_url) {
      api
        .mcpRegistryStars(recipe.repo_url)
        .then((r) => {
          if (alive) setStars(r.stars);
        })
        .catch(() => {
          /* silent */
        });
    }
    return () => {
      alive = false;
    };
  }, [recipe.repo_url]);

  return (
    <Surface level={2} className="overflow-hidden">
      <div className="flex items-start gap-3 px-4 py-3">
        <div
          className="grid place-items-center h-9 w-9 rounded-md
                        bg-elevated/60 border border-white/[0.05] text-pri shrink-0 mt-0.5"
        >
          <Icon name={CATEGORY_ICON[recipe.category]} size={15} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium tracking-tight text-text truncate">
              {recipe.title}
            </span>
            {recipe.official && <Badge tone="accent">oficial</Badge>}
            {alreadyInstalled && <Badge tone="info">instalado</Badge>}
            {typeof stars === "number" && <StarBadge stars={stars} />}
          </div>
          <p className="mt-1 text-xs text-text-dim leading-relaxed line-clamp-2">
            {recipe.description}
          </p>
          <div className="mt-1 text-[10px] text-text-dim font-mono truncate">
            {recipe.command} {recipe.args_template.join(" ")}
          </div>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {recipe.repo_url && (
            <a
              href={recipe.repo_url}
              target="_blank"
              rel="noopener noreferrer"
              className="grid place-items-center h-8 w-8 rounded-md text-text-dim
                          hover:text-text hover:bg-white/[0.05] transition-colors"
              title="Ver código"
            >
              <Icon name="info" size={14} />
            </a>
          )}
          <Button
            variant="primary"
            size="sm"
            icon="download"
            disabled={alreadyInstalled}
            onClick={onInstall}
          >
            {alreadyInstalled ? "Instalado" : "Instalar"}
          </Button>
        </div>
      </div>
    </Surface>
  );
}

/* ── Recipe install modal — pide prompts + env y dispara CREATE ─── */

function RecipeInstallModal({
  recipe,
  existingIds,
  onClose,
  onInstalled,
  onError,
}: {
  recipe?: MCPRecipe;
  existingIds: Set<string>;
  onClose: () => void;
  onInstalled: () => void;
  onError: (msg: string) => void;
}) {
  const open = !!recipe;
  const [id, setId] = useState("");
  const [prompts, setPrompts] = useState<Record<string, string>>({});
  const [env, setEnv] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!recipe) return;
    // Si el suggested_id colisiona, agregamos sufijo
    let candidate = recipe.suggested_id;
    let n = 2;
    while (existingIds.has(candidate)) candidate = `${recipe.suggested_id}${n++}`;
    setId(candidate);
    setPrompts(Object.fromEntries(recipe.prompts.map((p) => [p.key, p.default ?? ""])));
    setEnv(Object.fromEntries(recipe.env_required.map((e) => [e.name, ""])));
  }, [recipe, existingIds]);

  if (!recipe) return null;
  const r: MCPRecipe = recipe;

  function resolveArgs(): string[] {
    return r.args_template.map((tpl) =>
      tpl.replace(/\{([A-Z_][A-Z0-9_]*)\}/g, (_, k) => prompts[k] ?? ""),
    );
  }

  async function install() {
    if (!id.trim()) {
      onError("El id es obligatorio");
      return;
    }
    for (const p of r.prompts) {
      if (p.required && !(prompts[p.key] || "").trim()) {
        onError(`Falta completar: ${p.label}`);
        return;
      }
    }
    for (const e of r.env_required) {
      if (e.required && !(env[e.name] || "").trim()) {
        onError(`Falta la variable de entorno: ${e.name}`);
        return;
      }
    }
    const body: MCPServerBody & { id: string } = {
      id: id.trim(),
      command: r.command,
      args: resolveArgs(),
      env: Object.fromEntries(Object.entries(env).filter(([, v]) => v.trim() !== "")),
      enabled: true,
    };
    setBusy(true);
    try {
      await api.mcpCreateServer(body);
      onInstalled();
    } catch (e) {
      onError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const previewArgs = resolveArgs().join(" ");

  return (
    <Modal open={open} onClose={onClose} eyebrow="Receta curada" title={`Instalar ${recipe.title}`}>
      <div className="flex flex-col gap-3">
        <div
          className="flex items-start gap-2 p-3 rounded-md
                        border border-pri/20 bg-pri/[0.04] text-xs text-text-dim"
        >
          <Icon name="sparkles" size={14} className="mt-0.5 shrink-0 text-pri" />
          <div>{recipe.description}</div>
        </div>

        <Field label="ID" hint="Prefija las tools. Letras/dígitos/'-'/'_'.">
          <TextInput value={id} onChange={(e) => setId(e.target.value)} autoFocus />
        </Field>

        {recipe.prompts.map((p) => (
          <Field key={p.key} label={p.label} hint={p.description}>
            <TextInput
              value={prompts[p.key] || ""}
              onChange={(e) => setPrompts((s) => ({ ...s, [p.key]: e.target.value }))}
              placeholder={p.default}
            />
          </Field>
        ))}

        {recipe.env_required.length > 0 && (
          <div className="flex flex-col gap-2 pt-2 border-t border-white/[0.05]">
            <div className="text-[11px] uppercase tracking-[0.18em] text-text-dim">
              Variables de entorno
            </div>
            {recipe.env_required.map((e) => (
              <Field key={e.name} label={e.name + (e.required ? " *" : "")} hint={e.description}>
                <TextInput
                  value={env[e.name] || ""}
                  onChange={(ev) => setEnv((s) => ({ ...s, [e.name]: ev.target.value }))}
                  type="text"
                />
              </Field>
            ))}
          </div>
        )}

        <div
          className="text-[10px] font-mono text-text-dim p-2 rounded
                        border border-white/[0.05] bg-sunken/40 truncate"
        >
          <span className="text-text-dim">$</span> {recipe.command} {previewArgs}
        </div>

        <div
          className="flex items-center justify-end gap-2 pt-3 mt-1
                        border-t border-white/[0.05]"
        >
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancelar
          </Button>
          <Button variant="primary" icon="download" onClick={install} disabled={busy}>
            {busy ? "Instalando…" : "Instalar"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
