/**
 * NotificationsPanel — bandeja de Gmail + Classroom.
 *
 * El backend tiene un poller en background que cada N min trae nuevos
 * items. Acá los mostramos ordenados por fecha desc, con filtro por
 * fuente, botón de "marcar todas como leídas" y un botón "Autorizar
 * Classroom" cuando esa fuente está sin token.
 */

import { useEffect, useMemo, useState } from "react";

import {
  api, type NotifItem, type NotifPollerStatus,
} from "@/api/rest";
import { useOrionStore } from "@/stores/orion";
import { Icon } from "@/ui/Icon";
import { Badge, Button, Empty, SectionHeader, Surface } from "@/ui/primitives";

type Filter = "all" | "unread" | "gmail" | "classroom";

export function NotificationsPanel() {
  const rev    = useOrionStore((s) => s.rev.notifications);
  const [items,   setItems]   = useState<NotifItem[]>([]);
  const [status,  setStatus]  = useState<NotifPollerStatus | null>(null);
  const [filter,  setFilter]  = useState<Filter>("all");
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<string | null>(null);
  const [authorizing, setAuthorizing] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      const [list, st] = await Promise.all([
        api.listNotifications(filterToParams(filter)),
        api.notificationsStatus(),
      ]);
      setItems(list);
      setStatus(st);
      setError(null);
      // Reset del contador local de no-leídas (lo recalculamos del listado).
      const unread = list.filter((it) => !isReadFromStore(it.uid, list)).length;
      useOrionStore.setState({ unreadNotifs: unread });
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void refresh(); /* eslint-disable-next-line */ }, [filter, rev]);

  async function pollNow(src?: string) {
    setLoading(true);
    try {
      await api.pollNotifications(src);
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function markAllRead(src?: string) {
    try {
      await api.markAllNotificationsRead(src);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function authorizeClassroom() {
    setAuthorizing(true);
    setError(null);
    try {
      await api.authorizeClassroom();
      // Force a poll so the backend updates last_status and fetches items.
      await api.pollNotifications("classroom");
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setAuthorizing(false);
    }
  }

  const classroomState = status?.last_status?.classroom;
  // Fuente de verdad nueva: el backend ahora expone `is_configured` mirando
  // el filesystem (token.json + client_secret). Si el campo está presente,
  // úsalo directo y evita el bug del banner perpetuo cuando el poller en
  // background todavía no corrió y `last_status.classroom` viene undefined.
  // Si el backend es viejo y no manda `is_configured`, caemos al
  // heurístico anterior basado en `last_status`.
  const classroomNeedsAuth =
    status != null && (
      status.is_configured !== undefined
        ? !status.is_configured.classroom
        : (!classroomState ||
           (classroomState && !classroomState.ok &&
             (classroomState.error?.toLowerCase().includes("token") ||
              classroomState.error?.toLowerCase().includes("no configurado") ||
              classroomState.error?.toLowerCase().includes("not_configured"))))
    );

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <SectionHeader
        eyebrow="Sistema"
        title="Notificaciones"
        hint="Gmail + Classroom — el poller refresca cada 10 min en background."
        action={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" icon="memory" onClick={() => pollNow()} disabled={loading}>
              Refrescar
            </Button>
            <Button variant="primary" size="sm" icon="check" onClick={() => markAllRead()}>
              Marcar todas
            </Button>
          </div>
        }
      />

      <div className="px-6 py-3 border-b border-white/[0.06]">
        <div className="flex items-center gap-2 flex-wrap">
          <FilterChip current={filter} value="all"       onClick={setFilter}>Todas</FilterChip>
          <FilterChip current={filter} value="unread"    onClick={setFilter}>No leídas</FilterChip>
          <FilterChip current={filter} value="gmail"     onClick={setFilter}>Gmail</FilterChip>
          <FilterChip current={filter} value="classroom" onClick={setFilter}>Classroom</FilterChip>
          <span className="ml-auto text-[10px] text-muted">
            {status?.running ? "Poller activo" : "Poller detenido"}
            {status?.config?.interval_seconds &&
              ` · cada ${Math.round(status.config.interval_seconds / 60)} min`}
          </span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin px-6 py-4">
        {error && (
          <div className="mb-3 flex items-start gap-2 p-3 rounded-md
                          border border-danger/30 bg-danger/10 text-xs text-danger">
            <Icon name="alert" size={14} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {classroomNeedsAuth && (
          <Surface level={2} className="p-3 mb-4 border border-acc/30">
            <div className="text-[10px] uppercase tracking-[0.18em] text-acc mb-1">
              Classroom sin autorizar
            </div>
            <p className="text-[11px] leading-relaxed text-text-dim mb-3">
              Necesita un OAuth dance una vez. Abre el navegador, pide permisos,
              guarda el token en <code>tools/classroom/token.json</code>.
            </p>
            <Button variant="primary" size="sm" icon="play"
                    onClick={authorizeClassroom} disabled={authorizing}>
              {authorizing ? "Esperando autorización en el navegador…" : "Autorizar Classroom"}
            </Button>
          </Surface>
        )}

        <SourceStatusGrid status={status} onPoll={pollNow} />

        {loading && items.length === 0 && (
          <div className="space-y-2">
            <div className="skeleton h-16" />
            <div className="skeleton h-16" />
          </div>
        )}

        {!loading && items.length === 0 && (
          <Empty
            icon="bell"
            title="Sin notificaciones"
            hint="Si recién instalaste los adapters, dale a Refrescar para forzar el primer poll."
          />
        )}

        <div className="flex flex-col gap-2">
          {items.map((it, i) => (
            <NotifCard key={it.uid} item={it} delay={i * 25} onAfterRead={refresh} />
          ))}
        </div>
      </div>
    </div>
  );
}

function filterToParams(f: Filter): { source?: string; unread?: boolean } {
  switch (f) {
    case "unread":    return { unread: true };
    case "gmail":     return { source: "gmail" };
    case "classroom": return { source: "classroom" };
    default:          return {};
  }
}

// Las notifs no traen flag de leído por item — el backend lo tiene en un set
// aparte. Para el badge usamos el contador global del store; acá renderizamos
// todas con el mismo tratamiento visual.
function isReadFromStore(_uid: string, _all: NotifItem[]): boolean {
  return false;
}

function FilterChip({
  current, value, onClick, children,
}: {
  current: Filter; value: Filter; onClick: (v: Filter) => void; children: React.ReactNode;
}) {
  const active = current === value;
  return (
    <button
      onClick={() => onClick(value)}
      className={[
        "px-2.5 h-7 text-[11px] uppercase tracking-[0.14em] rounded-md transition-colors",
        active
          ? "bg-pri/15 text-pri shadow-[inset_0_0_0_1px_rgb(var(--orion-pri)/0.3)]"
          : "text-text-dim hover:text-text hover:bg-white/[0.04]",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

function SourceStatusGrid({
  status, onPoll,
}: { status: NotifPollerStatus | null; onPoll: (src?: string) => void }) {
  if (!status) return null;
  const sources = Object.entries(status.last_status);
  if (sources.length === 0) return null;
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mb-4">
      {sources.map(([src, s]) => (
        <Surface key={src} level={2} className="p-3">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <code className="text-sm font-mono text-text capitalize">{src}</code>
                {s.ok
                  ? <Badge tone="success" dot>Ok</Badge>
                  : <Badge tone="danger"  dot>Error</Badge>}
              </div>
              {!s.ok && s.error && (
                <p className="text-[10px] text-danger mt-1 truncate" title={s.error}>{s.error}</p>
              )}
              {s.ok && s.ts && (
                <p className="text-[10px] text-muted mt-1">
                  Último poll: {new Date(s.ts * 1000).toLocaleTimeString()}
                </p>
              )}
            </div>
            <Button variant="ghost" size="sm" icon="memory" onClick={() => onPoll(src)}>
              Probar
            </Button>
          </div>
        </Surface>
      ))}
    </div>
  );
}

function NotifCard({
  item, delay, onAfterRead,
}: { item: NotifItem; delay?: number; onAfterRead: () => void }) {
  const isGmail = item.source === "gmail";
  const tone    = isGmail ? "info" : "accent";

  async function markRead() {
    try {
      await api.markNotificationsRead([item.uid]);
      onAfterRead();
    } catch { /* ignore */ }
  }

  function openInBrowser() {
    if (item.url) window.open(item.url, "_blank", "noopener,noreferrer");
  }

  return (
    <Surface
      level={2}
      hover
      className="p-3 animate-fade-in-up"
      style={{ animationDelay: `${delay ?? 0}ms` }}
    >
      <header className="flex items-center justify-between gap-3 mb-1">
        <Badge tone={tone}>{item.source}</Badge>
        <span className="text-[10px] text-muted">
          {new Date(item.received_ts * 1000).toLocaleString()}
        </span>
      </header>
      <p className="text-sm text-text leading-snug mb-1">{item.title}</p>
      {item.summary && (
        <p className="text-xs text-text-dim leading-relaxed line-clamp-2 mb-2">
          {item.summary}
        </p>
      )}
      <div className="flex items-center gap-1.5">
        {item.url && (
          <Button variant="primary" size="sm" icon="play" onClick={openInBrowser}>
            Abrir
          </Button>
        )}
        <Button variant="ghost" size="sm" icon="check" onClick={markRead}>
          Marcar leída
        </Button>
      </div>
    </Surface>
  );
}

// useMemo importado por si lo necesito a futuro
export { useMemo };
