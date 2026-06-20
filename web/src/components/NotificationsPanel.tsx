/**
 * NotificationsPanel — bandeja unificada con avatares por fuente.
 *
 * Cada card muestra el logo de la fuente (Gmail, Classroom, Drive…) en
 * un avatar circular con halo del color de marca. Los filtros agrupan
 * por google / sistema / extensiones / otros, además de mantener el
 * filtro por fuente puntual.
 */

import { useEffect, useMemo, useState } from "react";

import { api, type NotifItem, type NotifPollerStatus } from "@/api/rest";
import {
  sourceMeta,
  stripLeadingEmoji,
  formatRelative,
  type SourceGroup,
} from "@/lib/notificationSource";
import { useOrionStore } from "@/stores/orion";
import { Icon } from "@/ui/Icon";
import { Badge, Button, Empty, SectionHeader, Surface } from "@/ui/primitives";

type Filter = "all" | "unread" | SourceGroup;

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "Todas" },
  { id: "unread", label: "No leídas" },
  { id: "google", label: "Google" },
  { id: "system", label: "Sistema" },
  { id: "extension", label: "Extensiones" },
  { id: "other", label: "Otros" },
];

export function NotificationsPanel() {
  const rev = useOrionStore((s) => s.rev.notifications);
  const [items, setItems] = useState<NotifItem[]>([]);
  const [status, setStatus] = useState<NotifPollerStatus | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [authorizing, setAuthorizing] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      // El backend filtra por source/unread; los grupos los filtramos
      // en el cliente porque combinan varias fuentes.
      const params = filter === "unread" ? { unread: true } : {};
      const [list, st] = await Promise.all([
        api.listNotifications(params),
        api.notificationsStatus(),
      ]);
      setItems(list);
      setStatus(st);
      setError(null);
      useOrionStore.setState({ unreadNotifs: list.length });
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
    // `refresh` se recrea en cada render — meterla en deps causa loop infinito.
    // Sus únicos inputs reales (filter, rev) ya están listados.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter, rev]);

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
      await api.pollNotifications("classroom");
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setAuthorizing(false);
    }
  }

  const classroomState = status?.last_status?.classroom;
  const classroomNeedsAuth =
    status != null &&
    (status.is_configured !== undefined
      ? !status.is_configured.classroom
      : !classroomState ||
        (classroomState &&
          !classroomState.ok &&
          (classroomState.error?.toLowerCase().includes("token") ||
            classroomState.error?.toLowerCase().includes("no configurado") ||
            classroomState.error?.toLowerCase().includes("not_configured"))));

  const visibleItems = useMemo(() => {
    if (filter === "all" || filter === "unread") return items;
    return items.filter((it) => sourceMeta(it.source).group === filter);
  }, [items, filter]);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <SectionHeader
        eyebrow="Sistema"
        title="Notificaciones"
        hint="Gmail · Classroom · y todo lo que conectes. Poll cada 10 min en background."
        action={
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              icon="memory"
              onClick={() => pollNow()}
              disabled={loading}
            >
              Refrescar
            </Button>
            <Button variant="primary" size="sm" icon="check" onClick={() => markAllRead()}>
              Marcar todas
            </Button>
          </div>
        }
      />

      <div className="px-6 py-3 border-b border-white/[0.06]">
        <div className="flex items-center gap-1.5 flex-wrap">
          {FILTERS.map((f) => (
            <FilterChip key={f.id} current={filter} value={f.id} onClick={setFilter}>
              {f.label}
            </FilterChip>
          ))}
          <span className="ml-auto text-[10px] text-muted">
            {status?.running ? "Poller activo" : "Poller detenido"}
            {status?.config?.interval_seconds &&
              ` · cada ${Math.round(status.config.interval_seconds / 60)} min`}
          </span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin px-6 py-4">
        {error && (
          <div
            className="mb-3 flex items-start gap-2 p-3 rounded-md
                          border border-danger/30 bg-danger/10 text-xs text-danger"
          >
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
              Necesita un OAuth dance una vez. Abre el navegador, pide permisos, guarda el token en{" "}
              <code>tools/classroom/token.json</code>.
            </p>
            <Button
              variant="primary"
              size="sm"
              icon="play"
              onClick={authorizeClassroom}
              disabled={authorizing}
            >
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

        {!loading && visibleItems.length === 0 && (
          <Empty
            icon="bell"
            title="Sin notificaciones"
            hint="Si recién instalaste los adapters, dale a Refrescar para forzar el primer poll."
          />
        )}

        <div className="flex flex-col gap-2">
          {visibleItems.map((it, i) => (
            <NotifCard key={it.uid} item={it} delay={i * 25} onAfterRead={refresh} />
          ))}
        </div>
      </div>
    </div>
  );
}

