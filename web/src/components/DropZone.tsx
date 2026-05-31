/**
 * DropZone — overlay global de drag-and-drop.
 *
 * Se monta una sola vez en App. Captura ``dragenter`` a nivel de window
 * y muestra un overlay translúcido sobre toda la ventana mientras el
 * usuario arrastra. Al soltar, sube el primer archivo via
 * ``POST /api/files/upload``. El backend setea ``bus.current_file`` y
 * emite ``file.attached``, así que el chip del chat aparece solo.
 *
 * Solo aceptamos un archivo a la vez (paridad con el comportamiento
 * actual de ``ui.FileDropZone`` en PyQt).
 */

import { useEffect, useState } from "react";

import { api } from "@/api/rest";

export function DropZone() {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Contador de dragenter/dragleave porque cada hijo dispara su
    // propio evento al pasar el cursor por encima.
    let depth = 0;

    const onEnter = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth++;
      setDragging(true);
    };
    const onOver = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
    };
    const onLeave = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth = Math.max(0, depth - 1);
      if (depth === 0) setDragging(false);
    };
    const onDrop = async (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth = 0;
      setDragging(false);
      const f = e.dataTransfer?.files?.[0];
      if (!f) return;
      try {
        setUploading(true);
        setError(null);
        await api.uploadFile(f);
        // Éxito: el evento WS file.attached actualiza el store.
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
    <div className="fixed inset-0 z-40 grid place-items-center bg-pri/10 backdrop-blur-sm pointer-events-none">
      <div className="rounded-xl border-2 border-dashed border-pri bg-bg/90 px-10 py-8 text-center max-w-md">
        {uploading ? (
          <>
            <div className="text-2xl text-pri mb-2">↑</div>
            <p className="text-sm">Subiendo archivo…</p>
          </>
        ) : error ? (
          <>
            <div className="text-2xl text-pri mb-2">!</div>
            <p className="text-sm">{error}</p>
            <button
              onClick={() => setError(null)}
              className="mt-3 text-xs underline text-text-dim pointer-events-auto"
            >Cerrar</button>
          </>
        ) : (
          <>
            <div className="text-3xl text-pri mb-2">↓</div>
            <p className="text-sm">Suelta el archivo aquí</p>
            <p className="text-[10px] text-text-dim mt-1">
              Se subirá a Orion como archivo activo (máx 50 MB)
            </p>
          </>
        )}
      </div>
    </div>
  );
}

function hasFiles(e: DragEvent): boolean {
  const types = e.dataTransfer?.types;
  if (!types) return false;
  for (let i = 0; i < types.length; i++) {
    if (types[i] === "Files") return true;
  }
  return false;
}
