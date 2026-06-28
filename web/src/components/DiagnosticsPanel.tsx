/**
 * DiagnosticsPanel — para que un usuario no-dev pueda ver:
 *   - donde estan sus archivos de config / data / logs
 *   - el tail del log activo con highlight de WARN/ERROR
 *   - info del runtime (Python, OS, versiones)
 *
 * Reemplaza el "tengo que abrir el CMD" — si algo no funciona, el
 * usuario abre este panel, copia el log, y ya tiene todo lo que necesita
 * para reportar el problema.
 */

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { api, type LogTailResult } from "@/api/rest";
import { toast } from "@/stores/toast";
import { Icon } from "@/ui/Icon";
import { Button, SectionHeader, Surface } from "@/ui/primitives";

const TAIL_LINES_OPTIONS = [100, 200, 500, 1000] as const;

export function DiagnosticsPanel() {
  const [tailLines, setTailLines] = useState<number>(200);

  const { data: info, error: infoError } = useQuery({
    queryKey: ["diagnostics", "info"],
    queryFn: () => api.diagnosticsInfo(),
    staleTime: 60_000,
  });

  const {
    data: logTail,
    isFetching: tailFetching,
    error: tailError,
    refetch: refetchTail,
  } = useQuery<LogTailResult>({
    queryKey: ["diagnostics", "log", tailLines],
    queryFn: () => api.diagnosticsLogTail(tailLines),
    refetchInterval: 5000, // tail vivo cada 5s
  });

  async function copyLogToClipboard() {
    if (!logTail?.lines.length) return;
    try {
      await navigator.clipboard.writeText(logTail.lines.join("\n"));
      toast.success("Log copiado al portapapeles");
    } catch {
      toast.error("No pude copiar al portapapeles");
    }
  }

  async function openLogFolder() {
    try {
      await api.diagnosticsOpenLogFolder();
    } catch (e) {
      toast.error(`No pude abrir la carpeta: ${e}`);
    }
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <SectionHeader
        eyebrow="Sistema"
        title="Diagnóstico"
        hint="Logs, rutas y info del runtime. Útil para reportar problemas."
        action={
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              icon="memory"
              onClick={() => refetchTail()}
              disabled={tailFetching}
            >
              Refrescar
            </Button>
            <Button variant="ghost" size="sm" icon="paperclip" onClick={copyLogToClipboard}>
              Copiar log
            </Button>
            <Button variant="primary" size="sm" icon="upload" onClick={openLogFolder}>
              Abrir carpeta
            </Button>
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto scrollbar-thin px-6 py-4 space-y-4">
        {infoError && (
          <Surface
            level={2}
            className="p-3 flex items-start gap-2 border border-danger/30 bg-danger/10 text-xs text-danger"
          >
            <Icon name="alert" size={14} className="mt-0.5 shrink-0" />
            <span>No pude leer la info del runtime: {String(infoError)}</span>
          </Surface>
        )}

        {info && <InfoGrid info={info} />}

        <Surface level={2} className="p-0 overflow-hidden">
          <div
            className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2
                       px-3 py-2 border-b border-white/[0.06]"
          >
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-[10px] uppercase tracking-[0.18em] text-text-dim shrink-0">
                Log activo
              </span>
              {logTail?.path && (
                <code className="text-[10px] text-muted truncate" title={logTail.path}>
                  {logTail.path}
                </code>
              )}
            </div>
            <div className="flex items-center gap-1 flex-wrap shrink-0">
              {TAIL_LINES_OPTIONS.map((n) => (
                <button
                  key={n}
                  onClick={() => setTailLines(n)}
                  className={[
                    "px-2 h-6 text-[10px] uppercase tracking-[0.14em] rounded-md transition-colors",
                    tailLines === n
                      ? "bg-pri/15 text-pri"
                      : "text-text-dim hover:text-text hover:bg-white/[0.04]",
                  ].join(" ")}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>

          {tailError && (
            <p className="px-3 py-3 text-xs text-danger">
              No pude leer el log: {String(tailError)}
            </p>
          )}

          {logTail && !logTail.exists && (
            <p className="px-3 py-3 text-xs text-text-dim">
              El archivo no existe todavía. Va a aparecer en el primer evento que loggee Orion.
            </p>
          )}

          {logTail?.exists && logTail.lines.length === 0 && (
            <p className="px-3 py-3 text-xs text-text-dim">El archivo está vacío.</p>
          )}

          {logTail?.exists && logTail.lines.length > 0 && <LogViewer lines={logTail.lines} />}
        </Surface>
      </div>
    </div>
  );
}

// ── Info grid ─────────────────────────────────────────────────────────────

function InfoGrid({ info }: { info: NonNullable<ReturnType<typeof useQuery>["data"]> & object }) {
  // Caller ya pasa un DiagnosticsInfo; el cast del tipo lo manejamos
  // arriba — aca solo renderizamos.
  const rows: Array<[string, string, string?]> = useMemo(() => {
    const d = info as unknown as {
      base_dir: string;
      resources_dir: string;
      config_dir: string;
      data_dir: string;
      api_keys_path: string;
      log_path: string;
      log_dir: string;
      python_version: string;
      platform: string;
      frozen: boolean;
      sys_executable: string;
    };
    return [
      ["Modo", d.frozen ? "Empaquetado (.exe)" : "Desarrollo (dev)", "El modo prod usa APPDATA."],
      ["Plataforma", d.platform],
      ["Python", d.python_version],
      ["Base dir", d.base_dir, "Donde se guarda config + data del usuario."],
      ["Config", d.config_dir],
      ["Data", d.data_dir],
      ["API key", d.api_keys_path, "Edita acá si querés cambiar la key sin re-abrir el wizard."],
      ["Log activo", d.log_path],
      ["Carpeta de logs", d.log_dir, "Rota cada 5MB, conserva 3 archivos."],
      ["Ejecutable Python", d.sys_executable],
    ];
  }, [info]);

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
      {rows.map(([label, value, hint]) => (
        <Surface key={label} level={2} className="p-3">
          <div className="text-[10px] uppercase tracking-[0.18em] text-text-dim mb-1">{label}</div>
          <div className="text-[12px] font-mono text-text break-all">{value}</div>
          {hint && <div className="text-[10px] text-muted mt-1 leading-relaxed">{hint}</div>}
        </Surface>
      ))}
    </div>
  );
}

// ── Log viewer ────────────────────────────────────────────────────────────

function LogViewer({ lines }: { lines: string[] }) {
  return (
    <div className="font-mono text-[11px] leading-snug max-h-[480px] overflow-y-auto scrollbar-thin">
      {lines.map((line, i) => (
        <LogLine key={i} line={line} />
      ))}
    </div>
  );
}

function LogLine({ line }: { line: string }) {
  const tone = useMemo(() => {
    const low = line.toLowerCase();
    if (low.includes("error") || low.includes("traceback")) return "text-danger";
    if (low.includes("warning") || low.includes("warn")) return "text-warn";
    if (low.includes("info")) return "text-text-dim";
    return "text-text-dim/70";
  }, [line]);
  return (
    <div className={`px-3 py-0.5 border-b border-white/[0.02] ${tone} hover:bg-white/[0.02]`}>
      {line || " "}
    </div>
  );
}
