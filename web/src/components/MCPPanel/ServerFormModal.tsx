/**
 * ServerFormModal — modal de creación/edición de un server MCP.
 *
 * Tres modos:
 * - **Crear a mano**: id + comando + args + env desde cero.
 * - **Editar existente**: pre-rellenado desde `initial`.
 * - **Instalar desde registry**: pre-rellenado desde `prefill` (que
 *   viene de la pestaña Explorar). Muestra hint con las env vars
 *   obligatorias del package.
 */

import { useEffect, useState } from "react";

import { api, type MCPServerBody, type MCPServerStatus } from "@/api/rest";
import { Icon } from "@/ui/Icon";
import { Button, Field, Modal, Switch, TextInput } from "@/ui/primitives";

import type { PrefillFromRegistry } from "./types";

interface Props {
  open: boolean;
  initial?: MCPServerStatus;
  prefill?: PrefillFromRegistry;
  onClose: () => void;
  onSaved: () => void;
  onError: (msg: string) => void;
}

export function ServerFormModal({ open, initial, prefill, onClose, onSaved, onError }: Props) {
  const isEdit = !!initial;
  const isFromRegistry = !isEdit && !!prefill;

  const [id, setId] = useState("");
  const [command, setCommand] = useState("");
  const [argsText, setArgsText] = useState("");
  const [envText, setEnvText] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [cwd, setCwd] = useState("");
  const [busy, setBusy] = useState(false);

  // Helper para serializar un dict de env vars al textarea
  function envToText(env: Record<string, string> | undefined): string {
    if (!env) return "";
    return Object.entries(env)
      .map(([k, v]) => `${k}=${v}`)
      .join("\n");
  }

  function quoteArg(a: string): string {
    return /\s/.test(a) ? `"${a}"` : a;
  }

  useEffect(() => {
    if (!open) return;
    if (initial) {
      // Modo edición
      setId(initial.id);
      setCommand(initial.command);
      setArgsText(initial.args.map(quoteArg).join(" "));
      setEnvText(envToText(initial.env));
      setEnabled(initial.enabled);
      setCwd(initial.cwd ?? "");
    } else if (prefill) {
      // Modo instalación desde registry
      setId(prefill.suggestedId);
      setCommand(prefill.body.command);
      setArgsText((prefill.body.args ?? []).map(quoteArg).join(" "));
      setEnvText(envToText(prefill.body.env));
      setEnabled(prefill.body.enabled ?? true);
      setCwd(prefill.body.cwd ?? "");
    } else {
      // Modo creación a mano: en blanco
      setId("");
      setCommand("");
      setArgsText("");
      setEnvText("");
      setEnabled(true);
      setCwd("");
    }
  }, [open, initial, prefill]);

  function parseArgs(s: string): string[] {
    // Tokenización simple por whitespace, respeta "quoted strings"
    const out: string[] = [];
    const re = /"([^"]*)"|'([^']*)'|(\S+)/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(s)) !== null) {
      out.push(m[1] ?? m[2] ?? m[3]);
    }
    return out;
  }

  function parseEnv(s: string): Record<string, string> {
    const out: Record<string, string> = {};
    for (const raw of s.split(/\r?\n/)) {
      const line = raw.trim();
      if (!line || line.startsWith("#")) continue;
      const eq = line.indexOf("=");
      if (eq < 0) continue;
      out[line.slice(0, eq).trim()] = line.slice(eq + 1).trim();
    }
    return out;
  }

  async function save() {
    if (!command.trim()) {
      onError("El comando es obligatorio");
      return;
    }
    if (!isEdit && !id.trim()) {
      onError("El id es obligatorio");
      return;
    }

    const body: MCPServerBody = {
      command: command.trim(),
      args: parseArgs(argsText),
      env: parseEnv(envText),
      enabled,
      cwd: cwd.trim() || undefined,
    };

    setBusy(true);
    try {
      if (isEdit) {
        await api.mcpUpdateServer(initial!.id, body);
      } else {
        await api.mcpCreateServer({ id: id.trim(), ...body });
      }
      onSaved();
    } catch (e) {
      onError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      eyebrow={isFromRegistry ? "Instalar desde registry" : "MCP"}
      title={
        isEdit
          ? `Editar server '${initial!.id}'`
          : isFromRegistry
            ? "Instalar servidor MCP"
            : "Nuevo servidor MCP"
      }
    >
      <div className="flex flex-col gap-3">
        {isFromRegistry && prefill && (
          <div
            className="flex items-start gap-2 p-3 rounded-md
                          border border-pri/30 bg-pri/[0.06] text-xs text-text-dim"
          >
            <Icon name="info" size={14} className="mt-0.5 shrink-0 text-pri" />
            <div className="space-y-1">
              <div>
                Pre-rellenado con la receta del registry oficial. Revisá el id, ajustá las variables
                de entorno y confirmá.
              </div>
              {prefill.envRequired.some((e) => e.required) && (
                <div>
                  Variables <span className="text-warn">obligatorias</span>:{" "}
                  <span className="font-mono text-text">
                    {prefill.envRequired
                      .filter((e) => e.required)
                      .map((e) => e.name)
                      .join(", ")}
                  </span>
                </div>
              )}
            </div>
          </div>
        )}

        {!isEdit && (
          <Field
            label="ID"
            hint="Letras, dígitos, '-' y '_'. Prefija las tools (ej. fs__read_file)."
          >
            <TextInput
              value={id}
              onChange={(e) => setId(e.target.value)}
              placeholder="fs"
              autoFocus
            />
          </Field>
        )}

        <Field label="Comando" hint="Binario que se ejecuta (resuelve PATH automáticamente).">
          <TextInput
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            placeholder="npx"
          />
        </Field>

        <Field
          label="Argumentos"
          hint="Separados por espacio. Usá comillas para preservar espacios."
        >
          <TextInput
            value={argsText}
            onChange={(e) => setArgsText(e.target.value)}
            placeholder='-y @modelcontextprotocol/server-filesystem "C:/Users/zahir"'
          />
        </Field>

        <Field
          label="Variables de entorno"
          hint="Una por línea, formato KEY=valor. Líneas vacías o que empiezan con # se ignoran."
        >
          <textarea
            value={envText}
            onChange={(e) => setEnvText(e.target.value)}
            placeholder="GITHUB_TOKEN=ghp_..."
            rows={3}
            className="w-full px-3 py-2 rounded-md font-mono text-xs
                       bg-elevated/40 border border-white/[0.06]
                       text-text placeholder:text-muted
                       focus:outline-none focus:border-pri/40
                       focus:ring-1 focus:ring-pri/20"
          />
        </Field>

        <Field label="Working directory (opcional)">
          <TextInput
            value={cwd}
            onChange={(e) => setCwd(e.target.value)}
            placeholder="(default: cwd de ORION)"
          />
        </Field>

        <div
          className="flex items-center justify-between px-1 py-2 mt-1
                        border-t border-white/[0.05]"
        >
          <div>
            <div className="text-xs font-medium text-text">Habilitado</div>
            <div className="text-[11px] text-text-dim">
              Si está apagado, el server queda guardado pero no se arranca.
            </div>
          </div>
          <Switch on={enabled} onClick={() => setEnabled((v) => !v)} />
        </div>

        <div
          className="flex items-center justify-end gap-2 pt-3 mt-1
                        border-t border-white/[0.05]"
        >
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancelar
          </Button>
          <Button variant="primary" onClick={save} disabled={busy}>
            {busy ? "Guardando…" : isEdit ? "Guardar" : "Crear"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
