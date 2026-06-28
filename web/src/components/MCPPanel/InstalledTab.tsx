/**
 * InstalledTab — lista de servers MCP configurados localmente.
 *
 * Renderiza una `ServerCard` por cada server. La card muestra estado
 * (running/error/disabled), tools expuestas (expandible) y permite
 * toggle/restart/edit/delete. El padre (`MCPPanel`) maneja el state
 * cross-tab y nos pasa los handlers.
 */

import type { MCPServerStatus } from "@/api/rest";
import { Icon } from "@/ui/Icon";
import { Badge, Button, Empty, Surface, Switch } from "@/ui/primitives";

interface Props {
  servers: MCPServerStatus[];
  loading: boolean;
  expanded: Set<string>;
  enabledCount: number;
  runningCount: number;
  toolsCount: number;
  onToggleExpand: (id: string) => void;
  onToggleEnabled: (s: MCPServerStatus) => void;
  onEdit: (s: MCPServerStatus) => void;
  onDelete: (id: string) => void;
  onRestart: (id: string) => void;
  onOpenCreate: () => void;
  onSwitchToExplore: () => void;
}

export function InstalledTab({
  servers,
  loading,
  expanded,
  enabledCount,
  runningCount,
  toolsCount,
  onToggleExpand,
  onToggleEnabled,
  onEdit,
  onDelete,
  onRestart,
  onOpenCreate,
  onSwitchToExplore,
}: Props) {
  return (
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
                <Button icon="search" variant="ghost" onClick={onSwitchToExplore}>
                  Explorar registry
                </Button>
                <Button icon="plus" onClick={onOpenCreate}>
                  Agregar a mano
                </Button>
              </div>
            }
          />
        ) : (
          servers.map((s) => (
            <ServerCard
              key={s.id}
              server={s}
              expanded={expanded.has(s.id)}
              onToggleExpand={() => onToggleExpand(s.id)}
              onToggleEnabled={() => onToggleEnabled(s)}
              onEdit={() => onEdit(s)}
              onDelete={() => onDelete(s.id)}
              onRestart={() => onRestart(s.id)}
            />
          ))
        )}
      </section>

      {servers.length > 0 && (
        // BRIEF · MCP: stats al pie como stat-chips compactos
        // (en lugar de un párrafo plano "0 habilitados · 0 corriendo…").
        // Cada chip lleva ícono propio + número monoespaciado.
        <div className="px-6 pb-6 flex flex-wrap items-center gap-2">
          <StatChip icon="bolt" label="activos" value={enabledCount} />
          <StatChip icon="play" label="corriendo" value={runningCount} />
          <StatChip icon="plug" label="tools registradas" value={toolsCount} />
        </div>
      )}
    </>
  );
}

/* ── Stat chip al pie de la lista ──────────────────────────────────── */

function StatChip({
  icon,
  label,
  value,
}: {
  icon: React.ComponentProps<typeof Icon>["name"];
  label: string;
  value: number;
}) {
  return (
    <span
      className="inline-flex items-center gap-1.5 pl-1.5 pr-2.5 py-1 rounded-full
                 bg-elevated/60 border border-white/[0.06] text-[11px]"
    >
      <span className="grid place-items-center h-5 w-5 rounded-full bg-pri/15 text-pri">
        <Icon name={icon} size={11} />
      </span>
      <span className="font-mono tabular-nums text-text font-medium">{value}</span>
      <span className="text-text-dim uppercase tracking-[0.16em] text-[10px]">{label}</span>
    </span>
  );
}

/* ── Card de un server individual ─────────────────────────────────── */

