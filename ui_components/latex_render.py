"""
ui_components.latex_render
==========================
Renderiza expresiones LaTeX a QPixmap usando matplotlib mathtext.
Mathtext NO es LaTeX completo pero entiende la mayoría de la notación
matemática común (\\frac, \\int, \\sum, \\sqrt, ^, _, símbolos griegos, etc.)
y no requiere una instalación de TeX en el sistema.

API principal:
    render_latex_to_pixmap(expr, color="#ffc4cc", fontsize=14, dpi=160) -> QPixmap
    has_latex(text) -> bool
    extract_latex_blocks(text) -> list[(kind, content)] donde kind ∈ {"text","inline","block"}
"""

from __future__ import annotations

import io
import re
import threading

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QImage

# Matplotlib es opcional. Si no está instalado, el chat seguirá funcionando
# pero las fórmulas LaTeX se mostrarán como texto crudo.
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import rcParams
    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False
    plt = None      # type: ignore
    rcParams = {}   # type: ignore

# Cache simple por expresión + color + tamaño
_PIXMAP_CACHE: dict[tuple, QPixmap] = {}
_CACHE_LOCK = threading.Lock()
_MAX_CACHE = 200

# Regex para detectar bloques LaTeX
# - Bloques: $$ ... $$  ó  \[ ... \]
# - Inline:  $ ... $    ó  \( ... \)
_RE_BLOCK  = re.compile(r"\$\$(.+?)\$\$|\\\[(.+?)\\\]", re.DOTALL)
_RE_INLINE = re.compile(r"(?<!\$)\$([^\$\n]+?)\$(?!\$)|\\\((.+?)\\\)", re.DOTALL)


def has_latex(text: str) -> bool:
    if not text:
        return False
    return bool(_RE_BLOCK.search(text) or _RE_INLINE.search(text))


def extract_latex_blocks(text: str) -> list[tuple[str, str]]:
    """Divide el texto en una lista de (kind, content):
        kind ∈ {"text", "inline", "block"}
    Mantiene el orden original.
    """
    if not text:
        return []

    # Primero marcamos los bloques con tokens, luego inline.
    pieces: list[tuple[str, str]] = []
    pos = 0

    # Buscamos tanto bloques como inline en una sola pasada combinada
    combined = re.compile(
        r"\$\$(.+?)\$\$|"        # 1: block $$...$$
        r"\\\[(.+?)\\\]|"        # 2: block \[...\]
        r"(?<!\$)\$([^\$\n]+?)\$(?!\$)|"  # 3: inline $...$
        r"\\\((.+?)\\\)",        # 4: inline \(...\)
        re.DOTALL,
    )

    for m in combined.finditer(text):
        if m.start() > pos:
            pieces.append(("text", text[pos:m.start()]))
        if m.group(1) is not None:
            pieces.append(("block", m.group(1).strip()))
        elif m.group(2) is not None:
            pieces.append(("block", m.group(2).strip()))
        elif m.group(3) is not None:
            pieces.append(("inline", m.group(3).strip()))
        elif m.group(4) is not None:
            pieces.append(("inline", m.group(4).strip()))
        pos = m.end()

    if pos < len(text):
        pieces.append(("text", text[pos:]))

    return pieces


def render_latex_to_pixmap(
    expr: str,
    color: str = "#ffc4cc",
    fontsize: int = 11,
    dpi: int = 120,
) -> QPixmap | None:
    """Renderiza una expresión matemática a QPixmap.
    Retorna None si matplotlib no está instalado o si el parseo falla.
    """
    if not expr or not _HAS_MPL:
        return None

    key = (expr, color, fontsize, dpi)
    with _CACHE_LOCK:
        cached = _PIXMAP_CACHE.get(key)
        if cached is not None:
            return cached

    # Asegurar que la expresión esté envuelta en $...$ para mathtext
    raw = expr.strip()
    if not (raw.startswith("$") and raw.endswith("$")):
        raw = f"${raw}$"

    try:
        # Usamos matplotlib en modo no interactivo
        rcParams["mathtext.fontset"] = "cm"  # Computer Modern, look matemático clásico
        fig = plt.figure(figsize=(0.01, 0.01), dpi=dpi)
        fig.patch.set_alpha(0.0)             # fondo transparente
        text = fig.text(0, 0, raw, fontsize=fontsize, color=color)

        buf = io.BytesIO()
        fig.savefig(
            buf, format="png", dpi=dpi,
            bbox_inches="tight", pad_inches=0.02,
            transparent=True,
        )
        plt.close(fig)

        buf.seek(0)
        img = QImage.fromData(buf.getvalue(), "PNG")
        if img.isNull():
            return None
        pm = QPixmap.fromImage(img)

        with _CACHE_LOCK:
            if len(_PIXMAP_CACHE) > _MAX_CACHE:
                # eviccion FIFO simple
                for k in list(_PIXMAP_CACHE.keys())[: _MAX_CACHE // 4]:
                    _PIXMAP_CACHE.pop(k, None)
            _PIXMAP_CACHE[key] = pm
        return pm

    except Exception as e:
        # Algunos comandos como \begin{align} no los soporta mathtext.
        # Devolvemos None para que el caller use el texto plano.
        print(f"[latex_render] ⚠️ Fallo al renderizar {expr!r}: {e}")
        return None


def clear_cache() -> None:
    with _CACHE_LOCK:
        _PIXMAP_CACHE.clear()
