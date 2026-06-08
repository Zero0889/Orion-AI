/**
 * SkillsPanel — catálogo de skills cargadas desde disco.
 *
 * Una skill es una carpeta `skills/<id>/SKILL.md` con frontmatter YAML
 * + markdown. El backend (core.skills) las parsea y el frontend solo
 * las muestra. A diferencia de MCP, las skills no corren procesos: son
 * markdown que el LLM lee como contexto.
 *
 * MVP: lista + drawer de detalle. La parte de "ejecutar" la skill
 * vendrá cuando el Director soporte el tool `use_skill`.
 */

import { useEffect, useMemo, useState } from "react";

import { api, type CliInfo, type SkillDetail, type SkillRegistryItem, type SkillSummary } from "@/api/rest";
import { Icon } from "@/ui/Icon";
import { Badge, Button, Empty, SectionHeader, Surface } from "@/ui/primitives";

export function SkillsPanel() {
  const [skills,  setSkills]  = useState<SkillSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<string | null>(null);
  const [openId,  setOpenId]  = useState<string | null>(null);
  const [browserOpen, setBrowserOpen] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      const list = await api.listSkills();
      setSkills(list);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function reload() {
    setLoading(true);
    try {
      await api.reloadSkills();
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void refresh(); }, []);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <SectionHeader
        eyebrow="Sistema"
        title="Skills"
        hint="Recetas en formato SKILL.md que el LLM lee como contexto extra. No son MCP — no corren procesos."
        action={
          <div className="flex items-center gap-2">
            <Badge tone="info" dot>{skills.length} cargadas</Badge>
            <Button variant="ghost" size="sm" icon="memory" onClick={reload} disabled={loading}>
              Recargar
            </Button>
            <Button variant="primary" size="sm" icon="plus" onClick={() => setBrowserOpen(true)}>
              Buscar en ClawHub
            </Button>
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto scrollbar-thin px-6 py-4">
        {error && (
          <div className="mb-3 flex items-start gap-2 p-3 rounded-md
                          border border-danger/30 bg-danger/10 text-xs text-danger">
            <Icon name="alert" size={14} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <Help />

        {loading && skills.length === 0 && (
          <div className="space-y-2">
            <div className="skeleton h-20" />
            <div className="skeleton h-20" />
          </div>
        )}

        {!loading && skills.length === 0 && (
          <Empty
            icon="sparkles"
            title="Aún no hay skills cargadas"
            hint="Creá una carpeta en `skills/<nombre>/` con un archivo SKILL.md (frontmatter YAML + markdown) y dale a Recargar."
          />
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {skills.map((s, i) => (
            <SkillCard key={s.id} skill={s} delay={i * 30} onOpen={() => setOpenId(s.id)} />
          ))}
        </div>
      </div>

      {openId && (
        <SkillDrawer id={openId} onClose={() => setOpenId(null)} />
      )}
      {browserOpen && (
        <ClawHubBrowser
          installed={new Set(skills.map((s) => s.id))}
          onClose={() => setBrowserOpen(false)}
          onInstalled={() => { void refresh(); }}
        />
      )}
    </div>
  );
}

/** Card genérica: detecta los bins requeridos del frontmatter
 *  (metadata.openclaw.requires.bins) y por cada uno:
 *   - Si está en el registry del backend → muestra botón Instalar/Reinstalar.
 *   - Si NO está en el registry → muestra link al repo y nota "manual".
 *   - Si está instalado (vía tools/ o PATH) → badge "Listo".
 */
function RequiredBinsCard({
  frontmatter, skillId,
}: { frontmatter: Record<string, unknown>; skillId: string }) {
  const bins = useMemo(() => extractRequiredBins(frontmatter), [frontmatter]);
  const [catalog, setCatalog] = useState<CliInfo[]>([]);
  const [busy,    setBusy]    = useState<string | null>(null);
  const [error,   setError]   = useState<string | null>(null);

  async function refresh() {
    try {
      setCatalog(await api.listCli());
    } catch (e) { setError(String(e)); }
  }
  useEffect(() => { void refresh(); /* eslint-disable-next-line */ }, [skillId]);

  if (bins.length === 0) {
    return (
      <Surface level={2} className="p-3 mb-4 border border-ok/15">
        <div className="text-[10px] uppercase tracking-[0.18em] text-ok mb-1">
          Sin dependencias externas
        </div>
        <p className="text-[11px] leading-relaxed text-text-dim">
          Esta skill no declara binarios requeridos. Debería andar al instalarse,
          asumiendo que las tools nativas de ORION (shell, files, web) cubren lo que pide.
        </p>
      </Surface>
    );
  }

  async function install(name: string) {
    setBusy(name);
    try {
      await api.cliInstall(name);
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Surface level={2} className="p-3 mb-4 border border-acc/20">
      <div className="text-[10px] uppercase tracking-[0.18em] text-acc mb-1">
        Binarios requeridos
      </div>
      <p className="text-[11px] leading-relaxed text-text-dim mb-3">
        Esta skill llama a CLIs externas. Las que ORION sabe instalar van con un botón;
        las que no, tenés que bajarlas a mano (link al repo).
      </p>
      {error && (
        <div className="mb-2 p-2 rounded-md border border-danger/30 bg-danger/10 text-[11px] text-danger">
          {error}
        </div>
      )}
      <ul className="space-y-2">
        {bins.map((bin) => {
          const entry = catalog.find((c) => c.name === bin);
          const knownInstaller = !!entry;
          const installed = entry?.installed ?? false;
          return (
            <li key={bin} className="flex items-center justify-between gap-3 p-2 rounded-md
                                     border border-white/[0.06] bg-bg/40">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <code className="text-sm font-mono text-text">{bin}</code>
                  {installed
                    ? <Badge tone="success" dot>Listo</Badge>
                    : knownInstaller
                      ? <Badge tone="warn" dot>Falta</Badge>
                      : <Badge tone="neutral">Manual</Badge>}
                </div>
                {entry && (
                  <div className="text-[10px] text-muted truncate">
                    {entry.description} · {entry.repo}@{entry.version}
                  </div>
                )}
                {!entry && (
                  <div className="text-[10px] text-muted">
                    No está en el registry de ORION. Instalalo a mano o pedime que lo agregue.
                  </div>
                )}
              </div>
              <div className="shrink-0 flex items-center gap-2">
                {knownInstaller && (
                  <Button
                    variant={installed ? "ghost" : "primary"}
                    size="sm"
                    icon={installed ? "memory" : "plus"}
                    onClick={() => install(bin)}
                    disabled={busy === bin}
                  >
                    {busy === bin ? "…" : installed ? "Reinstalar" : "Instalar"}
                  </Button>
                )}
                {!knownInstaller && (
                  <a
                    href={`https://www.google.com/search?q=${encodeURIComponent(bin + " windows install")}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[11px] text-pri hover:underline"
                  >
                    ¿cómo instalar?
                  </a>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </Surface>
  );
}

function extractRequiredBins(frontmatter: Record<string, unknown>): string[] {
  // Espejo del parser Python core.cli_installer.required_bins. Tolerante.
  let meta = frontmatter["metadata"];
  if (typeof meta === "string") {
    try { meta = JSON.parse(meta); } catch { return []; }
  }
  if (!meta || typeof meta !== "object") return [];
  const m = meta as Record<string, unknown>;
  const oc = (m["openclaw"] ?? m["orion"]) as Record<string, unknown> | undefined;
  if (!oc || typeof oc !== "object") return [];
  const requires = oc["requires"] as Record<string, unknown> | undefined;
  if (!requires || typeof requires !== "object") return [];
  const bins = requires["bins"];
  if (!bins) return [];
  if (typeof bins === "string") return bins.split(/[,\s]+/).filter(Boolean);
  if (Array.isArray(bins)) return (bins as unknown[]).map(String).filter(Boolean);
  return [];
}

/** Sólo OAuth (el binario lo gestiona RequiredBinsCard como cualquier otro). */
function GogOauthCard() {
  const [open, setOpen] = useState(false);
  return (
    <Surface level={2} className="p-3 mb-4 border border-pri/20">
      <div className="flex items-center justify-between mb-1">
        <div className="text-[10px] uppercase tracking-[0.18em] text-pri">
          OAuth de Google (paso obligatorio)
        </div>
        <Button variant="ghost" size="sm" onClick={() => setOpen((v) => !v)}>
          {open ? "Ocultar pasos" : "Ver pasos"}
        </Button>
      </div>
      <p className="text-[11px] leading-relaxed text-text-dim">
        Aunque tengas el binario instalado, hasta que no configures OAuth en Google Cloud
        Console y corras <code>gog auth add</code>, la skill no puede leer ni enviar nada.
        Es una sola vez.
      </p>
      {open && <div className="mt-3"><GogOauthSteps /></div>}
    </Surface>
  );
}

function GogOauthSteps() {
  return (
    <div className="text-[11px] leading-relaxed text-text-dim space-y-2 p-3 rounded-lg
                    border border-white/[0.06] bg-bg/40">
      <p className="text-text">
        Esto te lleva ~10 min. Hacelo <strong>una sola vez</strong>:
      </p>
      <ol className="list-decimal pl-4 space-y-1.5">
        <li>
          Andá a{" "}
          <a className="text-pri hover:underline"
             href="https://console.cloud.google.com/" target="_blank" rel="noopener noreferrer">
            Google Cloud Console
          </a>
          {" "}y creá (o seleccioná) un proyecto.
        </li>
        <li>
          Activá las APIs que vas a usar: Gmail, Calendar, Drive, Docs, Sheets, Contacts.
        </li>
        <li>
          En <em>OAuth consent screen</em> → tipo "External" → agregá tu email como test user.
        </li>
        <li>
          En <em>Credentials</em> → "Create Credentials" → "OAuth client ID" → tipo
          "Desktop app" → descargá el <code>client_secret.json</code>.
        </li>
        <li>
          Abrí una PowerShell y corré (cambiando la ruta):
          <pre className="mt-1 p-2 rounded bg-bg/60 border border-white/[0.06] text-[10px] font-mono whitespace-pre-wrap">
{`gog auth credentials C:\\ruta\\al\\client_secret.json
gog auth add tu-email@gmail.com --services gmail,calendar,drive,docs,sheets
gog auth list`}
          </pre>
        </li>
        <li>
          Verificá con: <code>gog gmail search "newer_than:1d" --max 3</code>.
          Si lista emails, está listo.
        </li>
      </ol>
      <p className="text-muted text-[10px] mt-2">
        ORION inyecta <code>tools/gog/</code> en el PATH del subprocess. Si <code>gog</code>
        no responde en tu PowerShell pero sí en una tarea de ORION, es porque tu shell no tiene
        la carpeta en el PATH — eso es normal, no es un bug.
      </p>
    </div>
  );
}

/** Drawer para explorar el repo OpenClaw y descargar skills al disco. */
function ClawHubBrowser({
  installed, onClose, onInstalled,
}: {
  installed:   Set<string>;
  onClose:     () => void;
  onInstalled: () => void;
}) {
  const [q,        setQ]        = useState("");
  const [items,    setItems]    = useState<SkillRegistryItem[]>([]);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState<string | null>(null);
  const [installing, setInstalling] = useState<string | null>(null);
  const [installed2, setInstalled2] = useState<Set<string>>(new Set());

  async function search() {
    setLoading(true);
    try {
      const r = await api.searchSkillRegistry(q);
      setItems(r);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void search(); /* primera carga */ /* eslint-disable-next-line */ }, []);

  async function install(id: string) {
    setInstalling(id);
    try {
      const r = await api.installSkill(id, "openclaw");
      if (r.loaded) {
        setInstalled2((s) => new Set([...s, id]));
        onInstalled();
      } else {
        setError(`Skill '${id}' descargada (${r.files.length} archivos) pero no se cargó. Revisá si tiene SKILL.md.`);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setInstalling(null);
    }
  }

  return (
    <div className="fixed inset-0 z-40 animate-fade-in">
      <div className="absolute inset-0 bg-black/55 backdrop-blur-sm" onClick={onClose} />
      <aside
        role="dialog"
        aria-modal="true"
        className="absolute right-0 top-0 h-full w-full max-w-[560px]
                   bg-surface border-l border-white/[0.06] shadow-2xl
                   flex flex-col animate-slide-in"
      >
        <header className="flex items-center justify-between px-5 h-14 border-b border-white/[0.06]">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-[10px] uppercase tracking-[0.18em] text-muted">ClawHub</span>
            <span className="text-sm font-medium text-text truncate">Skills disponibles en OpenClaw</span>
          </div>
          <button
            onClick={onClose}
            className="h-8 w-8 grid place-items-center rounded-md text-text-dim
                       hover:text-text hover:bg-white/[0.06] transition-colors"
            title="Cerrar"
          >
            <Icon name="close" size={15} />
          </button>
        </header>

        <div className="px-5 py-3 border-b border-white/[0.06]">
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") search(); }}
              placeholder="Filtrar por nombre (ej: github, notion, gh-issues)…"
              className="flex-1 px-3 h-9 text-sm rounded-md bg-elevated border border-white/[0.08]
                         focus:outline-none focus:border-pri/40 placeholder-muted"
            />
            <Button variant="primary" size="sm" icon="search" onClick={search} disabled={loading}>
              Buscar
            </Button>
          </div>
          <p className="mt-2 text-[10px] text-muted">
            Las skills se descargan de github.com/openclaw/openclaw → tu carpeta <code>skills/</code>.
          </p>
        </div>

        <div className="flex-1 overflow-y-auto scrollbar-thin px-5 py-3">
          {error && (
            <div className="mb-3 p-3 rounded-md border border-danger/30 bg-danger/10 text-xs text-danger">
              {error}
            </div>
          )}

          {loading && items.length === 0 && (
            <div className="space-y-2">
              <div className="skeleton h-10" />
              <div className="skeleton h-10" />
              <div className="skeleton h-10" />
            </div>
          )}

          {!loading && items.length === 0 && (
            <p className="text-xs text-text-dim italic">Sin resultados.</p>
          )}

          <ul className="divide-y divide-white/[0.04]">
            {items.map((it) => {
              const isInstalled = installed.has(it.id) || installed2.has(it.id);
              const isBusy      = installing === it.id;
              return (
                <li key={it.id} className="flex items-center justify-between gap-3 py-2.5">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <code className="text-sm font-mono text-text">{it.id}</code>
                      {isInstalled && <Badge tone="success">Instalada</Badge>}
                    </div>
                    <a
                      href={it.html_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[10px] text-muted hover:text-pri underline-offset-2 hover:underline"
                    >
                      ver en github ↗
                    </a>
                  </div>
                  <Button
                    variant={isInstalled ? "ghost" : "primary"}
                    size="sm"
                    icon={isInstalled ? "check" : "plus"}
                    onClick={() => install(it.id)}
                    disabled={isBusy}
                  >
                    {isBusy ? "Instalando…" : isInstalled ? "Reinstalar" : "Instalar"}
                  </Button>
                </li>
              );
            })}
          </ul>
        </div>

        <footer className="px-5 h-12 border-t border-white/[0.06] flex items-center text-[10px] text-muted">
          {items.length > 0 && `${items.length} skill${items.length === 1 ? "" : "s"} en el registry`}
        </footer>
      </aside>
    </div>
  );
}

function Help() {
  const [open, setOpen] = useState(false);
  return (
    <div className="mb-4 rounded-lg border border-white/[0.06] bg-elevated/30 overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-3 h-10
                   text-left hover:bg-white/[0.03] transition-colors"
      >
        <div className="flex items-center gap-2 text-xs text-text-dim">
          <Icon name="info" size={13} />
          <span>¿En qué se diferencian las skills de los servidores MCP?</span>
        </div>
        <Icon name={open ? "chevron-down" : "chevron-right"} size={13} className="text-muted" />
      </button>
      {open && (
        <div className="px-3 pb-3 text-[11px] leading-relaxed text-text-dim space-y-2 border-t border-white/[0.06]">
          <p>
            <strong className="text-text">MCP</strong> son procesos vivos que exponen
            <em> tools nuevas</em> vía JSON-RPC (ej: <code>github__create_issue</code>).
            Aportan funcionalidad ejecutable.
          </p>
          <p>
            <strong className="text-text">Skills</strong> son markdown que enseña al LLM
            <em> cómo combinar las tools que ya tiene</em> (shell, files, web). No
            corren nada — son contexto extra en el system prompt cuando el Director
            decide invocarlas.
          </p>
          <p>
            Una skill mide ~5–50 KB. El backend corta a <code>max_inject_chars</code>
            (default 8000) al inyectarla, para no reventar el context window.
          </p>
        </div>
      )}
    </div>
  );
}

function SkillCard({
  skill, onOpen, delay,
}: { skill: SkillSummary; onOpen: () => void; delay?: number }) {
  return (
    <button
      onClick={onOpen}
      style={{ animationDelay: `${delay ?? 0}ms` }}
      className="group text-left rounded-xl p-4 bg-elevated/60 border border-white/[0.06]
                 hover:border-pri/40 hover:bg-elevated transition-all duration-200
                 animate-fade-in-up overflow-hidden"
    >
      <header className="flex items-start justify-between gap-3 mb-2">
        <div className="min-w-0 flex-1">
          <h4 className="text-[15px] font-medium text-text leading-tight truncate">
            {skill.name}
          </h4>
          <code className="text-[10px] font-mono text-muted">{skill.id}</code>
        </div>
        {skill.user_invocable && (
          <Badge tone="accent">user</Badge>
        )}
      </header>

      <p className="text-xs leading-relaxed text-text-dim line-clamp-3 mb-3">
        {skill.description || "Sin descripción."}
      </p>

      <footer className="flex items-center justify-between text-[10px] uppercase tracking-[0.14em] text-muted">
        <span className="flex items-center gap-1">
          <Icon name="edit" size={11} />
          {skill.char_count.toLocaleString()} chars
        </span>
        <span className="text-pri group-hover:underline">Ver detalle →</span>
      </footer>
    </button>
  );
}

function SkillDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const [data,  setData]  = useState<SkillDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.getSkill(id)
      .then((d) => { if (alive) { setData(d); setError(null); } })
      .catch((e) => { if (alive) setError(String(e)); });
    return () => { alive = false; };
  }, [id]);

  return (
    <div className="fixed inset-0 z-40 animate-fade-in">
      <div className="absolute inset-0 bg-black/55 backdrop-blur-sm" onClick={onClose} />
      <aside
        role="dialog"
        aria-modal="true"
        className="absolute right-0 top-0 h-full w-full max-w-[640px]
                   bg-surface border-l border-white/[0.06] shadow-2xl
                   flex flex-col animate-slide-in"
      >
        <header className="flex items-center justify-between px-5 h-14 border-b border-white/[0.06]">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-[10px] uppercase tracking-[0.18em] text-muted">Skill</span>
            <span className="text-sm font-medium text-text truncate">{data?.name ?? id}</span>
          </div>
          <button
            onClick={onClose}
            className="h-8 w-8 grid place-items-center rounded-md text-text-dim
                       hover:text-text hover:bg-white/[0.06] transition-colors"
            title="Cerrar"
          >
            <Icon name="close" size={15} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto scrollbar-thin px-5 py-4">
          {error && (
            <div className="mb-3 p-3 rounded-md border border-danger/30 bg-danger/10
                            text-xs text-danger">
              {error}
            </div>
          )}

          {data && (
            <>
              <RequiredBinsCard frontmatter={data.frontmatter} skillId={data.id} />
              {data.id === "gog" && <GogOauthCard />}

              <Surface level={2} className="p-3 mb-4">
                <div className="text-[10px] uppercase tracking-[0.18em] text-muted mb-1">
                  Descripción
                </div>
                <p className="text-xs leading-relaxed text-text-dim">{data.description}</p>
                <div className="mt-3 grid grid-cols-2 gap-3 text-[10px] uppercase tracking-[0.14em] text-muted">
                  <span>{data.char_count.toLocaleString()} chars · corte a {data.max_inject.toLocaleString()}</span>
                  <span className="text-right truncate" title={data.path}>{data.path.split(/[\\/]/).slice(-3).join("/")}</span>
                </div>
              </Surface>

              <div className="text-[10px] uppercase tracking-[0.18em] text-muted mb-2">
                Frontmatter
              </div>
              <pre className="rounded-lg border border-white/[0.06] bg-bg/60 p-3 mb-4
                              text-[11px] leading-relaxed font-mono text-text
                              max-h-40 overflow-auto scrollbar-thin">
                <code>{JSON.stringify(data.frontmatter, null, 2)}</code>
              </pre>

              <div className="text-[10px] uppercase tracking-[0.18em] text-muted mb-2">
                Cuerpo (markdown)
              </div>
              <pre className="rounded-lg border border-white/[0.06] bg-bg/60 p-3
                              text-[11px] leading-relaxed font-mono text-text
                              whitespace-pre-wrap break-words">
                <code>{data.body}</code>
              </pre>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
