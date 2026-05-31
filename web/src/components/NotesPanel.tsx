/**
 * NotesPanel — CRUD de notas rápidas.
 *
 * Lista de notas ordenadas por (pinned desc, updated desc).
 * Crear desde un textarea + botón. Editar inline (click sobre el texto).
 * Pin / unpin con un toggle. Borrar con confirmación.
 *
 * Refresca al recibir bus.event `note.*` (incrementa `rev.notes` en el
 * store, este componente observa ese contador y vuelve a fetch).
 */

import { useEffect, useMemo, useState } from "react";

import { api, type NoteApi } from "@/api/rest";
import { useOrionStore } from "@/stores/orion";

export function NotesPanel() {
  const rev = useOrionStore((s) => s.rev.notes);
  const [notes, setNotes] = useState<NoteApi[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState("");

  // Carga inicial y cada vez que rev.notes cambia (eventos WS).
  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.listNotes()
      .then((ns) => { if (alive) { setNotes(ns); setError(null); } })
      .catch((e) => { if (alive) setError(String(e)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [rev]);

  const sorted = useMemo(() => {
    return [...notes].sort((a, b) => {
      if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
      return (b.updated ?? "").localeCompare(a.updated ?? "");
    });
  }, [notes]);

  async function add() {
    const t = draft.trim();
    if (!t) return;
    try {
      await api.createNote(t);
      setDraft("");
    } catch (e) { setError(String(e)); }
  }

  async function togglePin(n: NoteApi) {
    try { await api.updateNote(n.id, { pinned: !n.pinned }); }
    catch (e) { setError(String(e)); }
  }

  async function saveEdit() {
    if (!editingId) return;
    const t = editingText.trim();
    if (!t) { setEditingId(null); return; }
    try {
      await api.updateNote(editingId, { text: t });
      setEditingId(null);
      setEditingText("");
    } catch (e) { setError(String(e)); }
  }

  async function remove(id: string) {
    if (!confirm("¿Borrar esta nota?")) return;
    try { await api.deleteNote(id); }
    catch (e) { setError(String(e)); }
  }

  return (
    <div className="flex flex-col h-full">
      <header className="px-6 py-4 border-b border-border-b">
        <h2 className="text-sm uppercase tracking-[0.3em] text-text-dim">Notas rápidas</h2>
        <p className="text-xs text-text-dim/70 mt-1">{notes.length} nota{notes.length === 1 ? "" : "s"}</p>
      </header>

      {/* Editor de nueva nota */}
      <div className="p-4 border-b border-border-b bg-panel">
        <div className="flex gap-2 items-end">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Nueva nota…"
            rows={2}
            className="flex-1 resize-none rounded-md bg-panel2 border border-border-b
                       px-3 py-2 text-sm placeholder-text-dim
                       focus:outline-none focus:border-pri"
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); add(); }
            }}
          />
          <button
            onClick={add}
            disabled={!draft.trim()}
            className="rounded-md bg-pri text-bg text-sm font-medium px-4 py-2
                       disabled:opacity-30 hover:brightness-110 transition"
          >
            Añadir
          </button>
        </div>
        <p className="text-[10px] text-text-dim mt-2">Ctrl/Cmd+Enter para guardar</p>
      </div>

      {error && (
        <div className="mx-4 mt-3 p-2 text-xs rounded border border-pri bg-pri/10 text-pri">
          {error}
        </div>
      )}

      {/* Lista */}
      <div className="flex-1 overflow-y-auto scrollbar-thin p-4 flex flex-col gap-2">
        {loading && notes.length === 0 && (
          <div className="text-center text-text-dim text-sm">Cargando…</div>
        )}
        {!loading && notes.length === 0 && (
          <div className="text-center text-text-dim text-sm italic mt-8">
            Aún no hay notas. Crea la primera arriba.
          </div>
        )}
        {sorted.map((n) => {
          const isEditing = editingId === n.id;
          return (
            <article
              key={n.id}
              className={`group rounded-lg border p-3 transition
                ${n.pinned
                  ? "border-pri/60 bg-pri/5"
                  : "border-border-b bg-panel2 hover:border-pri/40"}`}
            >
              <header className="flex items-center justify-between text-[10px] uppercase tracking-widest text-text-dim mb-1">
                <span>{n.pinned ? "★ Anclada" : "Nota"}</span>
                <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition">
                  <button
                    onClick={() => togglePin(n)}
                    className="hover:text-pri"
                    title={n.pinned ? "Desanclar" : "Anclar"}
                  >
                    {n.pinned ? "☆" : "★"}
                  </button>
                  {!isEditing && (
                    <button
                      onClick={() => { setEditingId(n.id); setEditingText(n.text); }}
                      className="hover:text-pri"
                      title="Editar"
                    >
                      ✎
                    </button>
                  )}
                  <button
                    onClick={() => remove(n.id)}
                    className="hover:text-pri"
                    title="Borrar"
                  >
                    ×
                  </button>
                </div>
              </header>

              {isEditing ? (
                <div className="flex flex-col gap-2">
                  <textarea
                    value={editingText}
                    onChange={(e) => setEditingText(e.target.value)}
                    rows={3}
                    autoFocus
                    className="resize-none rounded-md bg-panel border border-border-b
                               px-2 py-1 text-sm focus:outline-none focus:border-pri"
                  />
                  <div className="flex gap-2 justify-end">
                    <button
                      onClick={() => { setEditingId(null); setEditingText(""); }}
                      className="text-xs px-2 py-1 text-text-dim hover:text-text"
                    >Cancelar</button>
                    <button
                      onClick={saveEdit}
                      className="text-xs px-3 py-1 rounded bg-pri text-bg hover:brightness-110"
                    >Guardar</button>
                  </div>
                </div>
              ) : (
                <p className="whitespace-pre-wrap text-sm leading-relaxed">{n.text}</p>
              )}

              <footer className="text-[10px] text-text-dim mt-2">
                {n.updated}
              </footer>
            </article>
          );
        })}
      </div>
    </div>
  );
}
