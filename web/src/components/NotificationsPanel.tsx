/**
 * NotificationsPanel — bandeja unificada con avatares por fuente.
 *
 * Cada card muestra el logo de la fuente (Gmail, Classroom, Drive…) en
 * un avatar circular con halo del color de marca. Los filtros agrupan
 * por google / sistema / extensiones / otros, además de mantener el
 * filtro por fuente puntual.
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { api, type NotifItem, type NotifPollerStatus } from "@/api/rest";
import { humanizeUnix } from "@/lib/humanTime";
import {
  sourceMeta,
  stripLeadingEmoji,
  formatRelative,
  type SourceGroup,
} from "@/lib/notificationSource";
import { QUERY_KEYS } from "@/query/keys";
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
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<Filter>("all");
  const [pickError, setPickError] = useState<string | null>(null);
  const [authorizing, setAuthorizing] = useState(false);

  // Lista filtrada — el backend acepta `unread`. Los grupos (google,
  // system, etc.) los filtramos client-side abajo porque combinan
  // múltiples sources.
  const onlyUnread = filter === "unread";
  const {
    data: items = [],
    isFetching: listFetching,
    error: listError,
  } = useQuery<NotifItem[]>({
    queryKey: QUERY_KEYS.notificationsList(onlyUnread),
    queryFn: () => api.listNotifications(onlyUnread ? { unread: true } : {}),
  });

  const {
    data: status = null,
    isFetching: statusFetching,
    error: statusError,
  } = useQuery<NotifPollerStatus>({
    queryKey: QUERY_KEYS.notificationsStatus,
    queryFn: () => api.notificationsStatus(),
  });

  const loading = listFetching || statusFetching;
  const queryError = listError ?? statusError;
  const error = pickError ?? (queryError ? String(queryError) : null);

  // Sync del contador de la campana con la lista visible — el bridge
  // WS ya mantiene `unreadNotifs` por evento (notification.new/.read),
  // pero el render del panel también lo refleja por consistencia con
  // el comportamiento anterior.
  useEffect(() => {
    useOrionStore.setState({ unreadNotifs: items.length });
  }, [items.length]);

  const invalidateAll = () => queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notifications });

  async function pollNow(src?: string) {
    try {
      await api.pollNotifications(src);
      await invalidateAll();
    } catch (e) {
      setPickError(String(e));
    }
  }

  async function markAllRead(src?: string) {
    try {
      await api.markAllNotificationsRead(src);
      await invalidateAll();
    } catch (e) {
      setPickError(String(e));
    }
  }

  async function authorizeClassroom() {
    setAuthorizing(true);
    setPickError(null);
    try {
      await api.authorizeClassroom();
      await api.pollNotifications("classroom");
      await invalidateAll();
    } catch (e) {
      setPickError(String(e));
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

        <SetupRequiredBanner status={status} />

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
            <NotifCard key={it.uid} item={it} delay={i * 25} onAfterRead={invalidateAll} />
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

/** Banner accionable cuando el OAuth client está roto en Google Cloud
 *  (deleted_client / invalid_client). El fix es manual y de una sola vez
 *  — apuntamos a la guía. Mostramos las fuentes afectadas y un link
 *  a `docs/SETUP_GOOGLE_OAUTH.md` para que el usuario sepa por dónde
 *  arrancar. */
function SetupRequiredBanner({ status }: { status: NotifPollerStatus | null }) {
  if (!status) return null;
  const affected = Object.entries(status.last_status).filter(
    ([, s]) => s.error_kind === "setup_required",
  );
  // Fallback al map derivado `setup_required` por si llegara antes que
  // last_status (race del primer fetch).
  if (affected.length === 0 && status.setup_required) {
    const fromMap = Object.entries(status.setup_required)
      .filter(([, v]) => v)
      .map(([k]) => [k, { user_message: undefined, doc: null }] as const);
    if (fromMap.length === 0) return null;
    return renderBanner(fromMap as ReadonlyArray<readonly [string, BannerSource]>);
  }
  if (affected.length === 0) return null;
  return renderBanner(
    affected.map(
      ([src, s]) =>
        [src, { user_message: s.user_message, doc: s.doc ?? null } as BannerSource] as const,
    ),
  );
}

type BannerSource = { user_message?: string; doc?: string | null };

