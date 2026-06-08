/**
 * DropZone — glassy overlay for drag-and-drop file upload.
 *
 * Listens at window level (counter to handle child events). On drop,
 * uploads the first file via POST /api/files/upload. The backend then
 * emits `file.attached`, so the chat chip appears automatically.
 */

import { useEffect, useState } from "react";

import { api } from "@/api/rest";
import { Icon } from "@/ui/Icon";

export function DropZone() {
  const [dragging,  setDragging]  = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error,     setError]     = useState<string | null>(null);

  useEffect(() => {
    let depth = 0;
    const onEnter = (e: DragEvent) => {
      if (!hasFiles(e)) return; e.preventDefault();
      depth++; setDragging(true);
    };
    const onOver  = (e: DragEvent) => { if (hasFiles(e)) e.preventDefault(); };
    const onLeave = (e: DragEvent) => {
      if (!hasFiles(e)) return; e.preventDefault();
      depth = Math.max(0, depth - 1);
      if (depth === 0) setDragging(false);
    };
    const onDrop = async (e: DragEvent) => {
      if (!hasFiles(e)) return; e.preventDefault();
      depth = 0; setDragging(false);
      const f = e.dataTransfer?.files?.[0];
      if (!f) return;
      try {
        setUploading(true); setError(null);
        await api.uploadFile(f);
      } catch (err) {
        setError(String(err));
      } finally {
        setUploading(false);
      }
    };

    window.addEventListener("dragenter", onEnter);
    window.addEventListener("dragover",  onOver);
    window.addEventListener("dragleave", onLeave);
    window.addEventListener("drop",      onDrop);
    return () => {
      window.removeEventListener("dragenter", onEnter);
      window.removeEventListener("dragover",  onOver);
      window.removeEventListener("dragleave", onLeave);
      window.removeEventListener("drop",      onDrop);
    };
  }, []);

  if (!dragging && !uploading && !error) return null;

  return (
    <div className="fixed inset-0 z-40 grid place-items-center bg-bg/55 backdrop-blur-md
                    pointer-events-none animate-fade-in">
      {/* ambient halo */}
      <div className="absolute h-[420px] w-[420px] rounded-full bg-pri/12 blur-3xl animate-halo" />

      <div className="relative max-w-md w-[88%] rounded-2xl border border-dashed
                      border-pri/55 surface-glass px-10 py-9 text-center shadow-lift
                      animate-scale-in">
        {uploading ? (
          <>
            <Spinner />
            <p className="mt-4 text-sm text-text">Subiendo archivo…</p>
          </>
        ) : error ? (
          <>
            <div className="mx-auto h-12 w-12 rounded-2xl bg-danger/15 grid place-items-center">
              <Icon name="alert" size={22} className="text-danger" />
            </div>
            <p className="mt-4 text-sm text-text">{error}</p>
            <button
              onClick={() => setError(null)}
              className="mt-4 text-xs underline text-text-dim pointer-events-auto hover:text-text"
            >Cerrar</button>
          </>
        ) : (
          <>
            <div className="mx-auto h-14 w-14 rounded-2xl bg-pri/15 grid place-items-center shadow-glow-soft">
              <Icon name="upload" size={26} className="text-pri" />
            </div>
            <p className="mt-4 text-base font-medium text-text">Suelta el archivo aquí</p>
            <p className="mt-1 text-xs text-text-dim">
              Se subirá a Orion como archivo activo · máx 50 MB
            </p>
          </>
        )}
      </div>
    </div>
  );
}

function Spinner() {
  return (
    <div className="relative mx-auto h-12 w-12">
      <div className="absolute inset-0 rounded-full border-2 border-white/[0.08]" />
      <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-pri animate-spin-fast" />
    </div>
  );
}

function hasFiles(e: DragEvent): boolean {
  const types = e.dataTransfer?.types;
  if (!types) return false;
  for (let i = 0; i < types.length; i++) if (types[i] === "Files") return true;
  return false;
}
