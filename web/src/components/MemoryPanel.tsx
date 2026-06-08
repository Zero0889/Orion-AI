/**
 * MemoryPanel — long-term memory across categories.
 *
 * Premium tabbed surface, inline editing, fresh card design.
 */

import { useEffect, useMemo, useState } from "react";

import { api, type MemoryShape, type MemoryCategory } from "@/api/rest";
import { useOrionStore } from "@/stores/orion";
import { Icon, type IconName } from "@/ui/Icon";
import { Badge, Button, Empty, SectionHeader, Surface } from "@/ui/primitives";

const CATEGORIES: { id: MemoryCategory; label: string; description: string; icon: IconName }[] = [
  { id: "identity",      label: "Identidad",    description: "Nombre, ciudad, trabajo, lo esencial",     icon: "shield"   },
  { id: "preferences",   label: "Preferencias", description: "Gustos, hobbies, ritmos diarios",          icon: "sparkles" },
  { id: "projects",      label: "Proyectos",    description: "Cosas en las que estás trabajando ahora",  icon: "cpu"      },
  { id: "relationships", label: "Relaciones",   description: "Familia, amistades, compañeros",           icon: "chat"     },
  { id: "wishes",        label: "Deseos",       description: "Planes, ambiciones, qué viene después",    icon: "bolt"     },
  { id: "notes",         label: "Notas",        description: "Hábitos, ideas, cualquier otra cosa",      icon: "notes"    },
];

const EMPTY_MEM: MemoryShape = {
  identity: {}, preferences: {}, projects: {},
  relationships: {}, wishes: {}, notes: {},
};

