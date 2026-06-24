/**
 * NotesPanel — quick notes CRUD.
 *
 * Sorted (pinned first → updated desc). Inline edit, pin toggle, delete.
 * Refresh reactively on `note.*` bus events via `rev.notes`.
 *
 * Mejoras:
 *   - Búsqueda local que filtra por contenido.
 *   - Layout en 2 columnas en pantallas grandes para más densidad.
 *   - Pinned section visualmente diferenciada arriba.
 *   - Toasts in-app reemplazando `confirm()` y `alert`.
 *   - Composer con contador de caracteres + foco mejorado.
 */

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import { api, type NoteApi } from "@/api/rest";
import { humanizeTime } from "@/lib/humanTime";
import { QUERY_KEYS } from "@/query/keys";
import { toast } from "@/stores/toast";
import { Icon } from "@/ui/Icon";
import { Badge, Button, Empty, SectionHeader, Surface } from "@/ui/primitives";

export function NotesPanel() {
  // Server-state via TanStack Query — la invalidación viene del bridge WS
  // en stores/orion.ts (case "note.*"), así que no hace falta leer rev.notes.
  const {
    data: notes = [],
    isFetching,
    error,
  } = useQuery<NoteApi[]>({
    queryKey: QUERY_KEYS.notes,
    queryFn: () => api.listNotes(),
  });
  // El loading skeleton del panel original sólo se mostraba en el primer
  // fetch (mientras `notes` estaba vacío). Replicamos esa semántica con
  // `isFetching && notes.length === 0` más abajo.
  const loading = isFetching;

  // Notificar errores via toast UNA vez por error — el panel anterior lo
  // hacía en el .catch del effect; acá usamos un ref para no spamear si
  // hay refetchs sucesivos del mismo error.
  const lastErrorRef = useRef<string | null>(null);
  useEffect(() => {
    if (error) {
      const msg = String(error);
      if (lastErrorRef.current !== msg) {
        toast.error("No pude cargar notas", msg);
        lastErrorRef.current = msg;
      }
    } else {
      lastErrorRef.current = null;
    }
  }, [error]);

  const [draft, setDraft] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState("");
  const [query, setQuery] = useState("");

  // Filtrado por query + orden: pinned arriba, después por updated desc.
  const { pinned, rest } = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = q ? notes.filter((n) => n.text.toLowerCase().includes(q)) : notes;
    const sorted = [...filtered].sort((a, b) => (b.updated ?? "").localeCompare(a.updated ?? ""));
    return {
      pinned: sorted.filter((n) => n.pinned),
      rest: sorted.filter((n) => !n.pinned),
    };
  }, [notes, query]);

  const totalShown = pinned.length + rest.length;

  /* ── Acciones ───────────────────────────────────────────────── */
  async function add() {
    const t = draft.trim();
    if (!t) return;
    try {
      await api.createNote(t);
      setDraft("");
      toast.success("Nota añadida");
    } catch (e) {
      toast.error("No se pudo crear", String(e));
    }
  }
  async function togglePin(n: NoteApi) {
    try {
      await api.updateNote(n.id, { pinned: !n.pinned });
    } catch (e) {
      toast.error("No se pudo cambiar el pin", String(e));
    }
  }
  async function saveEdit() {
    if (!editingId) return;
    const t = editingText.trim();
    if (!t) {
      setEditingId(null);
      return;
    }
    try {
      await api.updateNote(editingId, { text: t });
      setEditingId(null);
      setEditingText("");
      toast.success("Nota actualizada");
    } catch (e) {
      toast.error("No se pudo guardar", String(e));
    }
  }
  async function remove(id: string) {
    const ok = await toast.confirm({
      title: "¿Borrar nota?",
      detail: "Esta acción no se puede deshacer.",
      confirmLabel: "Borrar",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.deleteNote(id);
      toast.success("Nota borrada");
    } catch (e) {
      toast.error("No se pudo borrar", String(e));
    }
  }

  return (
    <div className="flex flex-col h-full">
      <SectionHeader
        eyebrow="Conocimiento"
        title="Notas rápidas"
        hint="Pensamientos sueltos, recordatorios, ideas. Se sincronizan en vivo."
        action={<Badge tone="neutral">{notes.length}</Badge>}
      />

      {/* ── Composer ─────────────────────────────────────────────── */}
      <div className="px-6 py-4 border-b border-white/[0.06]">
        <div
          className="rounded-xl border border-white/[0.08] bg-elevated/60
                        focus-within:border-pri/40 focus-within:shadow-glow-soft
                        transition-all duration-200 ease-out-expo"
        >
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Nueva nota…"
            rows={2}
            className="block w-full resize-none bg-transparent rounded-xl
                       px-4 pt-3 pb-2 text-sm leading-relaxed placeholder-muted
                       focus:outline-none"
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                add();
              }
            }}
          />
          <div className="flex items-center justify-between px-3 pb-2.5">
            <div className="flex items-center gap-3">
              <span className="text-[10px] uppercase tracking-[0.18em] text-muted font-mono">
                Ctrl/⌘ + Enter
              </span>
              {draft && (
                <span className="text-[10px] text-text-dim tabular-nums">{draft.length} chars</span>
              )}
            </div>
            <Button variant="primary" size="sm" icon="plus" onClick={add} disabled={!draft.trim()}>
              Añadir nota
            </Button>
          </div>
        </div>

        {/* search */}
        {notes.length > 0 && (
          <div className="mt-3 relative">
            <Icon
              name="search"
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-text-dim pointer-events-none"
            />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Buscar en notas…"
              className="w-full h-9 pl-9 pr-9 rounded-md bg-elevated/60 border border-white/[0.08]
                         text-sm placeholder-muted focus:outline-none focus:border-pri/40
                         transition-colors"
            />
            {query && (
              <button
                onClick={() => setQuery("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 h-6 w-6 grid place-items-center
                           rounded text-text-dim hover:text-text hover:bg-white/[0.05]"
                title="Limpiar"
              >
                <Icon name="close" size={11} />
              </button>
            )}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin px-6 py-4">
        {loading && notes.length === 0 && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-2.5">
            <div className="skeleton h-20" />
            <div className="skeleton h-20" />
            <div className="skeleton h-20" />
            <div className="skeleton h-20" />
          </div>
        )}
        {!loading && notes.length === 0 && (
          <Empty
            icon="notes"
            title="Aún no anoté nada por ti"
            hint="Escribí la primera arriba, o pedímelo en voz alta y la capturo."
          />
        )}
        {!loading && notes.length > 0 && totalShown === 0 && (
          <Empty
            icon="search"
            title="Sin coincidencias"
            hint={`Ninguna nota contiene "${query}".`}
          />
        )}

        {pinned.length > 0 && (
          <Section label="Ancladas" icon="pin" count={pinned.length} tone="pri">
            <NoteGrid
              notes={pinned}
              editingId={editingId}
              editingText={editingText}
              onStartEdit={(n) => {
                setEditingId(n.id);
                setEditingText(n.text);
              }}
              onCancelEdit={() => {
                setEditingId(null);
                setEditingText("");
              }}
              onChangeEdit={setEditingText}
              onSaveEdit={saveEdit}
              onTogglePin={togglePin}
              onRemove={remove}
            />
          </Section>
        )}

        {rest.length > 0 && (
          <Section
            label={pinned.length > 0 ? "Resto" : "Todas"}
            icon="notes"
            count={rest.length}
            className={pinned.length > 0 ? "mt-6" : ""}
          >
            <NoteGrid
              notes={rest}
              editingId={editingId}
              editingText={editingText}
              onStartEdit={(n) => {
                setEditingId(n.id);
                setEditingText(n.text);
              }}
              onCancelEdit={() => {
                setEditingId(null);
                setEditingText("");
              }}
              onChangeEdit={setEditingText}
              onSaveEdit={saveEdit}
              onTogglePin={togglePin}
              onRemove={remove}
            />
          </Section>
        )}
      </div>
    </div>
  );
}

/* ─── Section header ───────────────────────────────────────────────── */
function Section({
  label,
  icon,
  count,
  tone,
  className,
  children,
}: {
  label: string;
  icon: "pin" | "notes";
  count: number;
  tone?: "pri" | "muted";
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={className ?? ""}>
      <header className="flex items-center gap-2 mb-3 text-[10px] uppercase tracking-[0.24em] font-mono">
        <Icon name={icon} size={12} className={tone === "pri" ? "text-pri" : "text-text-dim"} />
        <span className={tone === "pri" ? "text-pri/90" : "text-text-dim"}>{label}</span>
        <span className="text-muted tabular-nums">· {count}</span>
        <span className="flex-1 h-px bg-white/[0.05] ml-2" />
      </header>
      {children}
    </section>
  );
}

/* ─── Grid (2 columnas en >lg) ─────────────────────────────────────── */
function NoteGrid({
  notes,
  editingId,
  editingText,
  onStartEdit,
  onCancelEdit,
  onChangeEdit,
  onSaveEdit,
  onTogglePin,
  onRemove,
}: {
  notes: NoteApi[];
  editingId: string | null;
  editingText: string;
  onStartEdit: (n: NoteApi) => void;
  onCancelEdit: () => void;
  onChangeEdit: (v: string) => void;
  onSaveEdit: () => void;
  onTogglePin: (n: NoteApi) => void;
  onRemove: (id: string) => void;
}) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-2.5">
      {notes.map((n, i) => (
        <NoteCard
          key={n.id}
          note={n}
          delay={i * 30}
          isEditing={editingId === n.id}
          editingText={editingText}
          onStartEdit={() => onStartEdit(n)}
          onCancelEdit={onCancelEdit}
          onChangeEdit={onChangeEdit}
          onSaveEdit={onSaveEdit}
          onTogglePin={() => onTogglePin(n)}
          onRemove={() => onRemove(n.id)}
        />
      ))}
    </div>
  );
}

