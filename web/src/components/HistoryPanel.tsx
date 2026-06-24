/**
 * HistoryPanel — conversation history.
 *
 * Two-pane layout: list (left) + detail (right). Premium card list with
 * hover affordances. Detail re-uses the chat presentation style.
 *
 * Nuevas capacidades:
 *   - Modo selección múltiple (checkbox por item, select-all).
 *   - Borrar todo / borrar seleccionadas con toast confirmatorio.
 *   - Detail filtra mensajes de "ruido" (logs de sistema sin contenido
 *     útil) y muestra solo turnos reales user/IA. Si la conversación no
 *     tiene contenido real, se muestra un empty-state claro con CTA
 *     para borrarla.
 *   - Todos los `confirm()` y errores nativos se reemplazaron por
 *     toasts in-app (no más alerts del browser arriba del layout).
 */

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import { api, type ConversationDetail, type ConversationSummary } from "@/api/rest";
import { QUERY_KEYS } from "@/query/keys";
import { toast } from "@/stores/toast";
import { Icon } from "@/ui/Icon";
import { Badge, Button, Empty, SectionHeader, Surface } from "@/ui/primitives";

// Patrones que típicamente vienen como ruido en mensajes "sys":
// "Conversación cargada (N mensajes)", "Reconectando…", etc. Si todos
// los mensajes de una conversación matchean estos, la consideramos vacía.
const NOISE_RE =
  /^(conversaci[oó]n cargada|reconectando|sistema:?|orion en l[ií]nea|error de|sin conexi[oó]n)/i;

function isRealMessage(m: { role: string; text: string }): boolean {
  if (m.role === "user" || m.role === "ai") return true;
  if (m.role === "file") return true;
  // sys/err: filtramos solo si matchea ruido conocido
  return !NOISE_RE.test(m.text.trim());
}

