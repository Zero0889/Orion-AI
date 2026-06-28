/**
 * AccessPanel — Control de acceso por huella dactilar (ESP32 + AS608).
 *
 * Tres tabs:
 *   · Reporte diario — la "tabla excel" agrupada por usuario+fecha.
 *   · Registros      — eventos crudos paginados.
 *   · Usuarios       — CRUD del mapping huella_id ↔ persona.
 *
 * Bridge WS: cada `access.event` que recibe el store dispara una
 * invalidación de `QUERY_KEYS.access.all` — los tabs se refrescan solos
 * en cuanto el ESP32 envía un nuevo registro.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  api,
  type AccessDailyRow,
  type AccessEvent,
  type AccessEventsPage,
  type AccessUser,
} from "@/api/rest";
import { inferBackendUrl } from "@/api/ws";
import { QUERY_KEYS } from "@/query/keys";
import { toast } from "@/stores/toast";
import { Icon } from "@/ui/Icon";
import { Badge, Empty, SectionHeader, Surface } from "@/ui/primitives";

import { DailyReportTab } from "./DailyReportTab";
import { EventsTab } from "./EventsTab";
import { UsersTab } from "./UsersTab";

type Tab = "daily" | "events" | "users";

export function AccessPanel() {
  const [tab, setTab] = useState<Tab>("daily");

  const { data: users = [], error: usersError } = useQuery<AccessUser[]>({
    queryKey: QUERY_KEYS.access.users,
    queryFn: () => api.accessUsers(),
  });
  const { data: eventsPage, error: eventsError } = useQuery<AccessEventsPage>({
    queryKey: QUERY_KEYS.access.events({ limit: 200 }),
    queryFn: () => api.accessListEvents({ limit: 200 }),
  });
  const { data: daily = [], error: dailyError } = useQuery<AccessDailyRow[]>({
    queryKey: QUERY_KEYS.access.daily(),
    queryFn: () => api.accessDaily(),
  });

  const events = eventsPage?.items ?? [];
  const totalEvents = eventsPage?.total ?? 0;
  const enrolledCount = users.length;
  const todayCount = daily.length;

  const queryError = usersError ?? eventsError ?? dailyError;
  const errorMsg = queryError ? String(queryError) : null;

  const { http } = inferBackendUrl();

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <SectionHeader
        eyebrow="Sistema"
        title="Acceso por huella"
        hint="Registros del ESP32 + reporte diario por persona. Cada lectura notifica por Telegram si está configurado."
        action={
          <div className="flex items-center gap-2 flex-wrap">
            <Badge tone="info" dot>
              {enrolledCount} enrolados
            </Badge>
            <Badge tone="accent">{totalEvents} eventos</Badge>
            <a
              href={`${http}/api/access/export.xlsx`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2 rounded-md font-medium
                         h-8 px-3 text-xs
                         bg-elevated text-text border border-white/[0.06]
                         hover:border-white/[0.14] transition-colors"
              title="Descargar reporte XLSX"
            >
              <Icon name="download" size={14} />
              XLSX
            </a>
            <a
              href={`${http}/api/access/export.csv`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2 rounded-md font-medium
                         h-8 px-3 text-xs
                         bg-elevated text-text border border-white/[0.06]
                         hover:border-white/[0.14] transition-colors"
              title="Descargar reporte CSV"
            >
              <Icon name="download" size={14} />
              CSV
            </a>
          </div>
        }
      />

      {/* Tabs */}
      <div
        className="px-4 sm:px-6 pt-3 flex items-center gap-1 border-b border-white/[0.05]
                   overflow-x-auto scrollbar-thin"
      >
        <TabButton active={tab === "daily"} onClick={() => setTab("daily")}>
          <Icon name="shield" size={13} />
          Reporte diario
          <span className="ml-1 text-text-dim">{todayCount}</span>
        </TabButton>
        <TabButton active={tab === "events"} onClick={() => setTab("events")}>
          <Icon name="history" size={13} />
          Registros
          <span className="ml-1 text-text-dim">{totalEvents}</span>
        </TabButton>
        <TabButton active={tab === "users"} onClick={() => setTab("users")}>
          <Icon name="agents" size={13} />
          Usuarios
          <span className="ml-1 text-text-dim">{enrolledCount}</span>
        </TabButton>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {errorMsg && (
          <div
            className="mx-4 sm:mx-6 mt-3 flex items-start gap-2 p-3 rounded-md
                       border border-danger/30 bg-danger/10 text-xs text-danger"
          >
            <Icon name="alert" size={14} className="mt-0.5 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {tab === "daily" && <DailyReportTab rows={daily} />}
        {tab === "events" && <EventsTab events={events} totalEvents={totalEvents} />}
        {tab === "users" && <UsersTab users={users} />}
      </div>
    </div>
  );
}

/* ── Tab button (idéntico patrón al de MCPPanel) ─────────────────────── */
function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={[
        "relative inline-flex items-center gap-1.5 px-3 h-8 text-xs font-medium shrink-0 whitespace-nowrap",
        "rounded-t-md transition-colors duration-150",
        active ? "text-text bg-elevated/40" : "text-text-dim hover:text-text hover:bg-white/[0.03]",
      ].join(" ")}
    >
      {children}
      {active && (
        <span
          aria-hidden
          className="absolute left-2 right-2 -bottom-px h-[2px] rounded-full bg-pri
                     shadow-[0_0_8px_rgb(var(--orion-pri)/0.6)]"
        />
      )}
    </button>
  );
}

/* ── Helper compartido por las tabs ───────────────────────────────────── */

export function AccessEmpty({
  icon,
  title,
  hint,
}: {
  icon: "shield" | "history" | "agents";
  title: string;
  hint: string;
}) {
  return (
    <div className="px-4 sm:px-6 py-8">
      <Empty icon={icon} title={title} hint={hint} />
    </div>
  );
}

/* ── Mutations compartidas ───────────────────────────────────────────── */

export function useDeleteUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.accessDeleteUser(id),
    onSuccess: () => {
      toast.success("Usuario eliminado");
      qc.invalidateQueries({ queryKey: QUERY_KEYS.access.all });
    },
    onError: (e) => toast.error("No pude borrar", String(e)),
  });
}

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { fingerprint_id: number; name: string; phone?: string }) =>
      api.accessCreateUser(body),
    onSuccess: (user) => {
      toast.success("Huella enrolada", `${user.name} (slot #${user.fingerprint_id})`);
      qc.invalidateQueries({ queryKey: QUERY_KEYS.access.all });
    },
    onError: (e) => toast.error("No pude enrolar", String(e)),
  });
}

export function useUpdateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: string;
      body: Partial<{ name: string; phone: string; active: boolean }>;
    }) => api.accessUpdateUser(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.access.all });
    },
    onError: (e) => toast.error("No pude actualizar", String(e)),
  });
}

/* ── Helpers de formato (compartidos por tabs) ───────────────────────── */

export function formatFecha(iso: string): string {
  if (iso.length !== 10) return iso;
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

export function formatTimestamp(iso: string): string {
  // "2026-06-27T14:23:45+00:00" → "27/06/2026 14:23:45"
  if (iso.length < 19) return iso;
  const date = iso.slice(0, 10);
  const time = iso.slice(11, 19);
  return `${formatFecha(date)} ${time}`;
}

export function eventTypeColor(t: AccessEvent["event_type"]): "success" | "danger" | "info" {
  if (t === "GRANTED") return "success";
  if (t === "DENIED") return "danger";
  return "info";
}

/* ── Surface re-export para tabs (atajo de import) ───────────────────── */
export { Surface };
