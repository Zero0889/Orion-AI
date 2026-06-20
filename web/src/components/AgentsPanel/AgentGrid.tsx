/**
 * AgentGrid + AgentCard — vista en grilla de agentes disponibles.
 *
 * Agrupa por habilitados / inhabilitados. Click en card abre el chat
 * con ese agente. Botón hover-revealed para editar.
 */

import type { OrchestraAgent } from "@/api/rest";
import { Icon, type IconName } from "@/ui/Icon";
import { Badge } from "@/ui/primitives";

import { agentIconTone, useProviderLabel } from "./types";

export function AgentGrid({
  agents,
  onChat,
  onEdit,
}: {
  agents: OrchestraAgent[];
  onChat: (a: OrchestraAgent) => void;
  onEdit: (a: OrchestraAgent) => void;
}) {
  const enabled = agents.filter((a) => a.enabled);
  const disabled = agents.filter((a) => !a.enabled);

  return (
    <div className="overflow-y-auto scrollbar-thin h-full px-6 py-6">
      {/* Enabled agents */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 mb-6">
        {enabled.map((a, i) => (
          <AgentCard
            key={a.id}
            agent={a}
            index={i}
            onChat={() => onChat(a)}
            onEdit={() => onEdit(a)}
          />
        ))}
      </div>

      {/* Disabled agents */}
      {disabled.length > 0 && (
        <>
          <div className="divider-label mb-3">Inhabilitados</div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 opacity-60">
            {disabled.map((a, i) => (
              <AgentCard
                key={a.id}
                agent={a}
                index={i}
                onChat={() => onChat(a)}
                onEdit={() => onEdit(a)}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/* ─── Agent Card ────────────────────────────────────────────────────── */

function AgentCard({
  agent,
  index,
  onChat,
  onEdit,
}: {
  agent: OrchestraAgent;
  index: number;
  onChat: () => void;
  onEdit: () => void;
}) {
  const tone = agentIconTone(agent.icon);

  return (
    <button
      onClick={onChat}
      style={{ animationDelay: `${index * 50}ms` }}
      className="group relative text-left rounded-xl border border-white/[0.06]
                 bg-elevated/40 hover:bg-elevated/80 hover:border-pri/30
                 hover:shadow-glow-soft transition-all duration-200 ease-out-expo
                 p-4 animate-fade-in-up"
    >
      {/* Header */}
      <div className="flex items-start gap-3 mb-3">
        <span
          className={`grid place-items-center h-10 w-10 rounded-xl bg-white/[0.04] ${tone}
                         group-hover:bg-pri/15 group-hover:text-pri transition-colors`}
        >
          <Icon name={(agent.icon as IconName) || "circle"} size={18} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-text truncate">{agent.role}</h3>
            {!agent.enabled && <Badge tone="neutral">off</Badge>}
          </div>
          <div className="text-[10px] uppercase tracking-[0.16em] text-muted font-mono mt-0.5">
            {agent.id}
          </div>
        </div>
        {/* Edit button */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            onEdit();
          }}
          title="Editar agente"
          className="h-7 w-7 grid place-items-center rounded-md text-text-dim
                     hover:text-text hover:bg-white/[0.06] transition-colors opacity-0
                     group-hover:opacity-100"
        >
          <Icon name="settings" size={13} />
        </button>
      </div>

      {/* Description */}
      <p className="text-xs text-text-dim leading-relaxed mb-3 line-clamp-2">
        {agent.description || "Sin descripción"}
      </p>

      {/* Footer: provider + model + status */}
      <div className="flex items-center gap-2 pt-3 border-t border-white/[0.05]">
        <span
          className={`h-1.5 w-1.5 rounded-full shrink-0 ${
            agent.available ? "bg-ok shadow-[0_0_6px_rgb(var(--orion-ok))]" : "bg-warn"
          }`}
        />
        <span className="text-[10px] text-text-dim truncate flex-1">
          {useProviderLabel(agent.provider)} · {agent.model}
        </span>
        <span className="text-[9px] text-muted">Chat →</span>
      </div>
    </button>
  );
}
