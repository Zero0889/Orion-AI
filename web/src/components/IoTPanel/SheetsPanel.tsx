/**
 * SheetsPanel — sincronización continua de lecturas IoT con Google Sheets.
 *
 * Si está desconectado, muestra formulario de conexión (email + nombre del
 * sheet). Si está conectado, muestra: link al Sheet, última sync (formato
 * relativo "hace Xs/min/h"), filas pusheadas, intervalo editable, y
 * acciones (Sync ahora, Reformatear, Desconectar).
 *
 * Vive bajo un `GogScopeGuard` que valida los permisos `sheets` + `drive`
 * antes de instanciar — si el user no tiene ese scope, el guard muestra
 * un CTA para autorizar.
 */

import { useEffect, useState } from "react";

import { api } from "@/api/rest";
import { Icon } from "@/ui/Icon";
import { Badge, Button, Surface } from "@/ui/primitives";

export function SheetsPanel() {
  const [state, setState] = useState<import("@/api/rest").IoTSheetsState | null>(null);
  const [email, setEmail] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // tick para refrescar el "hace Xs" sin pegarle al backend
  const [, setTick] = useState(0);

  async function refresh() {
    try {
      setState(await api.iotSheetsStatus());
    } catch (e) {
      setErr(String(e));
    }
  }

  useEffect(() => {
    refresh();
  }, []);
  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), 5000);
    return () => clearInterval(id);
  }, []);

  async function doConnect() {
    if (!email.trim()) {
      setErr("Falta el email.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const s = await api.iotSheetsConnect({
        account: email.trim(),
        title: title.trim() || undefined,
      });
      setState(s);
      setEmail("");
      setTitle("");
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function doDisconnect() {
    setBusy(true);
    setErr(null);
    try {
      setState(await api.iotSheetsDisconnect());
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function doSyncNow() {
    setBusy(true);
    setErr(null);
    try {
      await api.iotSheetsSyncNow();
      // El sync corre en background, esperamos un tiquito y re-fetch.
      setTimeout(() => {
        refresh();
        setBusy(false);
      }, 1500);
    } catch (e) {
      setErr(String(e));
      setBusy(false);
    }
  }

  async function doReformat() {
    setBusy(true);
    setErr(null);
    try {
      await api.iotSheetsReformat();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function saveInterval(secs: number) {
    setBusy(true);
    setErr(null);
    try {
      setState(await api.iotSheetsSetInterval(secs));
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!state) {
    return <p className="text-sm text-text-dim italic">Cargando…</p>;
  }

  // ── Disconnected: formulario de conexión ────────────────────────
  if (!state.enabled) {
    return (
      <Surface level={2} className="p-4">
        <div className="flex items-start gap-3 mb-3">
          <span
            className="grid place-items-center h-9 w-9 rounded-lg
                           bg-acc/10 border border-acc/30 text-acc shrink-0"
          >
            <Icon name="upload" size={16} />
          </span>
          <div className="min-w-0">
            <h4 className="text-[15px] font-medium leading-tight">Sincronizar con Google Sheets</h4>
            <p className="mt-0.5 text-[12px] text-text-dim leading-snug">
              ORION va a crear un Sheet nuevo y le pushea las lecturas cada 5 minutos. Necesita que
              tu cuenta tenga el scope <code className="text-acc font-mono">sheets</code> autorizado
              en gog.
            </p>
          </div>
        </div>

        <div className="grid gap-2 mt-3">
          <input
            type="email"
            placeholder="tu-email@gmail.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={busy}
            className="w-full px-3 py-2 rounded-md border border-white/[0.08]
                       bg-bg/40 text-sm focus:outline-none focus:border-acc/60"
          />
          <input
            type="text"
            placeholder="Nombre del Sheet (opcional)"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            disabled={busy}
            className="w-full px-3 py-2 rounded-md border border-white/[0.08]
                       bg-bg/40 text-sm focus:outline-none focus:border-acc/60"
          />
          <div className="flex justify-end mt-1">
            <Button
              variant="primary"
              size="sm"
              icon="upload"
              disabled={busy || !email.trim()}
              onClick={doConnect}
            >
              {busy ? "Conectando…" : "Conectar"}
            </Button>
          </div>
          {err && (
            <div
              className="mt-1 flex items-start gap-2 p-2 rounded-md
                            border border-danger/30 bg-danger/10 text-xs text-danger"
            >
              <Icon name="alert" size={13} className="mt-0.5 shrink-0" />
              <span className="break-all">{err}</span>
            </div>
          )}
        </div>
      </Surface>
    );
  }

  // ── Connected: dashboard ────────────────────────────────────────
  const ageStr = state.last_sync_at ? formatAge(state.last_sync_at) : "nunca";

  return (
    <Surface level={2} className="p-4">
      <div className="flex items-start gap-3">
        <span
          className="grid place-items-center h-9 w-9 rounded-lg
                         bg-ok/15 border border-ok/40 text-ok shrink-0"
        >
          <Icon name="check" size={16} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h4 className="text-[15px] font-medium leading-tight">Sheet conectado</h4>
            <Badge tone="info" dot>
              live
            </Badge>
          </div>
          <div className="mt-0.5 text-[12px] text-text-dim font-mono break-all">
            {state.account}
          </div>
        </div>
        <Button variant="ghost" size="sm" icon="close" onClick={doDisconnect} disabled={busy}>
          Desconectar
        </Button>
      </div>

      <div className="mt-3 grid sm:grid-cols-3 gap-2">
        <Surface level={2} className="p-3 bg-bg/40">
          <div className="text-[10px] uppercase tracking-[0.18em] text-text-dim">Última sync</div>
          <div className="mt-0.5 text-sm tabular-nums">{ageStr}</div>
        </Surface>
        <Surface level={2} className="p-3 bg-bg/40">
          <div className="text-[10px] uppercase tracking-[0.18em] text-text-dim">
            Filas pusheadas
          </div>
          <div className="mt-0.5 text-sm font-mono tabular-nums">
            {state.last_pushed_row.toLocaleString()}
          </div>
        </Surface>
        <IntervalControl value={state.sync_interval_s} disabled={busy} onSave={saveInterval} />
      </div>

      {state.spreadsheet_url && (
        <a
          href={state.spreadsheet_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 flex items-center gap-2 px-3 py-2 rounded-md
                     border border-acc/30 bg-acc/10 text-sm text-acc
                     hover:bg-acc/15 transition-colors"
        >
          <Icon name="chart" size={14} />
          <span className="flex-1 truncate font-mono">{state.spreadsheet_url}</span>
          <Icon name="arrow-right" size={13} />
        </a>
      )}

      <div className="mt-3 flex justify-end gap-1.5">
        <Button
          variant="ghost"
          size="sm"
          icon="edit"
          onClick={doReformat}
          disabled={busy}
          title="Reaplica cabecera, freeze, formato de fechas y bandas al Sheet"
        >
          Reformatear
        </Button>
        <Button variant="ghost" size="sm" icon="bolt" onClick={doSyncNow} disabled={busy}>
          {busy ? "Sincronizando…" : "Sync ahora"}
        </Button>
      </div>

      {state.last_error && (
        <div
          className="mt-3 flex items-start gap-2 p-2 rounded-md
                        border border-danger/30 bg-danger/10 text-xs text-danger"
        >
          <Icon name="alert" size={13} className="mt-0.5 shrink-0" />
          <span className="break-all">{state.last_error}</span>
        </div>
      )}
    </Surface>
  );
}

/* ── INTERVAL CONTROL ─────────────────────────────────────────────── */
// Permite editar `sync_interval_s` desde la UI. Acepta 10..3600 s y
// guarda solo cuando cambia respecto al valor del backend, para evitar
// PUTs ruidosos cuando el usuario abre/cierra el panel.
function IntervalControl({
  value,
  disabled,
  onSave,
}: {
  value: number;
  disabled: boolean;
  onSave: (s: number) => void;
}) {
  const [draft, setDraft] = useState<string>(String(value));
  useEffect(() => {
    setDraft(String(value));
  }, [value]);

  const parsed = Number(draft);
  const isValid = Number.isFinite(parsed) && parsed >= 10 && parsed <= 3600;
  const dirty = isValid && parsed !== value;

  function commit() {
    if (!dirty) return;
    onSave(Math.round(parsed));
  }

  return (
    <Surface level={2} className="p-3 bg-bg/40">
      <div className="text-[10px] uppercase tracking-[0.18em] text-text-dim">Sync cada</div>
      <div className="mt-1 flex items-center gap-1.5">
        <input
          type="number"
          min={10}
          max={3600}
          step={5}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
          }}
          disabled={disabled}
          className="w-16 px-2 py-1 rounded-md border border-white/[0.08]
                     bg-bg/40 text-sm font-mono tabular-nums
                     focus:outline-none focus:border-acc/60"
        />
        <span className="text-[11px] text-text-dim">seg</span>
        {dirty && (
          <button
            onClick={commit}
            disabled={disabled || !isValid}
            className="ml-auto px-2 py-1 rounded-md text-[11px]
                       border border-acc/40 bg-acc/10 text-acc
                       hover:bg-acc/20 disabled:opacity-40 transition-colors"
          >
            Guardar
          </button>
        )}
      </div>
      {!isValid && <div className="mt-1 text-[10px] text-danger">10 – 3600 s</div>}
    </Surface>
  );
}

function formatAge(iso: string): string {
  const past = new Date(iso).getTime();
  if (isNaN(past)) return iso;
  const secs = Math.max(0, Math.floor((Date.now() - past) / 1000));
  if (secs < 60) return `hace ${secs}s`;
  if (secs < 3600) return `hace ${Math.floor(secs / 60)} min`;
  return `hace ${Math.floor(secs / 3600)} h`;
}