function renderBanner(entries: ReadonlyArray<readonly [string, BannerSource]>) {
  // user_message es el mismo para todas las fuentes afectadas si el motivo
  // es el client OAuth borrado. Tomamos el primero no-vacío.
  const msg =
    entries.map(([, s]) => s.user_message).find(Boolean) ??
    "Tu cliente OAuth de Google fue invalidado. Tenés que crear uno nuevo en Google Cloud Console.";
  const doc = entries.map(([, s]) => s.doc).find(Boolean) ?? "docs/SETUP_GOOGLE_OAUTH.md";
  const labels = entries.map(([src]) => sourceMeta(src).label).join(" · ");
  return (
    <Surface
      level={2}
      className="mb-4 p-4 border border-danger/40 bg-danger/[0.08] flex items-start gap-3"
    >
      <span className="grid place-items-center h-9 w-9 rounded-md bg-danger/15 text-danger shrink-0">
        <Icon name="alert" size={18} />
      </span>
      <div className="flex-1 min-w-0">
        <div className="text-[12px] uppercase tracking-[0.18em] text-danger font-medium mb-1">
          Reconectar Google
        </div>
        <p className="text-sm text-text leading-snug">{msg}</p>
        <p className="text-[11px] text-text-dim mt-1">Afecta: {labels}</p>
        <p className="text-[11px] text-text-dim mt-2">
          Pasos en <code className="text-text bg-white/[0.05] px-1.5 py-0.5 rounded">{doc}</code> —
          toma ~5 min, se hace una sola vez por instalación.
        </p>
      </div>
    </Surface>
  );
}

function SourceStatusGrid({
  status,
  onPoll,
}: {
  status: NotifPollerStatus | null;
  onPoll: (src?: string) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  if (!status) return null;
  const sources = Object.entries(status.last_status);
  if (sources.length === 0) return null;
  const broken = sources.filter(([, s]) => !s.ok);
  // BRIEF · Notificaciones: si hay 2+ fuentes con problema NO mostramos
  // 2 cards expandidas (lo que el brief describe como "2 banners rojos
  // demasiado agresivos"). Las colapsamos en un único banner ámbar
  // "N integraciones necesitan atención" con botón para expandir el
  // detalle. Con una sola fuente con problema mostramos el grid
  // directo (la card individual ya es discreta).
  const useCollapsedBanner = broken.length >= 2 && !showAll;

  if (useCollapsedBanner) {
    return (
      <Surface
        level={2}
        className="mb-4 p-3 flex items-center gap-3 border border-warn/30 bg-warn/[0.05]"
      >
        <span className="grid place-items-center h-8 w-8 rounded-md bg-warn/15 text-warn shrink-0">
          <Icon name="alert" size={16} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-[12px] font-medium text-text">
            {broken.length} integraciones necesitan atención
          </div>
          <div className="text-[11px] text-text-dim truncate">
            {broken.map(([src]) => sourceMeta(src).label).join(" · ")}
          </div>
        </div>
        <Button variant="ghost" size="sm" icon="chevron-down" onClick={() => setShowAll(true)}>
          Ver detalle
        </Button>
      </Surface>
    );
  }

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
                    // BRIEF G3: OAuth vencido / sesión caducada NO es error
                    // crítico del sistema, es atención pendiente del
                    // usuario. Ámbar, no rojo.
                    <Badge tone="warn" dot>
                      Atención
                    </Badge>
                  )}
                </div>
                {!s.ok && s.error && (
                  <p className="text-[10px] text-warn mt-1 truncate" title={s.error}>
                    {sanitizeSourceError(s.error)}
                  </p>
                )}
                {s.ok && s.ts && (
                  <p className="text-[10px] text-muted mt-1">Último poll: {humanizeUnix(s.ts)}</p>
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
    // BRIEF · Notificaciones: cada fila lleva un dot/línea acento del
    // color de la fuente — así se identifica de un vistazo de dónde
    // viene la notificación sin tener que parsear el avatar. El border
    // se intensifica al hover.
    <Surface
      level={2}
      hover
      className="group relative p-3 animate-fade-in-up cursor-pointer
                 transition-transform duration-300 ease-spring hover:-translate-y-0.5"
      style={{
        animationDelay: `${delay ?? 0}ms`,
        ["--notif-accent" as string]: meta.color,
      }}
      onClick={openInBrowser}
    >
      <span
        aria-hidden
        className="absolute left-0 top-3 bottom-3 w-[2px] rounded-r-full transition-opacity duration-300 opacity-60 group-hover:opacity-100"
        style={{
          background: meta.color,
          boxShadow: `0 0 8px ${meta.color}80`,
        }}
      />
      <div className="flex items-start gap-3 pl-1">
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

/* ── Sanitización del error de fuente (BRIEF · Notificaciones) ────────
   "NUNCA mostrar URLs completas en la UI." Los errores de OAuth suelen
   venir con la URL de autenticación pegada — la reemplazamos por un
   marcador legible. El error original queda en el `title` por si el
   usuario power necesita inspeccionarlo. */
function sanitizeSourceError(raw: string): string {
  return raw
    .replace(/https?:\/\/\S+/gi, "[enlace]")
    .replace(/\s+/g, " ")
    .trim();
}
