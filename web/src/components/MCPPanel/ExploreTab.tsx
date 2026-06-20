/**
 * ExploreTab — búsqueda en el registry oficial de MCP.
 *
 * Permite buscar servers públicos en `registry.modelcontextprotocol.io`,
 * filtrarlos (solo instalables stdio / solo oficiales), ver sus detalles
 * y disparar el flow de instalación (que abre el `ServerFormModal` del
 * padre con los datos pre-rellenados).
 *
 * Debounce de 300ms en la búsqueda para no pegarle al registry por
 * cada keystroke. Lazy fetch de estrellas (best-effort, cacheado en el
 * padre vía `starsMap`).
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { api, type MCPRegistryPackage, type MCPRegistryServer } from "@/api/rest";
import { Icon } from "@/ui/Icon";
import { Badge, Button, Empty, Surface, TextInput } from "@/ui/primitives";

import { StarBadge } from "./StarBadge";

interface Props {
  installedIds: Set<string>;
  onInstall: (server: MCPRegistryServer, pkg: MCPRegistryPackage) => void;
  onError: (msg: string) => void;
}

export function ExploreTab({ installedIds, onInstall, onError }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<MCPRegistryServer[]>([]);
  const [loading, setLoading] = useState(false);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [onlyInstallable, setOnlyInstallable] = useState(true);
  const [onlyOfficial, setOnlyOfficial] = useState(false);
  // Mapa repo_url → stars (lazy-loaded por card)
  const [starsMap, setStarsMap] = useState<Record<string, number | null>>({});

  // Debounce de la búsqueda — no queremos pegarle al registry en cada keystroke.
  const debounceRef = useRef<number | undefined>(undefined);

  const runSearch = useCallback(
    async (q: string, append = false, fromCursor?: string) => {
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
    },
    [onError],
  );

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
        <Icon
          name="search"
          size={14}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-text-dim"
        />
        <TextInput
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder="Buscar en el registry oficial (github, postgres, slack, …)"
          className="pl-9"
        />
      </div>

      <div className="text-[11px] text-text-dim flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <span>
            Fuente: <span className="font-mono text-text">registry.modelcontextprotocol.io</span>
          </span>
          {loading && <span className="text-pri">cargando…</span>}
        </div>
        <div className="flex items-center gap-3">
          <label className="inline-flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={onlyOfficial}
              onChange={(e) => setOnlyOfficial(e.target.checked)}
              className="accent-pri h-3 w-3"
            />
            <span>Solo oficiales</span>
          </label>
          <label className="inline-flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={onlyInstallable}
              onChange={(e) => setOnlyInstallable(e.target.checked)}
              className="accent-pri h-3 w-3"
            />
            <span>Solo instalables (stdio)</span>
          </label>
        </div>
      </div>

      {/* Results */}
      {(() => {
        let filtered = results;
        if (onlyInstallable) filtered = filtered.filter((s) => s.installable);
        if (onlyOfficial) filtered = filtered.filter(isOfficial);

        // Ranking: cuando hay query, los matches en title/name pesan más que
        // los matches en description. Después, los oficiales arriba dentro
        // de cada grupo.
        if (query.trim()) {
          const q = query.trim().toLowerCase();
          const score = (s: MCPRegistryServer) => {
            let v = 0;
            if (s.title.toLowerCase().includes(q)) v += 4;
            if (s.name.toLowerCase().includes(q)) v += 2;
            if (s.description.toLowerCase().includes(q)) v += 1;
            if (isOfficial(s)) v += 1;
            return v;
          };
          filtered = [...filtered].sort((a, b) => score(b) - score(a));
        } else if (onlyOfficial) {
          // Sin query, al menos pone los oficiales arriba si están mezclados
          filtered = [...filtered].sort((a, b) => Number(isOfficial(b)) - Number(isOfficial(a)));
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
                {hiddenCount} resultado{hiddenCount === 1 ? "" : "s"} oculto
                {hiddenCount === 1 ? "" : "s"} (remote-only).
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
  return (
    n.startsWith("io.modelcontextprotocol/") ||
    n.startsWith("@modelcontextprotocol/") ||
    (s.repository || "").toLowerCase().includes("github.com/modelcontextprotocol/")
  );
}

function RegistryRow({
  server,
  alreadyInstalled,
  stars,
  onStarsLoaded,
  onInstall,
}: {
  server: MCPRegistryServer;
  alreadyInstalled: boolean;
  stars?: number | null;
  onStarsLoaded?: (s: number | null) => void;
  onInstall: (pkg: MCPRegistryPackage) => void;
}) {
  const [open, setOpen] = useState(false);

  // Lazy fetch de estrellas (una vez por repo_url; el padre cachea en starsMap).
  useEffect(() => {
    if (!server.repository) return;
    if (stars !== undefined) return;
    let alive = true;
    api
      .mcpRegistryStars(server.repository)
      .then((r) => {
        if (alive) onStarsLoaded?.(r.stars);
      })
      .catch(() => {
        /* silent */
      });
    return () => {
      alive = false;
    };
  }, [server.repository, stars, onStarsLoaded]);
  const pkg = server.packages[0]; // la primera installable
  const canInstall = server.installable && !!pkg;
  // Etiqueta principal del estado del server (solo una, en orden de prioridad)
  const tagTone: "accent" | "info" | "warn" | "neutral" = alreadyInstalled
    ? "accent"
    : canInstall
      ? "info"
      : server.remote
        ? "warn"
        : "neutral";
  const tagLabel = alreadyInstalled
    ? "instalado"
    : canInstall
      ? "instalable"
      : server.remote
        ? "remoto (HTTP)"
        : "no soportado";

  return (
    <Surface level={2} className="overflow-hidden">
      <div className="flex items-start gap-3 px-4 py-3">
        <div
          className="grid place-items-center h-8 w-8 rounded-md
                        bg-elevated/60 border border-white/[0.05] text-pri shrink-0 mt-0.5"
        >
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
          <div className="text-[11px] text-text-dim font-mono truncate">{server.name}</div>
          {server.description && (
            <p className="mt-1 text-xs text-text-dim leading-relaxed line-clamp-2">
              {server.description}
            </p>
          )}
          {server.remote && !canInstall && (
            <p className="mt-1 text-[11px] text-warn/80 leading-relaxed">
              Este server vive en {server.remote_kinds.join(", ")} y ORION todavía no soporta
              transports remotos — solo stdio. Mirá su repo para alternativas locales.
            </p>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {(pkg || server.remote) && (
            <Button
              variant="ghost"
              size="sm"
              icon={open ? "chevron-down" : "chevron-right"}
              onClick={() => setOpen((v) => !v)}
              title="Ver detalles"
            />
          )}
          {canInstall && (
            <Button variant="primary" size="sm" icon="download" onClick={() => onInstall(pkg!)}>
              Instalar
            </Button>
          )}
        </div>
      </div>

      {open && (
        <div
          className="border-t border-white/[0.05] bg-sunken/30 px-4 py-3 animate-fade-in
                        text-xs font-mono leading-relaxed text-text-dim"
        >
          {pkg ? (
            <>
              <div>
                <span className="text-text-dim">command:</span>{" "}
                <span className="text-text">{pkg.command}</span>
              </div>
              <div className="truncate">
                <span className="text-text-dim">args:</span>{" "}
                <span className="text-text">{pkg.args.join(" ")}</span>
              </div>
              <div>
                <span className="text-text-dim">registry:</span>{" "}
                <span className="text-text">{pkg.registry_type}</span>
              </div>
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
              <a
                href={server.repository}
                target="_blank"
                rel="noopener noreferrer"
                className="text-pri hover:underline"
              >
                {server.repository}
              </a>
            </div>
          )}
        </div>
      )}
    </Surface>
  );
}
