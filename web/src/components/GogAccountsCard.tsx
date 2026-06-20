/**
 * GogAccountsCard — gestión de cuentas Google sin terminal.
 *
 * Listado de cuentas + servicios autorizados + flujo de auth en vivo.
 * Se monta en Ajustes → Integraciones.
 *
 * Polling fino (2s) mientras hay un auth flow corriendo, lento (15s) en
 * idle. El mismo patrón que NotebookLMCard.
 */

import { useCallback, useEffect, useState } from "react";

import { api, type GogAccount, type GogFlowStatus, type GogService } from "@/api/rest";
import { toast } from "@/stores/toast";
import { Icon } from "@/ui/Icon";
import { Badge, Button, Surface } from "@/ui/primitives";

// Catalogo cosmetico para los servicios mas comunes (icono + label
// humano). Si llega uno desconocido, cae a "ti-default".
const SERVICE_META: Record<string, { label: string; hint?: string }> = {
  gmail: { label: "Gmail", hint: "Leer y gestionar mails" },
  calendar: { label: "Calendar", hint: "Eventos y recordatorios" },
  classroom: { label: "Classroom", hint: "Cursos y tareas" },
  drive: { label: "Drive", hint: "Archivos en la nube" },
  sheets: { label: "Sheets", hint: "Hojas de cálculo" },
  docs: { label: "Docs", hint: "Documentos" },
  slides: { label: "Slides", hint: "Presentaciones" },
  contacts: { label: "Contactos", hint: "Agenda" },
  tasks: { label: "Tasks", hint: "Lista de tareas" },
  chat: { label: "Chat", hint: "Mensajería" },
  meet: { label: "Meet", hint: "Videollamadas" },
  youtube: { label: "YouTube", hint: "Canal y videos" },
  photos: { label: "Photos", hint: "Galería de fotos" },
  forms: { label: "Forms", hint: "Formularios" },
  people: { label: "People", hint: "Personas" },
};

interface Props {
  /** Servicios pre-marcados al abrir el modal. Si no, todos del catálogo. */
  defaultServices?: string[];
}

