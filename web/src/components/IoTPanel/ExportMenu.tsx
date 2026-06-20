/**
 * ExportMenu — dropdown chico que ofrece descargas del histórico de sensores.
 *
 * CSV (tabla cruda) y XLSX (una hoja por sensor). Usa <a download> directo
 * para que el browser dispare la descarga en streaming desde el endpoint
 * — sin pasar por blobs en memoria.
 *
 * Click-outside cierra el menú (listener mounted solo cuando está abierto
 * para no acumular handlers).
 */

import { useEffect, useState } from "react";

import { Icon } from "@/ui/Icon";
import { Button } from "@/ui/primitives";

export function ExportMenu() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    function close(e: MouseEvent) {
      const t = e.target as HTMLElement;
      if (!t.closest("[data-export-menu]")) setOpen(false);
    }
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, [open]);

  return (
    <div className="relative" data-export-menu>
      <Button
        variant="ghost"
        size="sm"
        icon="download"
        onClick={() => setOpen((o) => !o)}
        title="Descargar histórico de sensores"
      >
        Exportar
      </Button>
      {open && (
        <div
          className="absolute right-0 top-full mt-1.5 z-30 min-w-[200px]
                     rounded-lg border border-white/[0.08] bg-elevated/95
                     backdrop-blur-md shadow-xl p-1.5 animate-fade-in"
        >
          <a
            href="/api/iot/sensor_log/xlsx"
            download
            onClick={() => setOpen(false)}
            className="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm text-text
                       hover:bg-white/[0.06] transition-colors"
          >
            <Icon name="chart" size={14} className="text-acc" />
            <div className="flex-1">
              <div className="leading-tight">Excel (.xlsx)</div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-muted">
                una hoja por sensor
              </div>
            </div>
          </a>
          <a
            href="/api/iot/sensor_log/csv"
            download
            onClick={() => setOpen(false)}
            className="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm text-text
                       hover:bg-white/[0.06] transition-colors"
          >
            <Icon name="download" size={14} className="text-text-dim" />
            <div className="flex-1">
              <div className="leading-tight">CSV (.csv)</div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-muted">tabla cruda</div>
            </div>
          </a>
        </div>
      )}
    </div>
  );
}
