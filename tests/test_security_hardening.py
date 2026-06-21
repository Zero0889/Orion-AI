"""
Tests de regresión para los guards de seguridad de Fase 1.

Si alguno de estos tests falla, alguien re-introdujo un agujero crítico:
  - desktop.py volvió a tener exec()/codegen path
  - open_app.py vuelve a usar shell=True con input del LLM
  - el sanitizador de app_name dejó pasar metacaracteres

Estos tests NO ejecutan los binarios — solo validan que la lógica de
defensa esté en su lugar.
"""

from __future__ import annotations

import inspect

import pytest


# ── desktop.py: no debe quedar codegen+exec ─────────────────────────────


def test_desktop_no_codegen_helpers():
    """Las funciones de codegen y ejecución deben haber sido eliminadas."""
    from orion.adapters.system import desktop

    assert not hasattr(desktop, "_execute_generated_code"), (
        "desktop._execute_generated_code re-aparece; la ejecución de "
        "código generado por LLM fue removida en Fase 1 (seguridad)."
    )
    assert not hasattr(desktop, "_ask_gemini_for_desktop_action")
    assert not hasattr(desktop, "_build_sandbox")


def test_desktop_module_has_no_exec_call():
    """El source de desktop.py no debe contener exec()/compile()/eval()."""
    from orion.adapters.system import desktop

    source = inspect.getsource(desktop)
    # Buscamos llamadas, no la palabra dentro de comments/docstrings
    forbidden = ("exec(", "eval(", "compile(")
    for token in forbidden:
        assert token not in _strip_comments_and_strings(source), (
            f"desktop.py contiene `{token}` — vector RCE prohibido."
        )


def test_desktop_task_action_returns_safe_message():
    """La rama action='task' ya no ejecuta nada — devuelve mensaje claro."""
    from orion.adapters.system.desktop import desktop_control

    out = desktop_control(parameters={"action": "task", "task": "borrá todo"})
    assert "ya no" in out.lower() or "no se ejecutan" in out.lower()
    # Y obviamente nada se ejecutó: la palabra "Listo" no aparece.
    assert "Listo." not in out


# ── open_app.py: sanitizer rechaza metacaracteres ───────────────────────


@pytest.mark.parametrize(
    "malicious",
    [
        "chrome & calc.exe",
        "chrome|whoami",
        "chrome;rmdir /S /Q .",
        "chrome`whoami`",
        "chrome$(whoami)",
        "chrome\nrmdir x",
        "chrome > out.txt",
        "chrome < /etc/passwd",
        "a" * 300,  # demasiado largo
        "",  # vacío
    ],
)
def test_open_app_sanitizer_rejects_metacharacters(malicious: str):
    from orion.adapters.system.open_app import _safe_app_name

    assert _safe_app_name(malicious) is False, (
        f"_safe_app_name dejó pasar input hostil: {malicious!r}"
    )


@pytest.mark.parametrize(
    "legit",
    [
        "chrome",
        "chrome.exe",
        "code",
        "ms-settings:",
        "https://example.com",
        "mailto:foo@bar.com",
        "C:/Program Files/App/app.exe",
    ],
)
def test_open_app_sanitizer_accepts_legit_names(legit: str):
    from orion.adapters.system.open_app import _safe_app_name

    assert _safe_app_name(legit) is True


def test_open_app_no_shell_true_with_llm_input():
    """El source de _launch_windows no debe usar shell=True más."""
    from orion.adapters.system import open_app

    src = _strip_comments_and_strings(inspect.getsource(open_app._launch_windows))
    assert "shell=True" not in src, (
        "_launch_windows volvió a usar shell=True — vector de command "
        "injection con app_name proveniente del LLM."
    )


# ── dev_agent.py: la lista + shell=True rota ────────────────────────────


def test_dev_agent_vscode_no_shell_true():
    from orion.adapters.system import dev_agent

    src = _strip_comments_and_strings(inspect.getsource(dev_agent._open_vscode))
    assert "shell=True" not in src


# ── helper ──────────────────────────────────────────────────────────────


def _strip_comments_and_strings(source: str) -> str:
    """Quita comentarios `#...` y strings triple-quoted para que el match
    no caiga sobre menciones dentro de docstrings."""
    import re

    # Borra comentarios línea a línea
    source = re.sub(r"#.*", "", source)
    # Borra triple-quoted strings (docstrings)
    source = re.sub(r'"""[\s\S]*?"""', "", source)
    source = re.sub(r"'''[\s\S]*?'''", "", source)
    return source
