/**
 * AgentGrid + AgentCard — vista en grilla de agentes disponibles.
 *
 * Agrupa por habilitados / inhabilitados. Click en card abre el chat
 * con ese agente. Botón hover-revealed para editar.
 */

import type { OrchestraAgent } from "@/api/rest";
import { Icon, type IconName } from "@/ui/Icon";
import { Badge } from "@/ui/primitives";

import { agentIdentityVar, compactModelLabel, translateRole, useProviderLabel } from "./types";

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
  // BRIEF · Agentes: cada rol mantiene su hue identitario. Resolvemos
  // el token CSS y dejamos que la card componga alpha por capa
  // (border top, gradiente sutil, icon container, CTA).
  const identity = agentIdentityVar(agent.role, agent.icon);
  const identityRgb = `rgb(var(${identity}))`;
  const identityAlpha = (a: number) => `rgb(var(${identity}) / ${a})`;

  return (
    <button
      onClick={onChat}
      style={{
        animationDelay: `${index * 50}ms`,
        borderTop: `2px solid ${identityAlpha(0.85)}`,
        background: `linear-gradient(180deg, ${identityAlpha(0.07)} 0%, rgb(var(--orion-elevated) / 0.55) 38%)`,
        // El glow del hover usa la variable de identidad — sin esto
        // tendríamos que multiplicar Tailwind classes hardcoded por
        // cada color de rol.
        ["--agent-hover-shadow" as string]: `0 18px 38px -16px ${identityAlpha(0.55)}, 0 0 0 1px ${identityAlpha(0.45)}, 0 0 32px -6px ${identityAlpha(0.45)}`,
      }}
      className="group relative text-left rounded-xl border border-white/[0.06]
                 transition-all duration-300 ease-spring
                 hover:-translate-y-1
                 hover:[box-shadow:var(--agent-hover-shadow)]
                 p-4 animate-fade-in-up overflow-hidden"
    >
      {/* Halo radial detrás del icono cuando el cursor está encima */}
      <span
        aria-hidden
        className="pointer-events-none absolute -top-4 left-4 h-16 w-16 rounded-full opacity-0
                   group-hover:opacity-100 transition-opacity duration-300 blur-2xl"
        style={{ background: `radial-gradient(circle, ${identityAlpha(0.5)}, transparent 70%)` }}
      />
      {/* Header */}
      <div className="flex items-start gap-3 mb-3">
        <span
          className="grid place-items-center h-10 w-10 rounded-xl border transition-colors shrink-0"
          style={{
            background: identityAlpha(0.13),
            borderColor: identityAlpha(0.4),
            color: identityRgb,
            boxShadow: `0 0 14px -4px ${identityAlpha(0.55)}`,
          }}
        >
          <Icon name={(agent.icon as IconName) || "circle"} size={18} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            {/* BRIEF G4: rol en español. translateRole respeta roles
                custom del usuario (los reconocidos los traduce). */}
            <h3 className="text-sm font-semibold text-text truncate">
              {translateRole(agent.role)}
            </h3>
            {!agent.enabled && <Badge tone="inactive">off</Badge>}
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

      {/* Footer: provider + model compactos + status.
          BRIEF: "Gemini · gemini-2.5-flash" → ícono + "Flash 2.5".
          BRIEF G3: "no disponible" usa sem-inactive (gris azulado),
          NUNCA warn ni danger. Solo errores reales son rojos.
          CTA "Activar →" en lugar de "Chat →" — más intencional para
          un agente autónomo. */}
      <div className="flex items-center gap-2 pt-3 border-t border-white/[0.05]">
        <span
          className={`h-1.5 w-1.5 rounded-full shrink-0 ${
            agent.available
              ? "bg-sem-live shadow-[0_0_6px_rgb(var(--sem-live))]"
              : "bg-sem-inactive"
          }`}
          title={agent.available ? "Disponible" : "En tarea"}
        />
        <span
          className="text-[10px] text-text-dim truncate flex-1 font-mono"
          title={`${useProviderLabel(agent.provider)} · ${agent.model}`}
        >
          {useProviderLabel(agent.provider)} · {compactModelLabel(agent.model)}
        </span>
        <span
          className="text-[10px] font-medium transition-opacity opacity-80 group-hover:opacity-100"
          style={{ color: identityRgb }}
        >
          Activar →
        </span>
      </div>
    </button>
  );
}
