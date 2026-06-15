/**
 * GogScopeGuard — wrapper que verifica si una cuenta tiene los scopes de gog
 * autorizados antes de mostrar una feature. Si faltan, muestra un banner
 * con call-to-action que dispara el flow de auth.
 *
 * Uso:
 *
 *   <GogScopeGuard requires={["sheets", "drive"]} account="zahir@gmail.com">
 *     <SheetsFeature />
 *   </GogScopeGuard>
 *
 * - account es opcional. Si no se pasa, agarra el primero de gogAccounts().
 * - cache local de 30s para no re-chequear en cada render.
 * - cuando termina un auth flow exitoso, re-fetch y muestra el children.
 */

import { useCallback, useEffect, useState } from "react";

import { api, type GogAccount } from "@/api/rest";
import { Icon } from "@/ui/Icon";
import { Button, Surface } from "@/ui/primitives";

import { GogAccountsCard } from "./GogAccountsCard";

interface Props {
  requires:  string[];
  account?:  string;
  children:  React.ReactNode;
  /** Título mostrado en el banner cuando faltan scopes. */
  title?:    string;
}

type CheckState =
  | { kind: "loading" }
  | { kind: "ok"; account: string }
  | { kind: "no_accounts" }
  | { kind: "missing"; account: string; missing: string[] }
  | { kind: "error"; message: string };

export function GogScopeGuard({ requires, account, children, title }: Props) {
  const [state, setState] = useState<CheckState>({ kind: "loading" });
  const [showInline, setShowInline] = useState(false);

  const check = useCallback(async () => {
    try {
      let target = account;
      if (!target) {
        const accs: GogAccount[] = await api.gogAccounts();
        if (accs.length === 0) { setState({ kind: "no_accounts" }); return; }
        target = accs[0].email;
      }
      const r = await api.gogCheckScopes({ account: target, services: requires });
      if (r.satisfied) setState({ kind: "ok", account: target });
      else setState({ kind: "missing", account: target, missing: r.missing });
    } catch (e) {
      setState({ kind: "error", message: String(e) });
    }
  }, [account, requires]);

  useEffect(() => { check(); }, [check]);

  // Poll cada 30s — barato y nos cubre el caso "el usuario completó auth en otra pestaña"
  useEffect(() => {
    const id = window.setInterval(check, 30000);
    return () => window.clearInterval(id);
  }, [check]);

  if (state.kind === "loading") {
    return (
      <Surface level={2} className="p-4 bg-bg/40">
        <p className="text-sm text-text-dim italic">Verificando permisos…</p>
      </Surface>
    );
  }

  if (state.kind === "ok") {
    return <>{children}</>;
  }

  if (state.kind === "error") {
    return (
      <Surface level={2} className="p-4 border border-danger/30 bg-danger/10">
        <div className="flex items-start gap-2 text-sm text-danger">
          <Icon name="alert" size={14} className="mt-0.5 shrink-0" />
          <span>No se pudo verificar permisos: {state.message}</span>
        </div>
      </Surface>
    );
  }

  // ── No accounts O scopes faltantes → banner CTA ──────────────────
  const needsAccount = state.kind === "no_accounts";
  const headline = title || "Esta feature requiere permisos de Google";
  const subtext = needsAccount
    ? "No tenés ninguna cuenta Google conectada todavía."
    : `Faltan permisos para: ${(state as { missing: string[] }).missing.join(", ")}.`;

  if (showInline) {
    return (
      <div className="flex flex-col gap-3">
        <button onClick={() => setShowInline(false)}
                className="text-[11px] uppercase tracking-[0.18em] text-text-dim
                           hover:text-text self-start">
          ← Volver
        </button>
        <GogAccountsCard defaultServices={requires} />
      </div>
    );
  }

  return (
    <Surface level={2} className="p-4 border border-amber-400/30 bg-amber-400/[0.06]">
      <div className="flex items-start gap-3">
        <span className="grid place-items-center h-9 w-9 rounded-lg
                         bg-amber-400/15 border border-amber-400/40
                         text-amber-300 shrink-0">
          <Icon name="shield" size={16} />
        </span>
        <div className="flex-1 min-w-0">
          <h4 className="text-[15px] font-medium leading-tight">{headline}</h4>
          <p className="text-[12px] text-text-dim mt-0.5">{subtext}</p>
        </div>
        <Button variant="primary" size="sm" icon="shield" onClick={() => setShowInline(true)}>
          {needsAccount ? "Conectar Google" : "Autorizar"}
        </Button>
      </div>
    </Surface>
  );
}
