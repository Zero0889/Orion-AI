/**
 * MCPPanel — gestión de servidores MCP (Model Context Protocol).
 *
 * Muestra los servers que ORION tiene configurados en
 * `config/mcp_servers.json`, su estado live (running / error / nro de
 * tools) y permite agregar, editar, restart, reload y borrar.
 *
 * Las tools que estos servers exponen aparecen automáticamente en
 * Gemini Live, en el executor autónomo y en el planner — el panel solo
 * gobierna el ciclo de vida del subprocess, no las tools en sí.
 *
 * Layout: lista (cards expandibles) + modal de edición.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  api,
  type MCPRecipe, type MCPRecipeCategory,
  type MCPRegistryPackage, type MCPRegistryServer,
  type MCPServerBody, type MCPServerStatus,
} from "@/api/rest";
import { Icon, type IconName } from "@/ui/Icon";
import {
  Badge, Button, Empty, Field, Modal, SectionHeader, Surface,
  Switch, TextInput,
} from "@/ui/primitives";

type Tab = "installed" | "curated" | "explore";

/** Datos para pre-rellenar el modal cuando el usuario hace "Instalar"
 * desde la pestaña Explorar. */
interface PrefillFromRegistry {
  suggestedId: string;
  body:        MCPServerBody;
  envRequired: { name: string; description: string; required: boolean }[];
}