export function HistoryPanel() {
  const [active, setActive] = useState<string | null>(null);
  // Modo selección múltiple — cuando hay items seleccionados aparecen
  // las acciones de bulk en la toolbar.
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [selectMode, setSelectMode] = useState(false);

  // Lista de conversaciones. El bridge WS invalida `["conversations"]`
  // (prefix-match, así que también pega a `["conversations", id]`).
  const { data: list = [], error: listError } = useQuery<ConversationSummary[]>({
    queryKey: QUERY_KEYS.conversations,
    queryFn: () => api.listConversations(),
  });

  // Detalle de la conversación activa. `enabled: !!active` evita pegarle
  // al backend cuando no hay nada seleccionado.
  const { data: detail, error: detailError } = useQuery<ConversationDetail>({
    queryKey: QUERY_KEYS.conversation(active ?? ""),
    queryFn: () => api.getConversation(active!),
    enabled: !!active,
  });

  // Toasts one-shot por error nuevo (mismo patrón que NotesPanel/MemoryPanel).
  const lastListErr = useRef<string | null>(null);
  useEffect(() => {
    if (listError) {
      const m = String(listError);
      if (lastListErr.current !== m) {
        toast.error("No pude cargar el historial", m);
        lastListErr.current = m;
      }
    } else lastListErr.current = null;
  }, [listError]);
  const lastDetailErr = useRef<string | null>(null);
  useEffect(() => {
    if (detailError) {
      const m = String(detailError);
      if (lastDetailErr.current !== m) {
        toast.error("No pude abrir la conversación", m);
        lastDetailErr.current = m;
      }
    } else lastDetailErr.current = null;
  }, [detailError]);

  /* ── Selección ───────────────────────────────────────────────── */
  function toggleSelected(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
  function selectAll() {
    setSelected(new Set(list.map((c) => c.id)));
  }
  function clearSel() {
    setSelected(new Set());
  }
  function exitSelMode() {
    setSelectMode(false);
    setSelected(new Set());
  }

  /* ── Acciones ────────────────────────────────────────────────── */
  async function removeOne(id: string, title?: string) {
    const ok = await toast.confirm({
      title: "¿Borrar conversación?",
      detail: title ? `"${title.slice(0, 60)}" se eliminará del historial.` : undefined,
      confirmLabel: "Borrar",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.deleteConversation(id);
      if (active === id) {
        setActive(null);
        // detail se auto-desactiva por enabled:!!active
      }
      setSelected((s) => {
        const n = new Set(s);
        n.delete(id);
        return n;
      });
      toast.success("Conversación borrada");
    } catch (e) {
      toast.error("No se pudo borrar", String(e));
    }
  }

  async function removeSelected() {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    const ok = await toast.confirm({
      title: `¿Borrar ${ids.length} conversación${ids.length === 1 ? "" : "es"}?`,
      detail: "Esta acción no se puede deshacer.",
      confirmLabel: `Borrar ${ids.length}`,
      danger: true,
    });
    if (!ok) return;
    try {
      const { deleted } = await api.bulkDeleteConversations(ids);
      if (active && selected.has(active)) {
        setActive(null);
      }
      clearSel();
      setSelectMode(false);
      toast.success(
        `${deleted} conversación${deleted === 1 ? "" : "es"} borrada${deleted === 1 ? "" : "s"}`,
      );
    } catch (e) {
      toast.error("Borrado masivo falló", String(e));
    }
  }

  async function removeAll() {
    if (list.length === 0) return;
    const ok = await toast.confirm({
      title: `¿Borrar TODAS las conversaciones?`,
      detail: `${list.length} en total. Acción irreversible.`,
      confirmLabel: "Borrar todo",
      danger: true,
    });
    if (!ok) return;
    try {
      const { deleted } = await api.deleteAllConversations();
      setActive(null);
      clearSel();
      setSelectMode(false);
      toast.success(`Historial limpio · ${deleted} conversaciones borradas`);
    } catch (e) {
      toast.error("Wipe falló", String(e));
    }
  }

  const allSelected = list.length > 0 && selected.size === list.length;

  return (
    <div className="flex flex-col h-full">
      <SectionHeader
        eyebrow="Conocimiento"
        title="Historial"
        hint="Conversaciones pasadas con Orion, persistidas localmente."
        action={
          <div className="flex items-center gap-2">
            <Badge tone="neutral">{list.length}</Badge>
            {selectMode ? (
              <>
                <span className="text-[11px] text-text-dim tabular-nums">{selected.size} sel.</span>
                <Button variant="ghost" size="sm" onClick={allSelected ? clearSel : selectAll}>
                  {allSelected ? "Ninguno" : "Todos"}
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  icon="trash"
                  onClick={removeSelected}
                  disabled={selected.size === 0}
                >
                  Borrar ({selected.size})
                </Button>
                <Button variant="ghost" size="sm" onClick={exitSelMode}>
                  Salir
                </Button>
              </>
            ) : (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  icon="check"
                  onClick={() => setSelectMode(true)}
                  disabled={list.length === 0}
                >
                  Seleccionar
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  icon="trash"
                  onClick={removeAll}
                  disabled={list.length === 0}
                  title="Borrar todo el historial"
                >
                  Borrar todo
                </Button>
              </>
            )}
          </div>
        }
      />

      <div className="grid grid-cols-[320px_1fr] flex-1 overflow-hidden">
        {/* ── lista ─────────────────────────────────────────────── */}
        <aside className="border-r border-white/[0.06] overflow-y-auto scrollbar-thin p-3">
          {list.length === 0 && (
            <Empty
              icon="history"
              title="Sin conversaciones"
              hint="Cuando hablemos por primera vez, lo recordaré aquí."
            />
          )}
          <div className="flex flex-col gap-1.5">
            {list.map((c, i) => (
              <ConversationItem
                key={c.id}
                c={c}
                i={i}
                isActive={active === c.id}
                isSelected={selected.has(c.id)}
                selectMode={selectMode}
                onOpen={() => {
                  if (selectMode) toggleSelected(c.id);
                  else setActive(c.id);
                }}
                onToggleSelect={() => toggleSelected(c.id)}
                onDelete={() => removeOne(c.id, c.title)}
              />
            ))}
          </div>
        </aside>

        {/* ── detalle ───────────────────────────────────────────── */}
        <main className="overflow-y-auto scrollbar-thin">
          {!detail ? (
            <div className="h-full grid place-items-center">
              <Empty
                icon="chat"
                title="Elegí una conversación"
                hint="Tocá cualquier elemento de la lista para abrirla."
              />
            </div>
          ) : (
            <DetailView detail={detail} onDelete={() => removeOne(detail.id, detail.title)} />
          )}
        </main>
      </div>
    </div>
  );
}

/* ─── Detail con filtro de ruido + empty state contextual ──────────── */
function DetailView({ detail, onDelete }: { detail: ConversationDetail; onDelete: () => void }) {
  const realMessages = useMemo(() => detail.messages.filter(isRealMessage), [detail.messages]);

  return (
    <div className="mx-auto max-w-3xl px-6 py-6 flex flex-col gap-5 animate-fade-in">
      <header className="border-b border-white/[0.06] pb-3 mb-1 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-[0.22em] text-pri/80 font-mono">
            Conversación
          </div>
          <h3 className="text-base font-semibold text-text mt-0.5 truncate">
            {detail.title || detail.id}
          </h3>
          <div className="text-[11px] text-muted mt-0.5 font-mono">{detail.started}</div>
        </div>
        <Button variant="ghost" size="sm" icon="trash" onClick={onDelete}>
          Borrar
        </Button>
      </header>

      {realMessages.length === 0 ? (
        <div className="py-12 px-6">
          <Empty
            icon="chat"
            title="Esta conversación no tiene contenido"
            hint="Solo contiene logs de sistema sin un turno real. Probablemente puedas borrarla con seguridad."
            action={
              <Button variant="danger" size="sm" icon="trash" onClick={onDelete}>
                Borrar conversación
              </Button>
            }
          />
        </div>
      ) : (
        realMessages.map((m, i) => <DetailMessage key={i} role={m.role} text={m.text} ts={m.ts} />)
      )}
    </div>
  );
}

/* ─── Item de lista ─────────────────────────────────────────────────── */
function ConversationItem({
  c,
  i,
  isActive,
  isSelected,
  selectMode,
  onOpen,
  onToggleSelect,
  onDelete,
}: {
  c: ConversationSummary;
  i: number;
  isActive: boolean;
  isSelected: boolean;
  selectMode: boolean;
  onOpen: () => void;
  onToggleSelect: () => void;
  onDelete: () => void;
}) {
  return (
    <button
      onClick={onOpen}
      style={{ animationDelay: `${i * 20}ms` }}
      className={[
        "group relative text-left rounded-lg px-3 py-2.5 border transition-all duration-200 ease-out-expo animate-fade-in",
        isSelected
          ? "bg-pri/15 border-pri/45"
          : isActive
            ? "bg-pri/10 border-pri/35 shadow-glow-soft"
            : "bg-elevated/40 border-white/[0.05] hover:border-white/[0.12]",
      ].join(" ")}
    >
      {isActive && !selectMode && (
        <span className="absolute left-0 top-2 bottom-2 w-[2px] rounded-full bg-pri shadow-[0_0_8px_rgb(var(--orion-pri))]" />
      )}

      <div className="flex items-center gap-2.5">
        {/* checkbox visible solo en modo selección */}
        {selectMode && (
          <span
            onClick={(e) => {
              e.stopPropagation();
              onToggleSelect();
            }}
            className={[
              "shrink-0 h-4 w-4 rounded border grid place-items-center cursor-pointer transition-colors",
              isSelected ? "border-pri bg-pri/30" : "border-white/20 hover:border-pri/60",
            ].join(" ")}
          >
            {isSelected && <Icon name="check" size={10} className="text-pri" />}
          </span>
        )}

        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-medium truncate text-text">
              {c.title || "Conversación"}
            </span>
            {!selectMode && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete();
                }}
                title="Borrar"
                className="h-6 w-6 grid place-items-center rounded text-muted shrink-0
                           opacity-0 group-hover:opacity-100 hover:text-danger hover:bg-danger/10
                           transition-all"
              >
                <Icon name="close" size={12} />
              </button>
            )}
          </div>
          <div className="mt-1 flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] text-muted font-mono">
            <span className="tabular-nums">{c.messages} msg</span>
            <span className="text-white/[0.10]">·</span>
            <span className="tabular-nums">{c.started}</span>
          </div>
        </div>
      </div>
    </button>
  );
}

