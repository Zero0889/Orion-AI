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
 * Layout: este archivo es solo el **shell** (header, tabs, state
 * compartido). Cada pestaña vive en su propio archivo:
 *
 *   - InstalledTab.tsx    — lista de servers configurados
 *   - CuratedTab.tsx      — recipes oficiales con install one-click
 *   - ExploreTab.tsx      — búsqueda en el registry público
 *   - ServerFormModal.tsx — modal de crear/editar (compartido)
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";

import {
  api,
  type MCPRegistryPackage,
  type MCPRegistryServer,
  type MCPServerStatus,
} from "@/api/rest";
import { QUERY_KEYS } from "@/query/keys";
import { Icon } from "@/ui/Icon";
import { Badge, Button, SectionHeader } from "@/ui/primitives";

import { CuratedTab } from "./CuratedTab";
import { ExploreTab } from "./ExploreTab";
import { InstalledTab } from "./InstalledTab";
import { ServerFormModal } from "./ServerFormModal";
import type { PrefillFromRegistry, Tab } from "./types";

export function MCPPanel() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("installed");
  const [mutationError, setMutationError] = useState<string | null>(null);

  // modal
  const [editing, setEditing] = useState<MCPServerStatus | undefined>(undefined);
  const [prefill, setPrefill] = useState<PrefillFromRegistry | undefined>(undefined);
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

  // Server-state via TanStack Query. MCP no tiene eventos WS (no hay
  // bridge), así que la invalidación viene SOLO de las mutaciones
  // (delete/restart/toggle/update).
  const {
    data: servers = [],
    isLoading: loading,
    error: queryError,
  } = useQuery<MCPServerStatus[]>({
    queryKey: QUERY_KEYS.mcpServers,
    queryFn: () => api.mcpListServers(),
  });
  const error = mutationError ?? (queryError ? String(queryError) : null);
  const setError = setMutationError;

  const refetch = useCallback(
    () => queryClient.invalidateQueries({ queryKey: QUERY_KEYS.mcpServers }),
    [queryClient],
  );

  async function handleDelete(id: string) {
    if (!confirm(`¿Borrar el server MCP '${id}'? Se detiene y se quita del config.`)) return;
    try {
      await api.mcpDeleteServer(id);
      await refetch();
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleRestart(id: string) {
    try {
      await api.mcpRestartServer(id);
      await refetch();
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleToggleEnabled(s: MCPServerStatus) {
    // Optimismo: pintamos el switch instantáneo via setQueryData. Si el
    // PUT falla, invalidateQueries refetchea y revierte al estado real.
    queryClient.setQueryData<MCPServerStatus[]>(QUERY_KEYS.mcpServers, (prev) =>
      (prev ?? []).map((x) => (x.id === s.id ? { ...x, enabled: !s.enabled } : x)),
    );
    try {
      await api.mcpUpdateServer(s.id, {
        command: s.command,
        args: s.args,
        env: s.env,
        enabled: !s.enabled,
        cwd: s.cwd,
        startup_timeout: s.startup_timeout,
        call_timeout: s.call_timeout,
      });
    } catch (e) {
      setError(String(e));
    }
    await refetch();
  }

  async function handleReloadAll() {
    try {
      await api.mcpReload();
      refetch();
    } catch (e) {
      setError(String(e));
    }
  }

  function openCreate() {
    setEditing(undefined);
    setPrefill(undefined);
    setModalOpen(true);
  }
  function openEdit(s: MCPServerStatus) {
    setEditing(s);
    setPrefill(undefined);
    setModalOpen(true);
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
        command: pkg.command,
        args: pkg.args,
        env: Object.fromEntries(pkg.env_required.map((e) => [e.name, ""])),
        enabled: true,
      },
      envRequired: pkg.env_required,
    });
    setModalOpen(true);
  }

  const installedIds = new Set(servers.map((s) => s.id));
  const enabledCount = servers.filter((s) => s.enabled).length;
  const runningCount = servers.filter((s) => s.running).length;
  const toolsCount = servers.reduce((acc, s) => acc + s.tool_count, 0);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <SectionHeader
        eyebrow="Sistema"
        title="MCP"
        hint="Servidores externos que extienden a ORION con tools adicionales."
        action={
          <div className="flex items-center gap-2">
            <div className="hidden md:flex items-center gap-1.5">
              <Badge tone="info" dot>
                {servers.length} servers
              </Badge>
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
      {/* overflow-x-auto + shrink-0 evita que el último tab se corte
          ("Exp regi…") cuando la suma de tabs excede el viewport mobile. */}
      <div
        className="px-4 sm:px-6 pt-3 flex items-center gap-1 border-b border-white/[0.05]
                   overflow-x-auto scrollbar-thin"
      >
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
          <div
            className="mx-6 mt-3 flex items-start gap-2 p-3 rounded-md
                          border border-danger/30 bg-danger/10 text-xs text-danger animate-fade-in"
          >
            <Icon name="alert" size={14} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {tab === "installed" && (
          <InstalledTab
            servers={servers}
            loading={loading}
            expanded={expanded}
            enabledCount={enabledCount}
            runningCount={runningCount}
            toolsCount={toolsCount}
            onToggleExpand={toggleExpand}
            onToggleEnabled={handleToggleEnabled}
            onEdit={openEdit}
            onDelete={handleDelete}
            onRestart={handleRestart}
            onOpenCreate={openCreate}
            onSwitchToExplore={() => setTab("explore")}
          />
        )}
        {tab === "curated" && (
          <CuratedTab
            installedIds={installedIds}
            onInstalled={() => {
              refetch();
              setTab("installed");
            }}
            onError={(e) => setError(String(e))}
          />
        )}
        {tab === "explore" && (
          <ExploreTab
            installedIds={installedIds}
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
        onSaved={() => {
          setModalOpen(false);
          refetch();
          setTab("installed");
        }}
        onError={(e) => setError(String(e))}
      />
    </div>
  );
}

/* ── Tab button ────────────────────────────────────────────────────── */

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={[
        "relative inline-flex items-center gap-1.5 px-3 h-8 text-xs font-medium shrink-0 whitespace-nowrap",
        "rounded-t-md transition-colors duration-150",
        active ? "text-text bg-elevated/40" : "text-text-dim hover:text-text hover:bg-white/[0.03]",
      ].join(" ")}
    >
      {children}
      {active && (
        <span
          aria-hidden
          className="absolute left-2 right-2 -bottom-px h-[2px] rounded-full bg-pri
                         shadow-[0_0_8px_rgb(var(--orion-pri)/0.6)]"
        />
      )}
    </button>
  );
}
