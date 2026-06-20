/**
 * AttachmentChip — visible above the chat composer when a file is
 * currently attached to the bus. Click × to clear; click "Adjuntar" to
 * open the native file picker (mirrors the drop-zone upload).
 */

import { useRef, useState } from "react";

import { api } from "@/api/rest";
import { useOrionStore } from "@/stores/orion";
import { Icon } from "@/ui/Icon";

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
    try {
      await api.clearCurrentFile();
    } catch (e) {
      console.error(e);
    }
  }

  return (
    <div className="inline-flex items-center gap-2 text-xs">
      <input ref={inputRef} type="file" className="hidden" onChange={pickFile} />

      {currentFile ? (
        <div
          className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full
                        border border-acc/30 bg-acc/10 text-acc max-w-xs animate-fade-in"
        >
          <Icon name="paperclip" size={12} />
          <span className="truncate" title={currentFile}>
            {fileLabel(currentFile)}
          </span>
          <button
            onClick={clear}
            title="Quitar adjunto"
            className="h-4 w-4 grid place-items-center rounded-full text-acc/70
                       hover:text-acc hover:bg-acc/20 transition-colors"
          >
            <Icon name="close" size={11} />
          </button>
        </div>
      ) : (
        <button
          onClick={() => inputRef.current?.click()}
          disabled={busy}
          title="Adjuntar archivo o arrastra uno a la ventana"
          className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md
                     border border-white/[0.06] bg-elevated/60 text-text-dim
                     hover:text-text hover:border-white/[0.14] hover:bg-elevated
                     transition-all duration-150 disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <Icon name="paperclip" size={13} />
          <span className="text-[11px]">{busy ? "Subiendo…" : "Adjuntar"}</span>
        </button>
      )}
    </div>
  );
}

function fileLabel(path: string): string {
  const base = path.split(/[\\/]/).pop() ?? path;
  const m = base.match(/^\d{10,}_(.+)$/);
  return m ? m[1] : base;
}