/* ─── Render de un mensaje en el detail ─────────────────────────────── */
function DetailMessage({ role, text, ts }: { role: string; text: string; ts: string }) {
  if (role === "sys" || role === "err") {
    return (
      <div className="flex items-center gap-2 my-1">
        <span className={`h-1 w-1 rounded-full ${role === "err" ? "bg-danger" : "bg-muted"}`} />
        <span className={`text-xs italic ${role === "err" ? "text-danger" : "text-text-dim"}`}>
          {text}
        </span>
        <span className="text-[10px] text-muted ml-1 font-mono">{ts}</span>
      </div>
    );
  }
  if (role === "file") {
    return (
      <div className="self-start">
        <Surface level={2} className="inline-flex items-center gap-2 px-3 py-1.5 text-xs text-acc">
          <Icon name="paperclip" size={13} />
          <span>{text}</span>
        </Surface>
      </div>
    );
  }
  if (role === "user") {
    return (
      <div className="self-end max-w-[78%]">
        <div className="rounded-2xl rounded-tr-md px-4 py-2.5 bg-pri/10 border border-pri/20">
          <div className="whitespace-pre-wrap leading-relaxed text-sm text-text">{text}</div>
        </div>
        <div className="text-right text-[9px] uppercase tracking-[0.22em] text-muted mt-1 font-mono">
          Tú · {ts}
        </div>
      </div>
    );
  }
  return (
    <div className="self-start max-w-[90%]">
      <div className="flex items-center gap-2 mb-1.5">
        <span className="h-2 w-2 rounded-full bg-pri" />
        <span className="text-[10px] uppercase tracking-[0.22em] text-pri/90 font-medium">
          Orion
        </span>
        <span className="text-[10px] text-muted font-mono">{ts}</span>
      </div>
      <div className="whitespace-pre-wrap leading-[1.7] text-[15px] text-text">{text}</div>
    </div>
  );
}
