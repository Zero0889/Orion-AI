"""orion.__main__ — Entry point para ``python -m orion``.

Wrapper thin sobre ``orion.bootstrap.main``. La lógica real se splitea
en (post Fase 3):

  - :mod:`orion.bootstrap` — setup del proceso + main loop.
  - :mod:`orion.runtime` — clase :class:`~orion.runtime.OrionLive`.
  - :mod:`orion.audio` — mixin de I/O de audio.
  - :mod:`orion.live_session` — mixin de config Gemini + watchdog.
  - :mod:`orion._helpers` — utilities puras compartidas.

Re-exportamos ``main`` para que ``import orion.__main__ as m; m.main`` siga
funcionando (lo usan algunos tests en ``tests/test_ui_mode.py``).
"""

from __future__ import annotations

from orion.bootstrap import main

__all__ = ["main"]


if __name__ == "__main__":
    main()