export function MCPPanel() {
  const [tab,         setTab]         = useState<Tab>("installed");
  const [servers,     setServers]     = useState<MCPServerStatus[]>([]);
  const [error,       setError]       = useState<string | null>(null);
  const [loading,     setLoading]     = useState(true);
  const [refreshTick, setRefreshTick] = useState(0);

  // modal
  const [editing,   setEditing]   = useState<MCPServerStatus | undefined>(undefined);
  const [prefill,   setPrefill]   = useState<PrefillFromRegistry | undefined>(undefined);
  const [modalOpen, setModalOpen] = useState(false);

  // expansión por server (qué cards muestran sus tools)
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const toggleExpand = (id: string) =>
    setExpanded((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const refetch = useCallback(() => setRefreshTick((n) => n + 1), []);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.mcpListServers()
      .then((data) => { if (alive) { setServers(data); setError(null); } })
      .catch((e) => { if (alive) setError(String(e)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [refreshTick]);

  async function handleDelete(id: string) {
    if (!confirm(`¿Borrar el server MCP '${id}'? Se detiene y se quita del config.`)) return;
    try {
      await api.mcpDeleteServer(id);
      refetch();
    } catch (e) { setError(String(e)); }
  }

  async function handleRestart(id: string) {
    try {
      await api.mcpRestartServer(id);
      refetch();
    } catch (e) { setError(String(e)); }
  }

  async function handleReloadAll() {
    try {
      await api.mcpReload();
      refetch();
    } catch (e) { setError(String(e)); }
  }

  function openCreate() {
    setEditing(undefined); setPrefill(undefined); setModalOpen(true);
  }
  function openEdit(s: MCPServerStatus) {
    setEditing(s); setPrefill(undefined); setModalOpen(true);
  }
  function openInstallFromRegistry(server: MCPRegistryServer, pkg: MCPRegistryPackage) {
    // Sugerimos un id derivado del nombre del paquete. El usuario lo edita.
    const cleanId = (pkg.identifier || server.name)
      .replace(/^@/, "")
      .replace(/[^a-zA-Z0-9_-]+/g, "_")
      .slice(0, 24);
    setEditing(undefined);
    setPrefill({
      suggestedId: cleanId,
      body: {
        command:  pkg.command,
        args:     pkg.args,
        env:      Object.fromEntries(pkg.env_required.map((e) => [e.name, ""])),
        enabled:  true,
      },
      envRequired: pkg.env_required,
    });
    setModalOpen(true);
  }

  const enabledCount = servers.filter((s) => s.enabled).length;
  const runningCount = servers.filter((s) => s.running).length;
  const toolsCount   = servers.reduce((acc, s) => acc + s.tool_count, 0);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <SectionHeader
        eyebrow="Sistema"
        title="MCP"
        hint="Servidores externos que extienden a ORION con tools adicionales."
        action={
          <div className="flex items-center gap-2">
            <div className="hidden md:flex items-center gap-1.5">
              <Badge tone="info" dot>{servers.length} servers</Badge>
              <Badge tone="accent">{toolsCount} tools</Badge>
            </div>
            {tab === "installed" && (
              <>
                <Button variant="ghost" size="sm" icon="orbit" onClick={handleReloadAll}>
                  Reload
                </Button>
                <Button variant="primary" size="sm" icon="plus" onClick={openCreate}>
                  Nuevo
                </Button>
              </>
            )}
          </div>
        }
      />

      {/* ── Tabs ─────────────────────────────────────────────────── */}
      <div className="px-6 pt-3 flex items-center gap-1 border-b border-white/[0.05]">
        <TabButton active={tab === "installed"} onClick={() => setTab("installed")}>
          <Icon name="plug" size={13} />
          Instalados
          <span className="ml-1 text-text-dim">{servers.length}</span>
        </TabButton>
        <TabButton active={tab === "curated"} onClick={() => setTab("curated")}>
          <Icon name="sparkles" size={13} />
          Curados
        </TabButton>
        <TabButton active={tab === "explore"} onClick={() => setTab("explore")}>
          <Icon name="search" size={13} />
          Explorar registry
        </TabButton>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {error && (
          <div className="mx-6 mt-3 flex items-start gap-2 p-3 rounded-md
                          border border-danger/30 bg-danger/10 text-xs text-danger animate-fade-in">
            <Icon name="alert" size={14} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {tab === "installed" && (
          <>
            <section className="p-6 flex flex-col gap-3">
              {loading && servers.length === 0 ? (
                <div className="text-xs text-text-dim">Cargando…</div>
              ) : servers.length === 0 ? (
                <Empty
                  icon="plug"
                  title="Sin servidores MCP configurados"
                  hint="Agregá uno o navegá el registry para descubrir servers oficiales (filesystem, GitHub, Slack, Postgres…)."
                  action={
                    <div className="flex gap-2">
                      <Button icon="search" variant="ghost" onClick={() => setTab("explore")}>
                        Explorar registry
                      </Button>
                      <Button icon="plus" onClick={openCreate}>Agregar a mano</Button>
                    </div>
                  }
                />
              ) : (
                servers.map((s) => (
                  <ServerCard
                    key={s.id}
                    server={s}
                    expanded={expanded.has(s.id)}
                    onToggleExpand={() => toggleExpand(s.id)}
                    onEdit={() => openEdit(s)}
                    onDelete={() => handleDelete(s.id)}
                    onRestart={() => handleRestart(s.id)}
                  />
                ))
              )}
            </section>

            {servers.length > 0 && (
              <div className="px-6 pb-6 text-[11px] text-text-dim">
                {enabledCount} habilitados · {runningCount} corriendo · {toolsCount} tools registradas
              </div>
            )}
          </>
        )}
        {tab === "curated" && (
          <CuratedTab
            installedIds={new Set(servers.map((s) => s.id))}
            onInstalled={() => { refetch(); setTab("installed"); }}
            onError={(e) => setError(String(e))}
          />
        )}
        {tab === "explore" && (
          <ExploreTab
            installedIds={new Set(servers.map((s) => s.id))}
            onInstall={openInstallFromRegistry}
            onError={(e) => setError(String(e))}
          />
        )}
      </div>

      <ServerFormModal
        open={modalOpen}
        initial={editing}
        prefill={prefill}
        onClose={() => setModalOpen(false)}
        onSaved={() => { setModalOpen(false); refetch(); setTab("installed"); }}
        onError={(e) => setError(String(e))}
      />
    </div>
  );
}


/* ── Tab button ────────────────────────────────────────────────────── */

function TabButton({
  active, onClick, children,
}: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={[
        "relative inline-flex items-center gap-1.5 px-3 h-8 text-xs font-medium",
        "rounded-t-md transition-colors duration-150",
        active
          ? "text-text bg-elevated/40"
          : "text-text-dim hover:text-text hover:bg-white/[0.03]",
      ].join(" ")}
    >
      {children}
      {active && (
        <span aria-hidden
              className="absolute left-2 right-2 -bottom-px h-[2px] rounded-full bg-pri
                         shadow-[0_0_8px_rgb(var(--orion-pri)/0.6)]" />
      )}
    </button>
  );
}


/* ── Pestaña Explorar ─────────────────────────────────────────────── */

function ExploreTab({
  installedIds, onInstall, onError,
}: {
  installedIds: Set<string>;
  onInstall:    (server: MCPRegistryServer, pkg: MCPRegistryPackage) => void;
  onError:      (msg: string) => void;
}) {
  const [query,            setQuery]            = useState("");
  const [results,          setResults]          = useState<MCPRegistryServer[]>([]);
  const [loading,          setLoading]          = useState(false);
  const [cursor,           setCursor]           = useState<string | null>(null);
  const [hasMore,          setHasMore]          = useState(false);
  const [onlyInstallable,  setOnlyInstallable]  = useState(true);
  const [onlyOfficial,     setOnlyOfficial]     = useState(false);
  // Mapa repo_url → stars (lazy-loaded por card)
  const [starsMap,         setStarsMap]         = useState<Record<string, number | null>>({});

  // Debounce de la búsqueda — no queremos pegarle al registry en cada keystroke.
  const debounceRef = useRef<number | undefined>(undefined);

  const runSearch = useCallback(async (q: string, append = false, fromCursor?: string) => {
    setLoading(true);
    try {
      const page = await api.mcpRegistrySearch(q, 20, fromCursor);
      setResults((prev) => (append ? [...prev, ...page.servers] : page.servers));
      setCursor(page.next_cursor);
      setHasMore(Boolean(page.next_cursor));
    } catch (e) {
      onError(String(e));
    } finally {
      setLoading(false);
    }
  }, [onError]);

  useEffect(() => {
    // Carga inicial: trae lo "trending" (sin query).
    runSearch("");
  }, [runSearch]);

  function onQueryChange(v: string) {
    setQuery(v);
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => {
      setCursor(null);
      runSearch(v);
    }, 300);
  }

  function loadMore() {
    if (cursor) runSearch(query, true, cursor);
  }

  return (
    <section className="p-6 flex flex-col gap-3">
      {/* Search bar */}
      <div className="relative">
        <Icon name="search" size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-text-dim" />
        <TextInput
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder="Buscar en el registry oficial (github, postgres, slack, …)"
          className="pl-9"
        />
      </div>

      <div className="text-[11px] text-text-dim flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <span>Fuente: <span className="font-mono text-text">registry.modelcontextprotocol.io</span></span>
          {loading && <span className="text-pri">cargando…</span>}
        </div>
        <div className="flex items-center gap-3">
          <label className="inline-flex items-center gap-2 cursor-pointer select-none">
            <input type="checkbox" checked={onlyOfficial}
                   onChange={(e) => setOnlyOfficial(e.target.checked)}
                   className="accent-pri h-3 w-3" />
            <span>Solo oficiales</span>
          </label>
          <label className="inline-flex items-center gap-2 cursor-pointer select-none">
            <input type="checkbox" checked={onlyInstallable}
                   onChange={(e) => setOnlyInstallable(e.target.checked)}
                   className="accent-pri h-3 w-3" />
            <span>Solo instalables (stdio)</span>
          </label>
        </div>
      </div>

      {/* Results */}
      {(() => {
        let filtered = results;
        if (onlyInstallable) filtered = filtered.filter((s) => s.installable);
        if (onlyOfficial)    filtered = filtered.filter(isOfficial);

        // Ranking: cuando hay query, los matches en title/name pesan más que
        // los matches en description. Después, los oficiales arriba dentro
        // de cada grupo.
        if (query.trim()) {
          const q = query.trim().toLowerCase();
          const score = (s: MCPRegistryServer) => {
            let v = 0;
            if (s.title.toLowerCase().includes(q)) v += 4;
            if (s.name.toLowerCase().includes(q))  v += 2;
            if (s.description.toLowerCase().includes(q)) v += 1;
            if (isOfficial(s)) v += 1;
            return v;
          };
          filtered = [...filtered].sort((a, b) => score(b) - score(a));
        } else if (onlyOfficial) {
          // Sin query, al menos pone los oficiales arriba si están mezclados
          filtered = [...filtered].sort((a, b) =>
            Number(isOfficial(b)) - Number(isOfficial(a)));
        }

        const hiddenCount = results.length - filtered.length;

        if (!loading && filtered.length === 0) {
          return (
            <Empty
              icon="search"
              title={
                results.length === 0
                  ? "Sin resultados"
                  : `Todos los resultados son remotos (${hiddenCount} ocultos)`
              }
              hint={
                results.length === 0
                  ? "Probá otra búsqueda o verificá que tu equipo tenga acceso a internet."
                  : "Desactivá 'Solo instalables' para verlos. ORION todavía no soporta transports HTTP, solo stdio."
              }
            />
          );
        }
        return (
          <>
            <ul className="flex flex-col gap-2">
              {filtered.map((srv) => (
                <RegistryRow
                  key={srv.name}
                  server={srv}
                  stars={srv.repository ? starsMap[srv.repository] : undefined}
                  onStarsLoaded={(s) => {
                    if (srv.repository) {
                      setStarsMap((m) => ({ ...m, [srv.repository!]: s }));
                    }
                  }}
                  alreadyInstalled={installedIds.has(srv.name.replace(/^@/, "").split("/")[0])}
                  onInstall={(pkg) => onInstall(srv, pkg)}
                />
              ))}
            </ul>
            {onlyInstallable && hiddenCount > 0 && (
              <p className="text-[11px] text-text-dim text-center">
                {hiddenCount} resultado{hiddenCount === 1 ? "" : "s"} oculto{hiddenCount === 1 ? "" : "s"} (remote-only).
              </p>
            )}
          </>
        );
      })()}

      {hasMore && (
        <div className="flex justify-center py-2">
          <Button variant="ghost" size="sm" onClick={loadMore} disabled={loading}>
            {loading ? "Cargando…" : "Cargar más"}
          </Button>
        </div>
      )}
    </section>
  );
}


/* ── Card de un resultado del registry ────────────────────────────── */

/** Heurística para detectar servers "oficiales" (Anthropic / namespace
 *  ``io.modelcontextprotocol/`` o paquetes ``@modelcontextprotocol/...``).
 *  El registry no expone un flag formal de "oficial" — usamos el namespace. */
function isOfficial(s: MCPRegistryServer): boolean {
  const n = (s.name || "").toLowerCase();
  return n.startsWith("io.modelcontextprotocol/")
      || n.startsWith("@modelcontextprotocol/")
      || (s.repository || "").toLowerCase().includes("github.com/modelcontextprotocol/");
}

function RegistryRow({
  server, alreadyInstalled, stars, onStarsLoaded, onInstall,
}: {
  server:            MCPRegistryServer;
  alreadyInstalled:  boolean;
  stars?:            number | null;
  onStarsLoaded?:    (s: number | null) => void;
  onInstall:         (pkg: MCPRegistryPackage) => void;
}) {
  const [open, setOpen] = useState(false);

  // Lazy fetch de estrellas (una vez por repo_url; el padre cachea en starsMap).
  useEffect(() => {
    if (!server.repository) return;
    if (stars !== undefined) return;
    let alive = true;
    api.mcpRegistryStars(server.repository)
      .then((r) => { if (alive) onStarsLoaded?.(r.stars); })
      .catch(() => { /* silent */ });
    return () => { alive = false; };
  }, [server.repository, stars, onStarsLoaded]);
  const pkg = server.packages[0]; // la primera installable
  const canInstall = server.installable && !!pkg;
  // Etiqueta principal del estado del server (solo una, en orden de prioridad)
  const tagTone: "accent" | "info" | "warn" | "neutral" =
    alreadyInstalled ? "accent"
    : canInstall     ? "info"
    : server.remote  ? "warn"
    :                  "neutral";
  const tagLabel =
    alreadyInstalled ? "instalado"
    : canInstall     ? "instalable"
    : server.remote  ? "remoto (HTTP)"
    :                  "no soportado";

  return (
    <Surface level={2} className="overflow-hidden">
      <div className="flex items-start gap-3 px-4 py-3">
        <div className="grid place-items-center h-8 w-8 rounded-md
                        bg-elevated/60 border border-white/[0.05] text-pri shrink-0 mt-0.5">
          <Icon name="plug" size={14} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium tracking-tight text-text truncate">
              {server.title || server.name || "(sin nombre)"}
            </span>
            {isOfficial(server) && <Badge tone="accent">oficial</Badge>}
            {server.version && <Badge tone="info">v{server.version}</Badge>}
            <Badge tone={tagTone}>{tagLabel}</Badge>
            {typeof stars === "number" && <StarBadge stars={stars} />}
          </div>
          <div className="text-[11px] text-text-dim font-mono truncate">
            {server.name}
          </div>
          {server.description && (
            <p className="mt-1 text-xs text-text-dim leading-relaxed line-clamp-2">
              {server.description}
            </p>
          )}
          {server.remote && !canInstall && (
            <p className="mt-1 text-[11px] text-warn/80 leading-relaxed">
              Este server vive en {server.remote_kinds.join(", ")} y ORION todavía
              no soporta transports remotos — solo stdio. Mirá su repo para
              alternativas locales.
            </p>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {(pkg || server.remote) && (
            <Button variant="ghost" size="sm"
                    icon={open ? "chevron-down" : "chevron-right"}
                    onClick={() => setOpen((v) => !v)}
                    title="Ver detalles" />
          )}
          {canInstall && (
            <Button variant="primary" size="sm" icon="download"
                    onClick={() => onInstall(pkg!)}>
              Instalar
            </Button>
          )}
        </div>
      </div>

      {open && (
        <div className="border-t border-white/[0.05] bg-sunken/30 px-4 py-3 animate-fade-in
                        text-xs font-mono leading-relaxed text-text-dim">
          {pkg ? (
            <>
              <div><span className="text-text-dim">command:</span> <span className="text-text">{pkg.command}</span></div>
              <div className="truncate"><span className="text-text-dim">args:</span> <span className="text-text">{pkg.args.join(" ")}</span></div>
              <div><span className="text-text-dim">registry:</span> <span className="text-text">{pkg.registry_type}</span></div>
              {pkg.env_required.length > 0 && (
                <div className="mt-2">
                  <div className="text-text-dim mb-1">Variables de entorno:</div>
                  <ul className="flex flex-col gap-0.5">
                    {pkg.env_required.map((e) => (
                      <li key={e.name}>
                        <span className="text-text">{e.name}</span>
                        {e.required && <span className="text-warn"> *</span>}
                        {e.description && <span className="text-text-dim"> — {e.description}</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          ) : server.remote ? (
            <div>
              <span className="text-text-dim">transports remotos:</span>{" "}
              <span className="text-text">{server.remote_kinds.join(", ")}</span>
            </div>
          ) : null}
          {server.repository && (
            <div className="mt-2 truncate">
              <span className="text-text-dim">repo:</span>{" "}
              <a href={server.repository} target="_blank" rel="noreferrer"
                 className="text-pri hover:underline">{server.repository}</a>
            </div>
          )}
        </div>
      )}
    </Surface>
  );
}


/* ── Card de un server individual ─────────────────────────────────── */

function ServerCard({
  server, expanded, onToggleExpand, onEdit, onDelete, onRestart,
}: {
  server: MCPServerStatus;
  expanded: boolean;
  onToggleExpand: () => void;
  onEdit:    () => void;
  onDelete:  () => void;
  onRestart: () => void;
}) {
  const statusTone =
    !server.enabled ? "muted"
    : server.error  ? "danger"
    : server.running ? "ok"
    : "warn";
  const statusLabel =
    !server.enabled ? "deshabilitado"
    : server.error  ? "error"
    : server.running ? "corriendo"
    : "detenido";

  return (
    <Surface level={2} className="overflow-hidden">
      {/* header */}
      <div className="flex items-center gap-3 px-4 py-3">
        <div className="grid place-items-center h-9 w-9 rounded-md bg-elevated/60
                        border border-white/[0.05] text-pri shrink-0">
          <Icon name="plug" size={16} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="text-sm font-medium tracking-tight text-text truncate">
              {server.id}
            </div>
            <StatusPill tone={statusTone} label={statusLabel} />
            {server.tool_count > 0 && (
              <Badge tone="info">{server.tool_count} tools</Badge>
            )}
          </div>
          <div className="text-[11px] text-text-dim truncate font-mono">
            {server.command}
            {server.args.length > 0 && (
              <span className="text-muted"> {server.args.join(" ")}</span>
            )}
          </div>
          {server.error && (
            <div className="text-[11px] text-danger mt-1 truncate">
              {server.error}
            </div>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <Button variant="ghost" size="sm" icon="orbit" onClick={onRestart}
                  title="Restart subprocess">
            Restart
          </Button>
          <Button variant="ghost" size="sm" icon="edit" onClick={onEdit} />
          <Button variant="ghost" size="sm" icon="trash" onClick={onDelete} />
          <Button variant="ghost" size="sm"
                  icon={expanded ? "chevron-down" : "chevron-right"}
                  onClick={onToggleExpand}
                  title="Ver tools" />
        </div>
      </div>

      {/* expanded: tools list */}
      {expanded && (
        <div className="border-t border-white/[0.05] bg-sunken/30 px-4 py-3 animate-fade-in">
          {server.tools.length === 0 ? (
            <div className="text-xs text-text-dim">
              {server.running
                ? "El server no expuso ninguna tool."
                : "Iniciá el server para ver las tools."}
            </div>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {server.tools.map((t) => (
                <li key={t.name} className="text-xs">
                  <span className="font-mono text-text">{server.id}__{t.name}</span>
                  {t.description && (
                    <span className="text-text-dim"> · {t.description}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Surface>
  );
}


/* ── Pill de estado ───────────────────────────────────────────────── */

function StatusPill({ tone, label }: { tone: string; label: string }) {
  const dotColor =
    tone === "ok"     ? "bg-ok shadow-[0_0_8px_rgb(var(--orion-ok))]"
    : tone === "danger" ? "bg-danger"
    : tone === "warn" ? "bg-warn"
    : "bg-muted";
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full
                     text-[10px] uppercase tracking-[0.16em]
                     border border-white/[0.06] bg-elevated/50 text-text-dim">
      <span className={`h-1.5 w-1.5 rounded-full ${dotColor}`} />
      {label}
    </span>
  );
}


/* ── Modal de creación / edición ──────────────────────────────────── */

function ServerFormModal({
  open, initial, prefill, onClose, onSaved, onError,
}: {
  open:     boolean;
  initial?: MCPServerStatus;
  prefill?: PrefillFromRegistry;
  onClose:  () => void;
  onSaved:  () => void;
  onError:  (msg: string) => void;
}) {
  const isEdit = !!initial;
  const isFromRegistry = !isEdit && !!prefill;

  const [id,          setId]          = useState("");
  const [command,     setCommand]     = useState("");
  const [argsText,    setArgsText]    = useState("");
  const [envText,     setEnvText]     = useState("");
  const [enabled,     setEnabled]     = useState(true);
  const [cwd,         setCwd]         = useState("");
  const [busy,        setBusy]        = useState(false);

  // Helper para serializar un dict de env vars al textarea
  function envToText(env: Record<string, string> | undefined): string {
    if (!env) return "";
    return Object.entries(env)
      .map(([k, v]) => `${k}=${v}`)
      .join("\n");
  }

  function quoteArg(a: string): string {
    return /\s/.test(a) ? `"${a}"` : a;
  }

  useEffect(() => {
    if (!open) return;
    if (initial) {
      // Modo edición
      setId(initial.id);
      setCommand(initial.command);
      setArgsText(initial.args.map(quoteArg).join(" "));
      setEnvText(envToText(initial.env));
      setEnabled(initial.enabled);
      setCwd(initial.cwd ?? "");
    } else if (prefill) {
      // Modo instalación desde registry
      setId(prefill.suggestedId);
      setCommand(prefill.body.command);
      setArgsText((prefill.body.args ?? []).map(quoteArg).join(" "));
      setEnvText(envToText(prefill.body.env));
      setEnabled(prefill.body.enabled ?? true);
      setCwd(prefill.body.cwd ?? "");
    } else {
      // Modo creación a mano: en blanco
      setId(""); setCommand(""); setArgsText(""); setEnvText("");
      setEnabled(true); setCwd("");
    }
  }, [open, initial, prefill]);

  function parseArgs(s: string): string[] {
    // Tokenización simple por whitespace, respeta "quoted strings"
    const out: string[] = [];
    const re = /"([^"]*)"|'([^']*)'|(\S+)/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(s)) !== null) {
      out.push(m[1] ?? m[2] ?? m[3]);
    }
    return out;
  }

  function parseEnv(s: string): Record<string, string> {
    const out: Record<string, string> = {};
    for (const raw of s.split(/\r?\n/)) {
      const line = raw.trim();
      if (!line || line.startsWith("#")) continue;
      const eq = line.indexOf("=");
      if (eq < 0) continue;
      out[line.slice(0, eq).trim()] = line.slice(eq + 1).trim();
    }
    return out;
  }

  async function save() {
    if (!command.trim()) { onError("El comando es obligatorio"); return; }
    if (!isEdit && !id.trim()) { onError("El id es obligatorio"); return; }

    const body: MCPServerBody = {
      command: command.trim(),
      args:    parseArgs(argsText),
      env:     parseEnv(envText),
      enabled,
      cwd:     cwd.trim() || undefined,
    };

    setBusy(true);
    try {
      if (isEdit) {
        await api.mcpUpdateServer(initial!.id, body);
      } else {
        await api.mcpCreateServer({ id: id.trim(), ...body });
      }
      onSaved();
    } catch (e) {
      onError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose}
           eyebrow={isFromRegistry ? "Instalar desde registry" : "MCP"}
           title={
             isEdit
               ? `Editar server '${initial!.id}'`
               : isFromRegistry
                 ? "Instalar servidor MCP"
                 : "Nuevo servidor MCP"
           }>
      <div className="flex flex-col gap-3">
        {isFromRegistry && prefill && (
          <div className="flex items-start gap-2 p-3 rounded-md
                          border border-pri/30 bg-pri/[0.06] text-xs text-text-dim">
            <Icon name="info" size={14} className="mt-0.5 shrink-0 text-pri" />
            <div className="space-y-1">
              <div>
                Pre-rellenado con la receta del registry oficial. Revisá el id,
                ajustá las variables de entorno y confirmá.
              </div>
              {prefill.envRequired.some((e) => e.required) && (
                <div>
                  Variables <span className="text-warn">obligatorias</span>:{" "}
                  <span className="font-mono text-text">
                    {prefill.envRequired.filter((e) => e.required).map((e) => e.name).join(", ")}
                  </span>
                </div>
              )}
            </div>
          </div>
        )}

        {!isEdit && (
          <Field label="ID" hint="Letras, dígitos, '-' y '_'. Prefija las tools (ej. fs__read_file).">
            <TextInput
              value={id}
              onChange={(e) => setId(e.target.value)}
              placeholder="fs"
              autoFocus
            />
          </Field>
        )}

        <Field label="Comando" hint="Binario que se ejecuta (resuelve PATH automáticamente).">
          <TextInput
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            placeholder="npx"
          />
        </Field>

        <Field label="Argumentos"
               hint='Separados por espacio. Usá comillas para preservar espacios.'>
          <TextInput
            value={argsText}
            onChange={(e) => setArgsText(e.target.value)}
            placeholder='-y @modelcontextprotocol/server-filesystem "C:/Users/zahir"'
          />
        </Field>

        <Field label="Variables de entorno"
               hint="Una por línea, formato KEY=valor. Líneas vacías o que empiezan con # se ignoran.">
          <textarea
            value={envText}
            onChange={(e) => setEnvText(e.target.value)}
            placeholder="GITHUB_TOKEN=ghp_..."
            rows={3}
            className="w-full px-3 py-2 rounded-md font-mono text-xs
                       bg-elevated/40 border border-white/[0.06]
                       text-text placeholder:text-muted
                       focus:outline-none focus:border-pri/40
                       focus:ring-1 focus:ring-pri/20"
          />
        </Field>

        <Field label="Working directory (opcional)">
          <TextInput
            value={cwd}
            onChange={(e) => setCwd(e.target.value)}
            placeholder="(default: cwd de ORION)"
          />
        </Field>

        <div className="flex items-center justify-between px-1 py-2 mt-1
                        border-t border-white/[0.05]">
          <div>
            <div className="text-xs font-medium text-text">Habilitado</div>
            <div className="text-[11px] text-text-dim">
              Si está apagado, el server queda guardado pero no se arranca.
            </div>
          </div>
          <Switch on={enabled} onClick={() => setEnabled((v) => !v)} />
        </div>

        <div className="flex items-center justify-end gap-2 pt-3 mt-1
                        border-t border-white/[0.05]">
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancelar
          </Button>
          <Button variant="primary" onClick={save} disabled={busy}>
            {busy ? "Guardando…" : isEdit ? "Guardar" : "Crear"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}


/* ── Curated tab ──────────────────────────────────────────────────── */

const CATEGORY_LABEL: Record<MCPRecipeCategory, string> = {
  files:  "Archivos",
  dev:    "Desarrollo",
  web:    "Web / búsqueda",
  ai:     "Inteligencia",
  system: "Sistema",
};

const CATEGORY_ICON: Record<MCPRecipeCategory, IconName> = {
  files:  "save",
  dev:    "cpu",
  web:    "search",
  ai:     "sparkles",
  system: "bolt",
};

function CuratedTab({
  installedIds, onInstalled, onError,
}: {
  installedIds: Set<string>;
  onInstalled:  () => void;
  onError:      (msg: string) => void;
}) {
  const [recipes,   setRecipes]   = useState<MCPRecipe[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [installing, setInstalling] = useState<MCPRecipe | undefined>(undefined);

  useEffect(() => {
    let alive = true;
    api.mcpRecipes()
      .then((data) => { if (alive) setRecipes(data); })
      .catch((e) => { if (alive) onError(String(e)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [onError]);

  // Agrupar por categoría
  const grouped = recipes.reduce<Record<string, MCPRecipe[]>>((acc, r) => {
    (acc[r.category] ||= []).push(r); return acc;
  }, {});

  return (
    <>
      <section className="p-6 flex flex-col gap-6">
        <div className="flex items-start gap-2 p-3 rounded-md
                        border border-acc/20 bg-acc/[0.04] text-xs text-text-dim">
          <Icon name="info" size={14} className="mt-0.5 shrink-0 text-acc" />
          <div>
            Los servers oficiales de Anthropic (Filesystem, Git, Memory…) NO
            están en el registry — viven en su monorepo. Los curamos acá para
            instalarlos con un click.
          </div>
        </div>

        {loading ? (
          <div className="text-xs text-text-dim">Cargando…</div>
        ) : (
          (Object.keys(grouped) as MCPRecipeCategory[]).map((cat) => (
            <div key={cat} className="flex flex-col gap-2">
              <div className="flex items-center gap-2 text-[11px] uppercase
                              tracking-[0.18em] text-pri/80">
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
        onInstalled={() => { setInstalling(undefined); onInstalled(); }}
        onError={onError}
      />
    </>
  );
}

function RecipeCard({
  recipe, alreadyInstalled, onInstall,
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
      api.mcpRegistryStars(recipe.repo_url)
        .then((r) => { if (alive) setStars(r.stars); })
        .catch(() => { /* silent */ });
    }
    return () => { alive = false; };
  }, [recipe.repo_url]);

  return (
    <Surface level={2} className="overflow-hidden">
      <div className="flex items-start gap-3 px-4 py-3">
        <div className="grid place-items-center h-9 w-9 rounded-md
                        bg-elevated/60 border border-white/[0.05] text-pri shrink-0 mt-0.5">
          <Icon name={CATEGORY_ICON[recipe.category]} size={15} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium tracking-tight text-text truncate">
              {recipe.title}
            </span>
            {recipe.official && <Badge tone="accent">oficial</Badge>}
            {alreadyInstalled && <Badge tone="info">instalado</Badge>}
            {typeof stars === "number" && (
              <StarBadge stars={stars} />
            )}
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
            <a href={recipe.repo_url} target="_blank" rel="noreferrer"
               className="grid place-items-center h-8 w-8 rounded-md text-text-dim
                          hover:text-text hover:bg-white/[0.05] transition-colors"
               title="Ver código">
              <Icon name="info" size={14} />
            </a>
          )}
          <Button variant="primary" size="sm" icon="download"
                  disabled={alreadyInstalled}
                  onClick={onInstall}>
            {alreadyInstalled ? "Instalado" : "Instalar"}
          </Button>
        </div>
      </div>
    </Surface>
  );
}

function StarBadge({ stars }: { stars: number }) {
  const display =
    stars >= 1000 ? `${(stars / 1000).toFixed(1)}k` : String(stars);
  return (
    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full
                     text-[10px] border border-white/[0.06] bg-elevated/50 text-text-dim"
          title={`${stars} estrellas en GitHub`}>
      <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" className="text-warn">
        <path d="M12 17.27 18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z" />
      </svg>
      {display}
    </span>
  );
}


/* ── Recipe install modal — pide prompts + env y dispara CREATE ─── */

function RecipeInstallModal({
  recipe, existingIds, onClose, onInstalled, onError,
}: {
  recipe?:    MCPRecipe;
  existingIds: Set<string>;
  onClose:    () => void;
  onInstalled: () => void;
  onError:    (msg: string) => void;
}) {
  const open = !!recipe;
  const [id,        setId]        = useState("");
  const [prompts,   setPrompts]   = useState<Record<string, string>>({});
  const [env,       setEnv]       = useState<Record<string, string>>({});
  const [busy,      setBusy]      = useState(false);

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
      tpl.replace(/\{([A-Z_][A-Z0-9_]*)\}/g, (_, k) => prompts[k] ?? "")
    );
  }

  async function install() {
    if (!id.trim()) { onError("El id es obligatorio"); return; }
    for (const p of r.prompts) {
      if (p.required && !(prompts[p.key] || "").trim()) {
        onError(`Falta completar: ${p.label}`); return;
      }
    }
    for (const e of r.env_required) {
      if (e.required && !(env[e.name] || "").trim()) {
        onError(`Falta la variable de entorno: ${e.name}`); return;
      }
    }
    const body: MCPServerBody & { id: string } = {
      id:      id.trim(),
      command: r.command,
      args:    resolveArgs(),
      env:     Object.fromEntries(
        Object.entries(env).filter(([, v]) => v.trim() !== "")
      ),
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
    <Modal open={open} onClose={onClose}
           eyebrow="Receta curada"
           title={`Instalar ${recipe.title}`}>
      <div className="flex flex-col gap-3">
        <div className="flex items-start gap-2 p-3 rounded-md
                        border border-pri/20 bg-pri/[0.04] text-xs text-text-dim">
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
              <Field key={e.name}
                     label={e.name + (e.required ? " *" : "")}
                     hint={e.description}>
                <TextInput
                  value={env[e.name] || ""}
                  onChange={(ev) => setEnv((s) => ({ ...s, [e.name]: ev.target.value }))}
                  type="text"
                />
              </Field>
            ))}
          </div>
        )}

        <div className="text-[10px] font-mono text-text-dim p-2 rounded
                        border border-white/[0.05] bg-sunken/40 truncate">
          <span className="text-text-dim">$</span> {recipe.command} {previewArgs}
        </div>

        <div className="flex items-center justify-end gap-2 pt-3 mt-1
                        border-t border-white/[0.05]">
          <Button variant="ghost" onClick={onClose} disabled={busy}>Cancelar</Button>
          <Button variant="primary" icon="download" onClick={install} disabled={busy}>
            {busy ? "Instalando…" : "Instalar"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