function ServerCard({
  server,
  expanded,
  onToggleExpand,
  onToggleEnabled,
  onEdit,
  onDelete,
  onRestart,
}: {
  server: MCPServerStatus;
  expanded: boolean;
  onToggleExpand: () => void;
  onToggleEnabled: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onRestart: () => void;
}) {
  // BRIEF · MCP: "deshabilitado" en rojo es alarmista para el estado
  // normal de un server apagado. Lo bajamos a "inactivo" gris-azulado
  // (sem-inactive). Solo `server.error` (failure real del subprocess)
  // se queda en danger.
  const statusTone = !server.enabled
    ? "inactive"
    : server.error
      ? "danger"
      : server.running
        ? "ok"
        : "warn";
  const statusLabel = !server.enabled
    ? "inactivo"
    : server.error
      ? "error"
      : server.running
        ? "corriendo"
        : "detenido";

  return (
    <Surface level={2} className="overflow-hidden">
      {/* header — en mobile stackeamos info arriba y acciones abajo.
          En desktop quedan en una sola row como antes. */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 px-4 py-3">
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <div
            className="grid place-items-center h-9 w-9 rounded-md bg-elevated/60
                          border border-white/[0.05] text-pri shrink-0"
          >
            <Icon name="plug" size={16} />
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <div className="text-sm font-medium tracking-tight text-text truncate">
                {server.id}
              </div>
              <StatusPill tone={statusTone} label={statusLabel} />
              {server.tool_count > 0 && <Badge tone="info">{server.tool_count} tools</Badge>}
            </div>
            <div
              className="text-[11px] text-text-dim truncate font-mono"
              title={`${server.command} ${server.args.join(" ")}`.trim()}
            >
              {shortenCommand(server.command, server.args)}
            </div>
            {server.error && (
              <div className="text-[11px] text-danger mt-1 truncate">{server.error}</div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-1 shrink-0 self-end sm:self-auto">
          <Switch
            on={server.enabled}
            onClick={onToggleEnabled}
            size="sm"
            className={server.enabled ? "" : "opacity-70"}
          />
          <Button
            variant="ghost"
            size="sm"
            icon="orbit"
            onClick={onRestart}
            title="Restart subprocess"
            disabled={!server.enabled}
          >
            Restart
          </Button>
          <Button variant="ghost" size="sm" icon="edit" onClick={onEdit} />
          <Button variant="ghost" size="sm" icon="trash" onClick={onDelete} />
          <Button
            variant="ghost"
            size="sm"
            icon={expanded ? "chevron-down" : "chevron-right"}
            onClick={onToggleExpand}
            title="Ver tools"
          />
        </div>
      </div>

      {/* expanded: comando completo + tools list */}
      {expanded && (
        <div className="border-t border-white/[0.05] bg-sunken/30 px-4 py-3 animate-fade-in space-y-3">
          <div>
            <div className="text-[9px] uppercase tracking-[0.22em] text-text-dim mb-1.5">
              Comando completo
            </div>
            <code className="block text-[11px] font-mono text-text/85 break-all leading-relaxed">
              {server.command}
              {server.args.length > 0 && (
                <span className="text-text-dim"> {server.args.join(" ")}</span>
              )}
            </code>
          </div>
          <div>
            <div className="text-[9px] uppercase tracking-[0.22em] text-text-dim mb-1.5">
              Tools registradas{" "}
              {server.tools.length > 0 && (
                <span className="text-text/60 font-mono">({server.tools.length})</span>
              )}
            </div>
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
                    <span className="font-mono text-text">
                      {server.id}__{t.name}
                    </span>
                    {t.description && <span className="text-text-dim"> · {t.description}</span>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </Surface>
  );
}

/* ── Pill de estado ───────────────────────────────────────────────── */

/* ── Compactador del comando del server (BRIEF · MCP) ─────────────────
   Toma `npx -y @modelcontextprotocol/server-foo` y devuelve solo el
   package name (`@modelcontextprotocol/server-foo`). Si no encuentra un
   "spec" obvio (uvx, pip, etc), cae al binario + último arg.

   Casos cubiertos:
     npx -y @x/y       → @x/y
     uvx mcp-server-x  → mcp-server-x
     node script.js    → node script.js
     python -m foo     → python -m foo
*/
function shortenCommand(cmd: string, args: string[]): string {
  // npm/npx: ignoramos flags y nos quedamos con el primer non-flag arg
  // que suele ser el package name.
  if (/^(npx|npm|pnpm|yarn|bunx|uvx)$/i.test(cmd)) {
    const pkg = args.find((a) => !a.startsWith("-"));
    if (pkg) return pkg;
  }
  // Fallback: comando + un solo arg para no llenar la fila.
  if (args.length === 0) return cmd;
  if (args.length === 1) return `${cmd} ${args[0]}`;
  return `${cmd} ${args[0]} …`;
}

function StatusPill({ tone, label }: { tone: string; label: string }) {
  // BRIEF G3 — el dot codifica el estado; la cápsula queda siempre
  // gris/translúcida (no rojo de fondo) salvo error real.
  const dotColor =
    tone === "ok"
      ? "bg-sem-success shadow-[0_0_8px_rgb(var(--sem-success))]"
      : tone === "danger"
        ? "bg-sem-error"
        : tone === "warn"
          ? "bg-sem-warning"
          : tone === "inactive"
            ? "bg-sem-inactive"
            : "bg-muted";
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full
                     text-[10px] uppercase tracking-[0.16em]
                     border border-white/[0.06] bg-elevated/50 text-text-dim"
    >
      <span className={`h-1.5 w-1.5 rounded-full ${dotColor}`} />
      {label}
    </span>
  );
}
