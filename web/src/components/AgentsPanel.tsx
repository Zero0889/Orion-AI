/**
 * AgentsPanel — cola de tareas del agente autónomo (TaskQueue).
 *
 * Lista del estado vivo, formulario para enviar una tarea nueva, botón
 * para cancelar las que aún no terminaron. Refresca al recibir
 * `agent.task` (rev.agent).
 */

import { useEffect, useState } from "react";

import { api, type AgentTask } from "@/api/rest";
import { useOrionStore } from "@/stores/orion";

const STATUS_STYLES: Record<AgentTask["status"], string> = {
  pending:   "text-text-dim",
  running:   "text-acc",
  completed: "text-pri",
  failed:    "text-pri",
  cancelled: "text-text-dim line-through",
};

const STATUS_LABEL: Record<AgentTask["status"], string> = {
  pending:   "Pendiente",
  running:   "En curso",
  completed: "Completada",
  failed:    "Falló",
  cancelled: "Cancelada",
};

export function AgentsPanel() {
  const rev = useOrionStore((s) => s.rev.agent);
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [goal,  setGoal]  = useState("");
  const [priority, setPriority] = useState<"low" | "normal" | "high">("normal");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.listTasks()
      .then((ts) => { if (alive) setTasks(ts); })
      .catch((e) => { if (alive) setError(String(e)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [rev]);

  async function submit() {
    const g = goal.trim();
    if (!g) return;
    try {
      await api.submitTask(g, priority);
      setGoal("");
    } catch (e) { setError(String(e)); }
  }

  async function cancel(id: string) {
    try { await api.cancelTask(id); }
    catch (e) { setError(String(e)); }
  }

  // Más recientes primero
  const sorted = [...tasks].sort((a, b) => {
    // Sin timestamps en el payload por ahora; usamos orden estable.
    return a.task_id < b.task_id ? 1 : -1;
  });

  return (
    <div className="flex flex-col h-full">
      <header className="px-6 py-4 border-b border-border-b">
        <h2 className="text-sm uppercase tracking-[0.3em] text-text-dim">Agentes</h2>
        <p className="text-xs text-text-dim/70 mt-1">
          Cola de tareas autónomas. Las tareas se ejecutan en background
          y avisan por voz cuando terminan.
        </p>
      </header>

      {/* Submit */}
      <div className="p-4 border-b border-border-b bg-panel flex gap-2 items-end">
        <textarea
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="Describe la tarea que quieres que haga Orion…"
          rows={2}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); submit(); }
          }}
          className="flex-1 resize-none rounded-md bg-panel2 border border-border-b
                     px-3 py-2 text-sm placeholder-text-dim
                     focus:outline-none focus:border-pri"
        />
        <select
          value={priority}
          onChange={(e) => setPriority(e.target.value as typeof priority)}
          className="rounded-md bg-panel2 border border-border-b px-2 py-2 text-xs"
        >
          <option value="low">Baja</option>
          <option value="normal">Normal</option>
          <option value="high">Alta</option>
        </select>
        <button
          onClick={submit}
          disabled={!goal.trim()}
          className="rounded-md bg-pri text-bg text-sm font-medium px-4 py-2
                     disabled:opacity-30 hover:brightness-110 transition"
        >
          Lanzar
        </button>
      </div>

      {error && (
        <div className="mx-4 mt-3 p-2 text-xs rounded border border-pri bg-pri/10 text-pri">
          {error}
        </div>
      )}

      {/* Lista */}
      <div className="flex-1 overflow-y-auto scrollbar-thin p-4 flex flex-col gap-2">
        {loading && tasks.length === 0 && (
          <p className="text-center text-text-dim text-sm">Cargando…</p>
        )}
        {!loading && tasks.length === 0 && (
          <p className="text-center text-text-dim text-sm italic mt-6">
            Sin tareas. Lanza la primera arriba.
          </p>
        )}
        {sorted.map((t) => {
          const stoppable = t.status === "pending" || t.status === "running";
          return (
            <article
              key={t.task_id}
              className="group rounded-lg border border-border-b bg-panel2 p-3
                         hover:border-pri/40 transition"
            >
              <header className="flex items-center justify-between text-[10px] uppercase tracking-widest mb-1">
                <span className="text-text-dim font-mono">{t.task_id}</span>
                <div className="flex items-center gap-3">
                  <span className={STATUS_STYLES[t.status]}>
                    {STATUS_LABEL[t.status]}
                  </span>
                  {stoppable && (
                    <button
                      onClick={() => cancel(t.task_id)}
                      className="text-text-dim hover:text-pri opacity-0 group-hover:opacity-100"
                      title="Cancelar"
                    >×</button>
                  )}
                </div>
              </header>
              <p className="text-sm leading-relaxed">{t.goal}</p>
              {typeof t.error === "string" && t.error && (
                <p className="text-xs text-pri mt-1">{t.error}</p>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}
