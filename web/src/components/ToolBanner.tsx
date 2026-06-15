/**
 * ToolBanner — chip sutil que aparece arriba del chat cuando hay una
 * tool en ejecución (o un agente background activo). Permite saber
 * exactamente QUÉ está haciendo Orion en este instante, en lugar de
 * solo ver "PENSANDO" sin más detalle.
 *
 * Visual: una banda de altura mínima con icono animado + nombre legible
 * de la tool + tiempo transcurrido. Se desliza en/out con fade.
 *
 * Prioridad de display:
 *   1. Tool activa (más reciente, más específica)
 *   2. Agente con tarea running
 *   3. Nada → no se renderiza
 */

import { useEffect, useState } from "react";

import { prettyToolName } from "@/lib/toolLabels";
import { useInteractionStore } from "@/stores/interaction";

export function ToolBanner() {
  const tool  = useInteractionStore((s) => s.tool);
  const agent = useInteractionStore((s) => s.agent);

  // Reloj para mostrar segundos transcurridos sin re-renderizar todo
  // el componente padre (el chat).
  const [, tick] = useState(0);
  useEffect(() => {
    if (!tool && !agent) return;
    const id = window.setInterval(() => tick((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [tool, agent]);

  if (tool) {
    const { label, icon } = prettyToolName(tool.name);
    const seconds = Math.max(0, Math.floor((Date.now() - tool.startedAt) / 1000));
    return (
      <div className="mx-auto max-w-3xl px-4 md:px-8 pt-3 animate-fade-in-up">
        <div
          className="relative flex items-center gap-3 rounded-xl
                     border border-warn/50 bg-gradient-to-r from-warn/[0.18] to-warn/[0.08]
                     px-4 py-2.5 backdrop-blur-sm
                     shadow-[0_0_24px_-6px_rgb(251_191_36_/_0.45)]"
        >
          {/* Borde izquierdo brillante para que destaque incluso si se baja la opacidad */}
          <span className="absolute left-0 top-0 bottom-0 w-[3px] rounded-l-xl bg-warn animate-pulse-soft" />
          <span className="text-xl leading-none">{icon}</span>
          <div className="min-w-0 flex-1">
            <div className="text-[12px] uppercase tracking-[0.22em] text-warn font-semibold">
              {label}
            </div>
            <div className="text-[11px] text-text-dim font-mono mt-0.5 truncate">
              {tool.name}
              {Object.keys(tool.args).length > 0 && (
                <>
                  {" · "}
                  {Object.entries(tool.args).slice(0, 2).map(([k, v]) => (
                    <span key={k} className="mr-2">
                      <span className="opacity-60">{k}=</span>
                      <span>{String(v).slice(0, 28)}</span>
                    </span>
                  ))}
                </>
              )}
            </div>
          </div>
          <div className="shrink-0 flex items-center gap-2 text-warn">
            <ProgressDots />
            <span className="text-[11px] uppercase tracking-[0.22em] font-mono tabular-nums">
              {seconds}s
            </span>
          </div>
        </div>
      </div>
    );
  }

  if (agent && (agent.status === "running" || agent.status === "pending")) {
    const seconds = Math.max(0, Math.floor((Date.now() - agent.updatedAt) / 1000));
    return (
      <div className="mx-auto max-w-3xl px-4 md:px-8 pt-3 animate-fade-in-up">
        <div className="flex items-center gap-3 rounded-xl border border-pink-400/30 bg-pink-400/[0.05] px-3.5 py-2 backdrop-blur-sm">
          <span className="text-lg leading-none">🎼</span>
          <div className="min-w-0 flex-1">
            <div className="text-[11px] uppercase tracking-[0.22em] text-pink-300 font-medium">
              Agente {agent.status === "pending" ? "en cola" : "trabajando"}
            </div>
            <div className="text-[12px] text-text mt-0.5 truncate">
              {agent.lastSpeech ?? agent.goal ?? "Procesando…"}
            </div>
          </div>
          <div className="shrink-0 flex items-center gap-2">
            <ProgressDots />
            <span className="text-[10px] uppercase tracking-[0.22em] text-pink-300/80 font-mono tabular-nums">
              {seconds}s
            </span>
          </div>
        </div>
      </div>
    );
  }

  return null;
}

function ProgressDots() {
  return (
    <span className="flex items-center gap-1">
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-30 animate-pulse-soft" style={{ animationDelay: "0s" }} />
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-60 animate-pulse-soft" style={{ animationDelay: "0.2s" }} />
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-90 animate-pulse-soft" style={{ animationDelay: "0.4s" }} />
    </span>
  );
}
