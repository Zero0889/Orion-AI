"""CLI auxiliar de Orion.

Hoy solo provee ``orion.cli.debug`` — wrapper que arranca la app
capturando stdout/stderr + faulthandler a ``logs/debug.log``. Útil
cuando Orion se cae al instante y no podés ver el traceback.

Uso:
    python -m orion.cli.debug
"""