export function MemoryPanel() {
  const rev = useOrionStore((s) => s.rev.memory);
  const [mem,   setMem]   = useState<MemoryShape>(EMPTY_MEM);
  const [tab,   setTab]   = useState<MemoryCategory>("identity");
  const [error, setError] = useState<string | null>(null);
  const [newKey, setNewKey] = useState("");
  const [newVal, setNewVal] = useState("");

  useEffect(() => {
    let alive = true;
    api.getMemory()
      .then((m) => { if (alive) { setMem(m); setError(null); } })
      .catch((e) => { if (alive) setError(String(e)); });
    return () => { alive = false; };
  }, [rev]);

  const entries = useMemo(
    () => Object.entries(mem[tab] ?? {}).map(([key, entry]) => ({ key, ...entry })),
    [mem, tab],
  );

  async function save(key: string, value: string) {
    const v = value.trim(); if (!v) return;
    try { await api.putMemory(tab, key, v); }
    catch (e) { setError(String(e)); }
  }
  async function addNew() {
    const k = newKey.trim().replace(/\s+/g, "_").toLowerCase();
    const v = newVal.trim();
    if (!k || !v) return;
    try { await api.putMemory(tab, k, v); setNewKey(""); setNewVal(""); }
    catch (e) { setError(String(e)); }
  }
  async function remove(key: string) {
    if (!confirm(`¿Borrar ${tab}/${key}?`)) return;
    try { await api.deleteMemory(tab, key); }
    catch (e) { setError(String(e)); }
  }

  const active = CATEGORIES.find((c) => c.id === tab)!;
  const totalEntries = Object.values(mem).reduce((acc, c) => acc + Object.keys(c).length, 0);

  return (
    <div className="flex flex-col h-full">
      <SectionHeader
        eyebrow="Conocimiento"
        title="Memoria"
        hint="Lo que Orion sabe sobre ti, organizado por categoría."
        action={<Badge tone="neutral">{totalEntries} entradas</Badge>}
      />

      {/* tabs as cards */}
      <nav className="px-6 py-4 border-b border-white/[0.06] grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
        {CATEGORIES.map((c) => {
          const n = Object.keys(mem[c.id] ?? {}).length;
          const isActive = tab === c.id;
          return (
            <button
              key={c.id}
              onClick={() => setTab(c.id)}
              className={[
                "group relative rounded-lg px-3 py-2.5 text-left border transition-all duration-200 ease-out-expo",
                isActive
                  ? "bg-pri/10 border-pri/35 text-text shadow-glow-soft"
                  : "bg-elevated/40 border-white/[0.05] text-text-dim hover:text-text hover:border-white/[0.12]",
              ].join(" ")}
            >
              <div className="flex items-center justify-between mb-1">
                <Icon name={c.icon} size={14} className={isActive ? "text-pri" : "text-text-dim"} />
                <span className={`text-[10px] font-mono tabular-nums ${isActive ? "text-pri" : "text-muted"}`}>{n}</span>
              </div>
              <div className="text-xs font-medium tracking-tight">{c.label}</div>
            </button>
          );
        })}
      </nav>

      <p className="px-6 pt-4 text-xs italic text-text-dim flex items-center gap-2">
        <Icon name={active.icon} size={13} className="text-pri/70" /> {active.description}
      </p>

      {error && (
        <div className="mx-6 mt-3 flex items-start gap-2 p-3 rounded-md border border-danger/30 bg-danger/10 text-xs text-danger">
          <Icon name="alert" size={14} className="mt-0.5 shrink-0" /><span>{error}</span>
        </div>
      )}

      <div className="flex-1 overflow-y-auto scrollbar-thin px-6 py-4">
        {entries.length === 0
          ? <Empty icon={active.icon} title="Sin entradas en esta categoría" hint="Añade la primera abajo o deja que Orion la guarde durante una conversación." />
          : (
            <div className="flex flex-col gap-2">
              {entries.map((e, i) => (
                <Row
                  key={e.key} entryKey={e.key} value={String(e.value ?? "")}
                  updated={e.updated} delay={i * 25}
                  onSave={(v) => save(e.key, v)} onDelete={() => remove(e.key)}
                />
              ))}
            </div>
          )
        }
      </div>

      {/* composer */}
      <div className="px-6 py-3 border-t border-white/[0.06] bg-bg/70">
        <div className="flex gap-2">
          <input
            type="text"
            value={newKey}
            onChange={(e) => setNewKey(e.target.value)}
            placeholder="clave (snake_case)"
            className="w-44 rounded-md bg-elevated border border-white/[0.08]
                       px-3 h-9 text-sm placeholder-muted
                       focus:outline-none focus:border-pri/40"
          />
          <input
            type="text"
            value={newVal}
            onChange={(e) => setNewVal(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") addNew(); }}
            placeholder="valor"
            className="flex-1 rounded-md bg-elevated border border-white/[0.08]
                       px-3 h-9 text-sm placeholder-muted
                       focus:outline-none focus:border-pri/40"
          />
          <Button
            variant="primary" size="md" icon="plus"
            onClick={addNew}
            disabled={!newKey.trim() || !newVal.trim()}
          >
            Guardar
          </Button>
        </div>
      </div>
    </div>
  );
}

function Row({
  entryKey, value, updated, delay, onSave, onDelete,
}: {
  entryKey: string; value: string; updated?: string; delay?: number;
  onSave: (v: string) => void; onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft,   setDraft]   = useState(value);
  useEffect(() => { setDraft(value); }, [value]);

  return (
    <Surface
      level={2}
      className="group px-3.5 py-2.5 animate-fade-in-up"
      style={{ animationDelay: `${delay ?? 0}ms` }}
    >
      <div className="flex items-center justify-between gap-3">
        <code className="shrink-0 text-xs font-mono text-acc/90 tracking-tight max-w-[28%] truncate">
          {entryKey}
        </code>
        {editing ? (
          <input
            value={draft}
            autoFocus
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => { onSave(draft); setEditing(false); }}
            onKeyDown={(e) => {
              if (e.key === "Enter")  { onSave(draft); setEditing(false); }
              if (e.key === "Escape") { setDraft(value); setEditing(false); }
            }}
            className="flex-1 bg-surface border border-pri/40 rounded px-2 py-1 text-sm focus:outline-none"
          />
        ) : (
          <button
            onClick={() => setEditing(true)}
            className="flex-1 text-left text-sm text-text hover:text-pri transition-colors cursor-text"
          >
            {value}
          </button>
        )}
        <button
          onClick={onDelete}
          title="Borrar"
          className="h-7 w-7 grid place-items-center rounded-md text-text-dim
                     opacity-0 group-hover:opacity-100
                     hover:text-danger hover:bg-danger/10 transition-all"
        >
          <Icon name="close" size={14} />
        </button>
      </div>
      {updated && <div className="text-[10px] uppercase tracking-[0.16em] text-muted mt-1">{updated}</div>}
    </Surface>
  );
}
