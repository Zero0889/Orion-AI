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
        <div className="px-6 pb-6 text-[11px] text-text-dim">
          {enabledCount} habilitados · {runningCount} corriendo · {toolsCount} tools registradas
        </div>
      )}
    </>
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
  const statusTone = !server.enabled
    ? "muted"
    : server.error
      ? "danger"
      : server.running
        ? "ok"
        : "warn";
  const statusLabel = !server.enabled
    ? "deshabilitado"
    : server.error
      ? "error"
      : server.running
        ? "corriendo"
        : "detenido";

  return (
    <Surface level={2} className="overflow-hidden">
      {/* header */}
      <div className="flex items-center gap-3 px-4 py-3">
        <div
          className="grid place-items-center h-9 w-9 rounded-md bg-elevated/60
                        border border-white/[0.05] text-pri shrink-0"
        >
          <Icon name="plug" size={16} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="text-sm font-medium tracking-tight text-text truncate">{server.id}</div>
            <StatusPill tone={statusTone} label={statusLabel} />
            {server.tool_count > 0 && <Badge tone="info">{server.tool_count} tools</Badge>}
          </div>
          <div className="text-[11px] text-text-dim truncate font-mono">
            {server.command}
            {server.args.length > 0 && <span className="text-muted"> {server.args.join(" ")}</span>}
          </div>
          {server.error && (
            <div className="text-[11px] text-danger mt-1 truncate">{server.error}</div>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0">
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
                  <span className="font-mono text-text">
                    {server.id}__{t.name}
                  </span>
                  {t.description && <span className="text-text-dim"> · {t.description}</span>}
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
    tone === "ok"
      ? "bg-ok shadow-[0_0_8px_rgb(var(--orion-ok))]"
      : tone === "danger"
        ? "bg-danger"
        : tone === "warn"
          ? "bg-warn"
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