function FilterChip({
  current,
  value,
  onClick,
  children,
}: {
  current: Filter;
  value: Filter;
  onClick: (v: Filter) => void;
  children: React.ReactNode;
}) {
  const active = current === value;
  return (
    <button
      onClick={() => onClick(value)}
      className={[
        "px-2.5 h-7 text-[11px] uppercase tracking-[0.14em] rounded-md transition-colors",
        active
          ? "bg-white/[0.08] text-text"
          : "text-text-dim hover:text-text hover:bg-white/[0.04]",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

function SourceStatusGrid({
  status,
  onPoll,
}: {
  status: NotifPollerStatus | null;
  onPoll: (src?: string) => void;
}) {
  if (!status) return null;
  const sources = Object.entries(status.last_status);
  if (sources.length === 0) return null;
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mb-4">
      {sources.map(([src, s]) => {
        const meta = sourceMeta(src);
        return (
          <Surface key={src} level={2} className="p-3">
            <div className="flex items-center gap-3">
              <SourceAvatar src={meta.logo} color={meta.color} size={28} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-text">{meta.label}</span>
                  {s.ok ? (
                    <Badge tone="success" dot>
                      Ok
                    </Badge>
                  ) : (
                    <Badge tone="danger" dot>
                      Error
                    </Badge>
                  )}
                </div>
                {!s.ok && s.error && (
                  <p className="text-[10px] text-danger mt-1 truncate" title={s.error}>
                    {s.error}
                  </p>
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
        );
      })}
    </div>
  );
}

/* Avatar circular con halo del color de marca de la fuente. */
function SourceAvatar({ src, color, size = 36 }: { src: string; color: string; size?: number }) {
  return (
    <div
      className="relative grid place-items-center rounded-full shrink-0
                 border border-white/[0.08] bg-white/[0.04]"
      style={{ width: size, height: size }}
    >
      <span
        aria-hidden
        className="absolute -inset-1 rounded-full blur-md pointer-events-none opacity-40"
        style={{ background: `radial-gradient(circle, ${color}55 0%, transparent 70%)` }}
      />
      <img
        src={src}
        alt=""
        width={size - 14}
        height={size - 14}
        className="relative z-10"
        loading="lazy"
      />
    </div>
  );
}

function NotifCard({
  item,
  delay,
  onAfterRead,
}: {
  item: NotifItem;
  delay?: number;
  onAfterRead: () => void;
}) {
  const meta = sourceMeta(item.source);
  const title = stripLeadingEmoji(item.title);

  async function markRead() {
    try {
      await api.markNotificationsRead([item.uid]);
      onAfterRead();
    } catch {
      /* ignore */
    }
  }

  function openInBrowser() {
    if (item.url) window.open(item.url, "_blank", "noopener,noreferrer");
  }

  return (
    <Surface
      level={2}
      hover
      className="p-3 animate-fade-in-up cursor-pointer"
      style={{ animationDelay: `${delay ?? 0}ms` }}
      onClick={openInBrowser}
    >
      <div className="flex items-start gap-3">
        <SourceAvatar src={meta.logo} color={meta.color} />

        <div className="min-w-0 flex-1">
          <header className="flex items-center justify-between gap-3 mb-0.5">
            <span className="text-[11px] uppercase tracking-[0.16em] text-text-dim/90 font-medium">
              {meta.label}
            </span>
            <span
              className="text-[10px] text-muted shrink-0"
              title={new Date(item.received_ts * 1000).toLocaleString()}
            >
              {formatRelative(item.received_ts)}
            </span>
          </header>
          <p className="text-sm text-text leading-snug font-medium truncate">{title}</p>
          {item.summary && (
            <p className="mt-1 text-xs text-text-dim leading-relaxed line-clamp-2">
              {item.summary}
            </p>
          )}
          <div className="mt-2 flex items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
            {item.url && (
              <Button variant="primary" size="sm" icon="play" onClick={openInBrowser}>
                Abrir
              </Button>
            )}
            <Button variant="ghost" size="sm" icon="check" onClick={markRead}>
              Marcar leída
            </Button>
          </div>
        </div>
      </div>
    </Surface>
  );
}
