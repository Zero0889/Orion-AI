/**
 * MemoryPanel — Memoria de largo plazo agrupada por categoría.
 *
 * Categorías: identity | preferences | projects | relationships |
 * wishes | notes (las mismas que define memory_manager.py).
 *
 * Cada entrada (key → value) se puede editar inline, borrar, y crear
 * nuevas. Refresca al recibir bus.event memory.updated.
 */

import { useEffect, useMemo, useState } from "react";

import { api, type MemoryShape, type MemoryCategory } from "@/api/rest";
import { useOrionStore } from "@/stores/orion";

const CATEGORIES: { id: MemoryCategory; label: string; description: string }[] = [
  { id: "identity",      label: "Identidad",     description: "Nombre, ciudad, trabajo…" },
  { id: "preferences",   label: "Preferencias",  description: "Gustos, hobbies, comida favorita…" },
  { id: "projects",      label: "Proyectos",     description: "Cosas en las que estás trabajando" },
  { id: "relationships", label: "Relaciones",    description: "Familia, amigos, colegas" },
  { id: "wishes",        label: "Deseos",        description: "Planes y aspiraciones futuras" },
  { id: "notes",         label: "Notas",         description: "Hábitos, horario, cualquier otra cosa" },
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

  const entries = useMemo(() => {
    const cat = mem[tab] ?? {};
    return Object.entries(cat).map(([key, entry]) => ({ key, ...entry }));
  }, [mem, tab]);

  async function save(key: string, value: string) {
    const v = value.trim();
    if (!v) return;
    try { await api.putMemory(tab, key, v); }
    catch (e) { setError(String(e)); }
  }

  async function addNew() {
    const k = newKey.trim().replace(/\s+/g, "_").toLowerCase();
    const v = newVal.trim();
    if (!k || !v) return;
    try {
      await api.putMemory(tab, k, v);
      setNewKey(""); setNewVal("");
    } catch (e) { setError(String(e)); }
  }

  async function remove(key: string) {
    if (!confirm(`¿Borrar ${tab}/${key}?`)) return;
    try { await api.deleteMemory(tab, key); }
    catch (e) { setError(String(e)); }
  }

  const activeCat = CATEGORIES.find((c) => c.id === tab)!;

  return (
    <div className="flex flex-col h-full">
      <header className="px-6 py-4 border-b border-border-b">
        <h2 className="text-sm uppercase tracking-[0.3em] text-text-dim">Memoria</h2>
        <p className="text-xs text-text-dim/70 mt-1">
          Lo que Orion sabe sobre ti, organizado por categoría.
        </p>
      </header>

      {/* Tabs */}
      <div className="flex gap-1 px-4 py-2 border-b border-border-b bg-panel overflow-x-auto scrollbar-thin">
        {CATEGORIES.map((c) => (
          <button
            key={c.id}
            onClick={() => setTab(c.id)}
            className={`text-xs px-3 py-1.5 rounded-md whitespace-nowrap border transition
              ${tab === c.id
                ? "bg-pri-dim/30 border-pri text-text"
                : "bg-transparent border-transparent text-text-dim hover:border-border-b"}`}
          >
            {c.label}
            <span className="ml-2 text-text-dim">
              {Object.keys(mem[c.id] ?? {}).length}
            </span>
          </button>
        ))}
      </div>

      <p className="px-6 pt-3 text-xs italic text-text-dim">{activeCat.description}</p>

      {error && (
        <div className="mx-4 mt-3 p-2 text-xs rounded border border-pri bg-pri/10 text-pri">
          {error}
        </div>
      )}

      {/* Entradas existentes */}
      <div className="flex-1 overflow-y-auto scrollbar-thin p-4 flex flex-col gap-2">
        {entries.length === 0 && (
          <div className="text-center text-text-dim text-sm italic mt-6">
            Sin entradas en esta categoría todavía.
          </div>
        )}
        {entries.map((e) => (
          <MemoryRow
            key={e.key}
            entryKey={e.key}
            value={String(e.value ?? "")}
            updated={e.updated}
            onSave={(v) => save(e.key, v)}
            onDelete={() => remove(e.key)}
          />
        ))}
      </div>

      {/* Nueva entrada */}
      <div className="p-3 border-t border-border-b bg-panel">
        <div className="flex gap-2">
          <input
            type="text"
            value={newKey}
            onChange={(e) => setNewKey(e.target.value)}
            placeholder="clave (snake_case)"
            className="w-40 rounded-md bg-panel2 border border-border-b
                       px-3 py-2 text-sm placeholder-text-dim
                       focus:outline-none focus:border-pri"
          />
          <input
            type="text"
            value={newVal}
            onChange={(e) => setNewVal(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") addNew(); }}
            placeholder="valor"
            className="flex-1 rounded-md bg-panel2 border border-border-b
                       px-3 py-2 text-sm placeholder-text-dim
                       focus:outline-none focus:border-pri"
          />
          <button
            onClick={addNew}
            disabled={!newKey.trim() || !newVal.trim()}
            className="rounded-md bg-pri text-bg text-sm font-medium px-4 py-2
                       disabled:opacity-30 hover:brightness-110 transition"
          >
            Guardar
          </button>
        </div>
      </div>
    </div>
  );
}

interface RowProps {
  entryKey: string;
  value:    string;
  updated?: string;
  onSave:   (v: string) => void;
  onDelete: () => void;
}

function MemoryRow({ entryKey, value, updated, onSave, onDelete }: RowProps) {
  const [editing, setEditing] = useState(false);
  const [draft,   setDraft]   = useState(value);

  useEffect(() => { setDraft(value); }, [value]);

  return (
    <div className="group rounded-lg border border-border-b bg-panel2 px-3 py-2 hover:border-pri/40 transition">
      <div className="flex items-center justify-between gap-3">
        <code className="text-xs text-acc font-mono shrink-0">{entryKey}</code>
        {editing ? (
          <input
            value={draft}
            autoFocus
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => { onSave(draft); setEditing(false); }}
            onKeyDown={(e) => {
              if (e.key === "Enter") { onSave(draft); setEditing(false); }
              if (e.key === "Escape") { setDraft(value); setEditing(false); }
            }}
            className="flex-1 bg-panel border border-pri rounded px-2 py-1 text-sm focus:outline-none"
          />
        ) : (
          <button
            onClick={() => setEditing(true)}
            className="flex-1 text-left text-sm hover:text-pri transition cursor-text"
          >
            {value}
          </button>
        )}
        <button
          onClick={onDelete}
          className="opacity-0 group-hover:opacity-100 text-text-dim hover:text-pri transition"
          title="Borrar"
        >×</button>
      </div>
      {updated && (
        <div className="text-[10px] text-text-dim mt-1">{updated}</div>
      )}
    </div>
  );
}