function NoteCard({
  note,
  delay,
  isEditing,
  editingText,
  onStartEdit,
  onCancelEdit,
  onChangeEdit,
  onSaveEdit,
  onTogglePin,
  onRemove,
}: {
  note: NoteApi;
  delay: number;
  isEditing: boolean;
  editingText: string;
  onStartEdit: () => void;
  onCancelEdit: () => void;
  onChangeEdit: (v: string) => void;
  onSaveEdit: () => void;
  onTogglePin: () => void;
  onRemove: () => void;
}) {
  return (
    // BRIEF · Notas:
    //  · Quitamos el badge "NOTA" de cada card — redundante en una
    //    sección llamada Notas. Solo mostramos "Anclada" cuando aplica.
    //  · Texto de la nota a 15px para que sea legible sin esfuerzo.
    //  · Hover: border-left de 2px del acento + lift sutil (-2px).
    //  · Timestamp humanizado abajo a la derecha, sin prominencia.
    <Surface
      level={2}
      className={[
        "group relative p-3.5 animate-fade-in-up transition-all duration-300 ease-spring",
        "hover:-translate-y-0.5 hover:border-pri/25",
        note.pinned ? "ring-1 ring-pri/30 bg-pri/[0.03]" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      style={{ animationDelay: `${delay}ms` }}
    >
      {/* barra accent que asoma al hover — sello visionOS */}
      <span
        aria-hidden
        className="absolute left-0 top-3 bottom-3 w-[2px] rounded-r-full bg-pri/0
                   group-hover:bg-pri/60 transition-colors duration-300
                   shadow-[0_0_10px_rgb(var(--orion-pri-glow)/0.4)]"
      />

      <header className="flex items-center justify-between gap-2 mb-2">
        {note.pinned ? (
          <Badge tone="info" dot>
            Anclada
          </Badge>
        ) : (
          <span />
        )}
        <div className="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
          <IconBtn
            icon="pin"
            active={note.pinned}
            onClick={onTogglePin}
            title={note.pinned ? "Desanclar" : "Anclar"}
          />
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
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                onSaveEdit();
              }
              if (e.key === "Escape") onCancelEdit();
            }}
          />
          <div className="flex gap-2 justify-end items-center">
            <span className="text-[10px] uppercase tracking-[0.18em] text-muted font-mono mr-auto">
              Ctrl/⌘ + Enter
            </span>
            <Button variant="ghost" size="sm" onClick={onCancelEdit}>
              Cancelar
            </Button>
            <Button variant="primary" size="sm" icon="check" onClick={onSaveEdit}>
              Guardar
            </Button>
          </div>
        </div>
      ) : (
        <p className="whitespace-pre-wrap text-[15px] leading-relaxed text-text">{note.text}</p>
      )}

      <footer className="mt-2 flex justify-end text-[10px] text-muted/80 font-mono">
        <span title={note.updated}>{humanizeTime(note.updated)}</span>
      </footer>
    </Surface>
  );
}

function IconBtn({
  icon,
  onClick,
  title,
  active,
  danger,
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
