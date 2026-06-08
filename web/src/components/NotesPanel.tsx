/**
 * NotesPanel — quick notes CRUD.
 *
 * Sorted (pinned first → updated desc). Inline edit, pin toggle, delete.
 * Refresh reactively on `note.*` bus events via `rev.notes`.
 */

import { useEffect, useMemo, useState } from "react";

import { api, type NoteApi } from "@/api/rest";
import { useOrionStore } from "@/stores/orion";
import { Icon } from "@/ui/Icon";
import { Badge, Button, Empty, SectionHeader, Surface } from "@/ui/primitives";

export function NotesPanel() {
  const rev = useOrionStore((s) => s.rev.notes);
  const [notes, setNotes] = useState<NoteApi[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState("");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.listNotes()
      .then((ns) => { if (alive) { setNotes(ns); setError(null); } })
      .catch((e) => { if (alive) setError(String(e)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [rev]);

  const sorted = useMemo(() => [...notes].sort((a, b) => {
    if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
    return (b.updated ?? "").localeCompare(a.updated ?? "");
  }), [notes]);

  async function add() {
    const t = draft.trim();
    if (!t) return;
    try { await api.createNote(t); setDraft(""); }
    catch (e) { setError(String(e)); }
  }
  async function togglePin(n: NoteApi) {
    try { await api.updateNote(n.id, { pinned: !n.pinned }); }
    catch (e) { setError(String(e)); }
  }
  async function saveEdit() {
    if (!editingId) return;
    const t = editingText.trim();
    if (!t) { setEditingId(null); return; }
    try { await api.updateNote(editingId, { text: t }); setEditingId(null); setEditingText(""); }
    catch (e) { setError(String(e)); }
  }
  async function remove(id: string) {
    if (!confirm("¿Borrar esta nota?")) return;
    try { await api.deleteNote(id); }
    catch (e) { setError(String(e)); }
  }

  return (
    <div className="flex flex-col h-full">
      <SectionHeader
        eyebrow="Conocimiento"
        title="Notas rápidas"
        hint="Pensamientos sueltos, recordatorios, ideas. Se sincronizan en vivo."
        action={<Badge tone="neutral">{notes.length}</Badge>}
      />

      <div className="px-6 py-4 border-b border-white/[0.06]">
        <div className="rounded-xl border border-white/[0.08] bg-elevated/60
                        focus-within:border-pri/40 focus-within:shadow-glow-soft
                        transition-all duration-200 ease-out-expo">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Nueva nota…"
            rows={2}
            className="block w-full resize-none bg-transparent rounded-xl
                       px-4 pt-3 pb-2 text-sm leading-relaxed placeholder-muted
                       focus:outline-none"
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); add(); }
            }}
          />
          <div className="flex items-center justify-between px-3 pb-2.5">
            <span className="text-[10px] uppercase tracking-[0.18em] text-muted">Ctrl/⌘ + Enter</span>
            <Button
              variant="primary" size="sm" icon="plus"
              onClick={add} disabled={!draft.trim()}
            >
              Añadir nota
            </Button>
          </div>
        </div>
      </div>

      {error && <Inline error={error} />}

      <div className="flex-1 overflow-y-auto scrollbar-thin px-6 py-4">
        {loading && notes.length === 0 && (
          <div className="space-y-2">
            <div className="skeleton h-16" /><div className="skeleton h-16" /><div className="skeleton h-16" />
          </div>
        )}
        {!loading && notes.length === 0 && (
          <Empty
            icon="notes"
            title="Aún sin notas"
            hint="Crea la primera arriba o pídele a Orion que la guarde por ti."
          />
        )}
        <div className="flex flex-col gap-2.5">
          {sorted.map((n, i) => (
            <NoteCard
              key={n.id}
              note={n}
              delay={i * 30}
              isEditing={editingId === n.id}
              editingText={editingText}
              onStartEdit={() => { setEditingId(n.id); setEditingText(n.text); }}
              onCancelEdit={() => { setEditingId(null); setEditingText(""); }}
              onChangeEdit={setEditingText}
              onSaveEdit={saveEdit}
              onTogglePin={() => togglePin(n)}
              onRemove={() => remove(n.id)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function NoteCard({
  note, delay,
  isEditing, editingText,
  onStartEdit, onCancelEdit, onChangeEdit, onSaveEdit,
  onTogglePin, onRemove,
}: {
  note: NoteApi; delay: number;
  isEditing: boolean; editingText: string;
  onStartEdit: () => void; onCancelEdit: () => void;
  onChangeEdit: (v: string) => void; onSaveEdit: () => void;
  onTogglePin: () => void; onRemove: () => void;
}) {
  return (
    <Surface
      level={2}
      className={[
        "group p-3.5 animate-fade-in-up transition-colors duration-200",
        note.pinned && "ring-1 ring-pri/30",
      ].filter(Boolean).join(" ")}
      style={{ animationDelay: `${delay}ms` }}
    >
      <header className="flex items-center justify-between gap-2 mb-1.5">
        {note.pinned
          ? <Badge tone="info" dot>Anclada</Badge>
          : <span className="text-[10px] uppercase tracking-[0.18em] text-muted">Nota</span>}
        <div className="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
          <IconBtn icon="pin"  active={note.pinned} onClick={onTogglePin}
                   title={note.pinned ? "Desanclar" : "Anclar"} />
          {!isEditing && <IconBtn icon="edit" onClick={onStartEdit} title="Editar" />}
          <IconBtn icon="trash" danger onClick={onRemove} title="Borrar" />
        </div>
      </header>

      {isEditing ? (
        <div className="flex flex-col gap-2">
          <textarea
            value={editingText}
            onChange={(e) => onChangeEdit(e.target.value)}
            rows={3}
            autoFocus
            className="resize-none rounded-lg bg-surface border border-pri/40
                       px-3 py-2 text-sm focus:outline-none focus:border-pri"
          />
          <div className="flex gap-2 justify-end">
            <Button variant="ghost"   size="sm" onClick={onCancelEdit}>Cancelar</Button>
            <Button variant="primary" size="sm" icon="check" onClick={onSaveEdit}>Guardar</Button>
          </div>
        </div>
      ) : (
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-text">{note.text}</p>
      )}

      <footer className="mt-2 text-[10px] uppercase tracking-[0.18em] text-muted">
        {note.updated}
      </footer>
    </Surface>
  );
}

function IconBtn({
  icon, onClick, title, active, danger,
}: {
  icon: "pin" | "edit" | "trash";
  onClick: () => void;
  title?: string;
  active?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={[
        "h-7 w-7 grid place-items-center rounded-md transition-colors duration-150",
        active ? "text-pri" : "text-text-dim hover:text-text",
        danger ? "hover:text-danger hover:bg-danger/10" : "hover:bg-white/[0.05]",
      ].join(" ")}
    >
      <Icon name={icon} size={14} />
    </button>
  );
}

function Inline({ error }: { error: string }) {
  return (
    <div className="mx-6 mt-3 flex items-start gap-2 p-3 rounded-md border border-danger/30 bg-danger/10 text-xs text-danger animate-fade-in">
      <Icon name="alert" size={14} className="mt-0.5 shrink-0" /><span>{error}</span>
    </div>
  );
}
