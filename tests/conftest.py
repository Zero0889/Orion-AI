"""
tests.conftest — fixtures globales para la suite
================================================
Razón de existir: ``server.sharing.SharingMiddleware`` rechaza con 403
cualquier request cuyo ``scope["client"]`` no caiga en 127.0.0.0/8
(loopback) o en el rango Tailscale 100.64.0.0/10.

``starlette.testclient.TestClient`` por defecto setea
``scope["client"] = ("testclient", 50000)``. La cadena ``"testclient"``
no es una IP válida → el middleware no puede clasificarla → 403.

Resultado antes de esta fixture: 61 tests HTTP en rojo aun cuando el
endpoint funciona.

Fix: aquí monkeypatcheamos el ``TestClient`` para que use
``("127.0.0.1", 50000)`` como cliente por defecto. Loopback siempre está
permitido, así que el middleware deja pasar la request al endpoint y los
tests pueden verificar la lógica de negocio real.

Esto NO toca el código de producción — solo cómo los tests se conectan
a la app. En runtime real, el cliente lo pone uvicorn a partir del
socket TCP, así que esto no afecta nada fuera de pytest.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# ── Mock sounddevice antes de cualquier import de main/actions ──────────
# main.py importa `sounddevice` (audio I/O nativo). En CI Linux la
# librería del sistema (PortAudio) no está instalada y el import crashea
# con ModuleNotFoundError — rompe test_ui_mode que importa `main`.
# Mock vacío: los tests no ejercen audio real.
sys.modules.setdefault("sounddevice", MagicMock())

# ── Permitir tmpdir como SAFE_ROOT durante tests ────────────────────────
# `actions.file_controller._SAFE_ROOTS` se computa al import como
# [Path.home(), $OneDrive]. En Windows el tmpdir cae bajo
# C:\Users\<user>\AppData\Local\Temp → relativo a home → pasa. En Linux
# el tmpdir es /tmp/ → NO está bajo /home/runner → rechaza con "Acceso
# denegado". Los ~40 tests de file_controller usan `tmp_path` y fallan
# por esto. Solución: extender _SAFE_ROOTS con gettempdir() para tests.
# Esto NO toca la prod — solo el módulo cargado en este proceso pytest.
try:
    from orion.actions import file_controller as _fc

    _fc._SAFE_ROOTS = [*_fc._SAFE_ROOTS, Path(tempfile.gettempdir()).resolve()]
except Exception:
    # Si el módulo no se puede importar acá, los tests fallarán igual con
    # un error más claro — no enmascaramos.
    pass

import pytest
from starlette.testclient import TestClient as _StarletteTestClient

_original_init = _StarletteTestClient.__init__


def _patched_init(self, app, *args, **kwargs):
    # Solo seteamos client si el caller no lo especificó. Así un test que
    # quiera probar el middleware con una IP distinta puede hacerlo.
    kwargs.setdefault("client", ("127.0.0.1", 50000))
    return _original_init(self, app, *args, **kwargs)


@pytest.fixture(autouse=True)
def _testclient_uses_loopback(monkeypatch):
    """Autouse — se aplica a TODOS los tests sin que tengan que pedirlo.

    Tests que no usan TestClient simplemente no notan nada.
    """
    monkeypatch.setattr(_StarletteTestClient, "__init__", _patched_init)
    yield


@pytest.fixture(autouse=True)
def _isolated_sqlite_db(tmp_path, monkeypatch):
    """Autouse — apunta el SQLite singleton a un archivo dentro de
    ``tmp_path`` y resetea TODOS los stores que cachean instancias.

    Sin esta fixture, el primer test que importe un store migraría el
    JSON real del usuario al ``data/orion.sqlite`` real. Acá garantizamos
    que cada test parte de un DB vacío en tmp y no toca producción.
    """
    from orion.storage import override_db_path_for_tests

    db_path = tmp_path / "orion_test.sqlite"
    override_db_path_for_tests(db_path)

    # Por cada store: apuntar el legacy json a algo que NO existe (no
    # importar data real) + resetear el flag de inicialización para que
    # el próximo `_init_if_needed()` arme schema contra el nuevo DB.
    _reset_helpers = []
    try:
        from orion.actions.notifications import store as _notif_store

        monkeypatch.setattr(_notif_store, "_LEGACY_JSON_PATH", tmp_path / "no_notif.json")
        _notif_store._reset_for_tests()
        _reset_helpers.append(_notif_store._reset_for_tests)
    except ImportError:
        pass

    try:
        from orion.domain.memory import quick_notes as _qn

        monkeypatch.setattr(_qn, "_NOTES_PATH", tmp_path / "no_qn.json")
        _qn._reset_for_tests()
        _reset_helpers.append(_qn._reset_for_tests)
    except ImportError:
        pass

    try:
        from orion.domain.memory import conversations as _cv

        monkeypatch.setattr(_cv, "_CONVERSATIONS_PATH", tmp_path / "no_conv.json")
        _cv._reset_for_tests()
        _reset_helpers.append(_cv._reset_for_tests)
    except ImportError:
        pass

    try:
        from orion.domain.memory import memory_manager as _mm

        # memory_manager mira MEMORY_PATH del config — lo apuntamos a tmp.
        monkeypatch.setattr(_mm, "MEMORY_PATH", tmp_path / "no_long_term.json")
        _mm._reset_for_tests()
        _reset_helpers.append(_mm._reset_for_tests)
    except ImportError:
        pass

    yield db_path

    # Cleanup: limpia singletons para que el próximo test arranque limpio.
    for reset in _reset_helpers:
        reset()
