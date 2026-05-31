/**
 * AttachmentChip — chip que muestra el archivo actualmente adjunto.
 *
 * Aparece encima del input del ChatPanel cuando ``currentFile`` no es
 * null. Click en × → DELETE /api/files/current (limpia el bus).
 * También expone un botón "Examinar…" que abre el file picker nativo y
 * llama al mismo endpoint de upload que el drop-zone global.
 */

import { useRef, useState } from "react";

import { api } from "@/api/rest";
import { useOrionStore } from "@/stores/orion";

export function AttachmentChip() {
  const currentFile = useOrionStore((s) => s.currentFile);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [busy, setBusy] = useState(false);

  async function pickFile(ev: React.ChangeEvent<HTMLInputElement>) {
    const f = ev.target.files?.[0];
    if (!f) return;
    try {
      setBusy(true);
      await api.uploadFile(f);
    } catch (e) {
      console.error(e);
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function clear() {
    try { await api.clearCurrentFile(); }
    catch (e) { console.error(e); }
  }

  return (
    <div className="flex items-center gap-2 text-xs">
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        onChange={pickFile}
      />
      {currentFile ? (
        <div className="flex items-center gap-2 px-2.5 py-1 rounded-full border border-acc bg-acc/10 text-acc max-w-[60%]">
          <span className="shrink-0">📎</span>
          <span className="truncate" title={currentFile}>
            {fileLabel(currentFile)}
          </span>
          <button
            onClick={clear}
            className="text-acc/70 hover:text-pri shrink-0"
            title="Quitar adjunto"
          >×</button>
        </div>
      ) : (
        <button
          onClick={() => inputRef.current?.click()}
          disabled={busy}
          className="px-2.5 py-1 rounded-md border border-border-b text-text-dim
                     hover:border-pri hover:text-pri transition disabled:opacity-30"
          title="Adjuntar archivo o arrastra uno a la ventana"
        >
          {busy ? "Subiendo…" : "📎 Adjuntar"}
        </button>
      )}
    </div>
  );
}

function fileLabel(path: string): string {
  const base = path.split(/[\\\/]/).pop() ?? path;
  // Quitar el prefijo timestamp_ que añade el backend.
  const m = base.match(/^\d{10,}_(.+)$/);
  return m ? m[1] : base;
}
