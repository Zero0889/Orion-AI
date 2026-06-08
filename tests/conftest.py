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
