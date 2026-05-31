"""
run_debug.py — Lanza ORION capturando TODOS los errores a logs/debug.log
=======================================================================
Si ORION se cierra al instante, ejecuta este script en su lugar:

    python run_debug.py

Luego revisa logs/debug.log para ver el traceback completo.
"""

from __future__ import annotations

import faulthandler
import sys
import traceback
from pathlib import Path

# Asegurar que estamos en el directorio del proyecto
HERE = Path(__file__).resolve().parent
LOG_DIR = HERE / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / "debug.log"


def main() -> None:
    # Tee de stdout/stderr al archivo de log
    log_file = open(LOG_PATH, "w", encoding="utf-8", buffering=1)
    faulthandler.enable(log_file)

    class _Tee:
        def __init__(self, *streams):
            self._streams = streams
        def write(self, s):
            for st in self._streams:
                try:
                    st.write(s)
                except Exception:
                    pass
        def flush(self):
            for st in self._streams:
                try:
                    st.flush()
                except Exception:
                    pass

    sys.stdout = _Tee(sys.__stdout__, log_file)
    sys.stderr = _Tee(sys.__stderr__, log_file)

    print(f"=== ORION DEBUG LAUNCHER ===")
    print(f"Log: {LOG_PATH}")
    print(f"Python: {sys.version}")
    print(f"Working dir: {HERE}")
    print(f"=" * 30)

    try:
        # Hook de excepciones no manejadas
        def _on_unhandled(exctype, value, tb):
            print("\n!!! EXCEPCIÓN NO MANEJADA !!!", file=sys.stderr)
            traceback.print_exception(exctype, value, tb, file=sys.stderr)
        sys.excepthook = _on_unhandled

        # Hook para excepciones en hilos
        import threading
        def _on_thread_unhandled(args):
            print(f"\n!!! EXCEPCIÓN EN THREAD {args.thread.name} !!!", file=sys.stderr)
            traceback.print_exception(
                args.exc_type, args.exc_value, args.exc_traceback,
                file=sys.stderr,
            )
        threading.excepthook = _on_thread_unhandled

        # Ejecutar main.main()
        from main import main as orion_main
        orion_main()

    except SystemExit:
        print("\n[run_debug] sys.exit() llamado.")
    except KeyboardInterrupt:
        print("\n[run_debug] Interrumpido por el usuario.")
    except BaseException:
        print("\n!!! ERROR FATAL al arrancar ORION !!!", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
    finally:
        print("\n=== Fin de la ejecución ===")
        log_file.flush()
        log_file.close()
        # Pausa para que el usuario lea si está en doble-click
        try:
            input("\nPresiona Enter para cerrar...")
        except EOFError:
            pass


if __name__ == "__main__":
    main()