export function GogAccountsCard({ defaultServices }: Props = {}) {
  const [accounts, setAccounts] = useState<GogAccount[] | null>(null);
  const [services, setServices] = useState<GogService[] | null>(null);
  const [flow, setFlow] = useState<GogFlowStatus>({ status: "idle" });
  const [modalOpen, setModalOpen] = useState(false);
  const [modalPrefill, setModalPrefill] = useState<{ account?: string; services?: string[] }>({});

  const refresh = useCallback(async () => {
    try {
      const [a, s, f] = await Promise.all([
        api.gogAccounts(),
        api.gogServices(),
        api.gogFlowStatus(),
      ]);
      setAccounts(a);
      setServices(s);
      setFlow(f);
    } catch (e) {
      console.warn("gog refresh falló:", e);
    }
  }, []);

  // Initial load
  useEffect(() => {
    refresh();
  }, [refresh]);

  // Poll dinámico — 2s mientras corre auth, 15s en idle.
  useEffect(() => {
    const id = window.setInterval(refresh, flow.status === "running" ? 2000 : 15000);
    return () => window.clearInterval(id);
  }, [flow.status, refresh]);

  // Si el flow cambió de running a success/error, toast y reset
  useEffect(() => {
    if (flow.status === "success") {
      toast.success("Cuenta autorizada", flow.account || "");
      api
        .gogResetAuth()
        .then(setFlow)
        .catch(() => {});
    } else if (flow.status === "error") {
      toast.error("La autorización falló", flow.message || "Probá de nuevo");
      api
        .gogResetAuth()
        .then(setFlow)
        .catch(() => {});
    } else if (flow.status === "cancelled") {
      api
        .gogResetAuth()
        .then(setFlow)
        .catch(() => {});
    }
  }, [flow.status, flow.account, flow.message]);

  function openAdd(prefill?: { account?: string; services?: string[] }) {
    setModalPrefill(prefill || {});
    setModalOpen(true);
  }

  async function startAuth(account: string, selected: string[]) {
    try {
      const s = await api.gogStartAuth({ account, services: selected });
      setFlow(s);
      toast.info("Autorización iniciada", "Se abrirá el navegador para que des consentimiento.");
      setModalOpen(false);
    } catch (e) {
      toast.error("No pude arrancar la autorización", String(e));
    }
  }

  async function cancelAuth() {
    try {
      setFlow(await api.gogCancelAuth());
    } catch {
      /* cancel best-effort */
    }
  }

  return (
    <Surface level={2} className="p-4">
      <div className="flex items-start gap-3 mb-3">
        <span
          className="grid place-items-center h-9 w-9 rounded-lg
                         bg-acc/10 border border-acc/30 text-acc shrink-0"
        >
          <Icon name="shield" size={16} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h4 className="text-[15px] font-medium leading-tight">Cuentas Google</h4>
            {accounts && accounts.length > 0 && <Badge tone="info">{accounts.length}</Badge>}
          </div>
          <p className="text-[12px] text-text-dim leading-snug mt-0.5">
            Gestioná los permisos de Google sin abrir terminal. Click en{" "}
            <strong>Agregar permisos</strong> para autorizar servicios nuevos.
          </p>
        </div>
        <Button
          variant="primary"
          size="sm"
          icon="plus"
          onClick={() => openAdd({ services: defaultServices })}
          disabled={flow.status === "running"}
        >
          Agregar cuenta
        </Button>
      </div>

      {/* flow en curso */}
      {flow.status === "running" && (
        <div
          className="mb-3 flex items-start gap-2 p-3 rounded-md
                        border border-acc/30 bg-acc/10 text-sm"
        >
          <Icon name="orbit" size={16} className="mt-0.5 shrink-0 text-acc animate-spin" />
          <div className="flex-1 min-w-0">
            <div className="font-medium">Esperando consentimiento…</div>
            <div className="text-[12px] text-text-dim mt-0.5">
              {flow.account} • {flow.services?.join(", ")}
            </div>
            {flow.auth_url && (
              <a
                href={flow.auth_url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1 inline-block text-[11px] text-acc underline break-all"
              >
                Si no se abrió, hacé click acá
              </a>
            )}
          </div>
          <Button variant="ghost" size="sm" icon="close" onClick={cancelAuth}>
            Cancelar
          </Button>
        </div>
      )}

      {/* listado de cuentas */}
      {accounts === null ? (
        <p className="text-sm text-text-dim italic">Cargando…</p>
      ) : accounts.length === 0 ? (
        <Surface level={2} className="p-4 bg-bg/40 text-center">
          <Icon name="shield" size={20} className="mx-auto text-text-dim mb-1.5" />
          <p className="text-sm">Sin cuentas autorizadas todavía.</p>
          <p className="text-[12px] text-text-dim mt-0.5">
            Tocá <strong>Agregar cuenta</strong> para empezar.
          </p>
        </Surface>
      ) : (
        <div className="flex flex-col gap-2">
          {accounts.map((acc) => (
            <AccountRow
              key={acc.email}
              account={acc}
              allServices={services || []}
              onAddPerms={(extra) =>
                openAdd({ account: acc.email, services: [...acc.services, ...extra] })
              }
              disabled={flow.status === "running"}
            />
          ))}
        </div>
      )}

      {modalOpen && (
        <AuthModal
          prefillAccount={modalPrefill.account}
          prefillServices={modalPrefill.services}
          allServices={services || []}
          onCancel={() => setModalOpen(false)}
          onConfirm={startAuth}
        />
      )}
    </Surface>
  );
}

/* ── ACCOUNT ROW ──────────────────────────────────────────────────── */
function AccountRow({
  account,
  allServices,
  onAddPerms,
  disabled,
}: {
  account: GogAccount;
  allServices: GogService[];
  onAddPerms: (extraServices: string[]) => void;
  disabled: boolean;
}) {
  const authorized = new Set(account.services.map((s) => s.toLowerCase()));
  const catalogIds = allServices.map((s) => s.service);
  const notAuth = catalogIds.filter((s) => !authorized.has(s.toLowerCase()));

  return (
    <Surface level={2} className="p-3 bg-bg/40">
      <div className="flex items-center gap-2 mb-2">
        <Icon name="check" size={14} className="text-ok" />
        <span className="text-sm font-mono break-all flex-1">{account.email}</span>
        {notAuth.length > 0 && !disabled && (
          <Button variant="ghost" size="sm" icon="plus" onClick={() => onAddPerms(notAuth)}>
            Agregar permisos
          </Button>
        )}
      </div>
      <div className="flex flex-wrap gap-1">
        {account.services.length === 0 ? (
          <span className="text-[11px] text-text-dim italic">Sin servicios</span>
        ) : (
          account.services.sort().map((s) => <ServiceChip key={s} service={s} authorized />)
        )}
        {notAuth.slice(0, 5).map((s) => (
          <ServiceChip key={s} service={s} authorized={false} />
        ))}
        {notAuth.length > 5 && (
          <span className="text-[10px] text-muted self-center">+{notAuth.length - 5} más</span>
        )}
      </div>
    </Surface>
  );
}

function ServiceChip({ service, authorized }: { service: string; authorized: boolean }) {
  const meta = SERVICE_META[service];
  const label = meta?.label || service;
  return (
    <span
      title={meta?.hint || ""}
      className={
        authorized
          ? "px-2 py-0.5 rounded-full text-[10px] uppercase tracking-[0.14em] " +
            "bg-ok/15 text-ok border border-ok/30"
          : "px-2 py-0.5 rounded-full text-[10px] uppercase tracking-[0.14em] " +
            "bg-white/[0.04] text-text-dim border border-white/[0.06] line-through"
      }
    >
      {label}
    </span>
  );
}

/* ── MODAL DE AUTH ────────────────────────────────────────────────── */
function AuthModal({
  prefillAccount,
  prefillServices,
  allServices,
  onCancel,
  onConfirm,
}: {
  prefillAccount?: string;
  prefillServices?: string[];
  allServices: GogService[];
  onCancel: () => void;
  onConfirm: (account: string, services: string[]) => void;
}) {
  const [email, setEmail] = useState(prefillAccount || "");
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(prefillServices || ["gmail", "drive", "sheets"]),
  );

  function toggle(svc: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(svc)) next.delete(svc);
      else next.add(svc);
      return next;
    });
  }

  const canSubmit = email.trim() && selected.size > 0;

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/60 backdrop-blur-sm"
      onClick={onCancel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-[min(560px,90vw)] max-h-[85vh] overflow-auto
                      rounded-xl border border-white/[0.08] bg-elevated p-5 shadow-2xl"
      >
        <div className="flex items-start gap-3 mb-4">
          <span
            className="grid place-items-center h-9 w-9 rounded-lg
                           bg-acc/15 border border-acc/40 text-acc shrink-0"
          >
            <Icon name="shield" size={16} />
          </span>
          <div className="flex-1">
            <h3 className="text-lg font-medium leading-tight">
              {prefillAccount ? "Agregar permisos" : "Conectar cuenta Google"}
            </h3>
            <p className="text-[12px] text-text-dim mt-0.5">
              Al confirmar, se abrirá el navegador para que des consentimiento. Marcá{" "}
              <strong>todos</strong> los checkboxes en la pantalla de Google.
            </p>
          </div>
        </div>

        <div className="mb-3">
          <label className="block text-[11px] uppercase tracking-[0.18em] text-text-dim mb-1">
            Email
          </label>
          <input
            type="email"
            placeholder="tu-email@gmail.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={!!prefillAccount}
            className="w-full px-3 py-2 rounded-md border border-white/[0.08]
                       bg-bg/40 text-sm focus:outline-none focus:border-acc/60
                       disabled:opacity-60"
          />
        </div>

        <div className="mb-4">
          <label className="block text-[11px] uppercase tracking-[0.18em] text-text-dim mb-2">
            Servicios ({selected.size} seleccionados)
          </label>
          <div className="grid grid-cols-2 gap-1.5">
            {allServices.length === 0 && (
              <span className="text-xs text-text-dim italic col-span-2">Cargando catálogo…</span>
            )}
            {allServices.map((svc) => {
              const meta = SERVICE_META[svc.service];
              const checked = selected.has(svc.service);
              return (
                <label
                  key={svc.service}
                  className={
                    "flex items-start gap-2 p-2 rounded-md cursor-pointer transition-colors " +
                    (checked
                      ? "bg-acc/10 border border-acc/30"
                      : "bg-bg/40 border border-white/[0.06] hover:bg-white/[0.04]")
                  }
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggle(svc.service)}
                    className="mt-1 accent-acc"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm leading-tight">{meta?.label || svc.service}</div>
                    {meta?.hint && (
                      <div className="text-[10px] text-text-dim leading-tight">{meta.hint}</div>
                    )}
                  </div>
                </label>
              );
            })}
          </div>
        </div>

        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onCancel}>
            Cancelar
          </Button>
          <Button
            variant="primary"
            size="sm"
            icon="shield"
            disabled={!canSubmit}
            onClick={() => onConfirm(email.trim(), Array.from(selected))}
          >
            Autorizar
          </Button>
        </div>
      </div>
    </div>
  );
}
