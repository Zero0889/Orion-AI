"""
ui_components.chat_panel
========================
Panel de conversación tipo chat con:
  - Burbujas estilizadas (usuario derecha, ORION izquierda)
  - Avatares por rol
  - Renderizado de markdown básico (negritas, código, listas)
  - Renderizado de LaTeX inline ($...$) y bloque ($$...$$) como imagen
  - Drag & drop (texto, URLs, archivos múltiples)
  - Compatible con la API antigua de LogWidget (append_log, dropped_text,
    dropped_file y dropped_files señales)

Uso desde MainWindow:
    self._log = ChatPanel(theme=C)
    self._log.append_log("Tú: hola")
    self._log.append_log("ORION: hola, señor")
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
    QTextBrowser, QVBoxLayout, QWidget,
)

from ui_components.latex_render import (
    extract_latex_blocks, has_latex, render_latex_to_pixmap,
)


# ── Roles / tipos de mensaje ─────────────────────────────────────────────────
ROLE_USER  = "user"
ROLE_AI    = "ai"
ROLE_SYS   = "sys"
ROLE_ERR   = "err"
ROLE_FILE  = "file"


def _classify(text: str) -> tuple[str, str]:
    """Detecta el rol según el prefijo y retorna (rol, contenido_sin_prefijo)."""
    if not text:
        return ROLE_SYS, ""
    tl = text.lstrip().lower()
    for prefix, role in (
        ("tú:",      ROLE_USER),
        ("tu:",      ROLE_USER),
        ("orion:",   ROLE_AI),
        ("o.r.i.o.n:", ROLE_AI),
        ("archivo:", ROLE_FILE),
        ("sistema:", ROLE_SYS),
        ("sys:",     ROLE_SYS),
        ("error:",   ROLE_ERR),
        ("[search]", ROLE_SYS),
    ):
        if tl.startswith(prefix):
            content = text[len(prefix):].lstrip() if text.lower().startswith(prefix) \
                      else text.split(":", 1)[1].lstrip()
            return role, content
    # heurística de error
    if "error" in tl:
        return ROLE_ERR, text
    return ROLE_SYS, text


# ── Avatar circular dibujado (sin necesidad de imágenes externas) ────────────
class Avatar(QWidget):
    def __init__(self, role: str, theme, size: int = 28, parent=None):
        super().__init__(parent)
        self._role  = role
        self._theme = theme
        self._size  = size
        self.setFixedSize(size, size)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        C = self._theme
        r = self._size
        # Color de fondo según rol
        bg, fg, letter = {
            ROLE_USER: (QColor(C.PANEL2), QColor(C.WHITE),    "U"),
            ROLE_AI:   (QColor(C.PRI),    QColor(C.DARK),     "◈"),
            ROLE_SYS:  (QColor(C.PANEL),  QColor(C.TEXT_MED), "i"),
            ROLE_ERR:  (QColor(C.RED),    QColor(C.WHITE),    "!"),
            ROLE_FILE: (QColor(C.GREEN),  QColor(C.DARK),     "📎"),
        }.get(self._role, (QColor(C.PANEL), QColor(C.TEXT_MED), "?"))

        p.setBrush(QBrush(bg))
        p.setPen(QPen(QColor(C.BORDER_B), 1))
        p.drawEllipse(0, 0, r - 1, r - 1)

        font = QFont("Segoe UI Emoji" if letter == "📎" else "Courier New",
                     int(r * 0.45), QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(QPen(fg, 1))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, letter)


# ── Etiqueta que renderiza markdown + LaTeX intercalado ──────────────────────
class _RichContent(QWidget):
    """Un contenedor vertical que recibe texto y lo divide en bloques:
      - Texto plano → QLabel con markdown→HTML
      - LaTeX → QLabel con pixmap renderizado por matplotlib
    """

    def __init__(self, text: str, role: str, theme, parent=None):
        super().__init__(parent)
        self._text  = text
        self._role  = role
        self._theme = theme

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        text_color = self._role_text_color()
        latex_color = text_color   # usamos el mismo color para los símbolos

        # Si hay LaTeX, dividimos en bloques. Si no, una sola label.
        if has_latex(text):
            chunks = extract_latex_blocks(text)
            # Agrupamos texto plano consecutivo + inline en un mismo QLabel
            # cuando sea posible para que fluya como párrafo.
            buffer_html: list[str] = []
            for kind, content in chunks:
                if kind == "text":
                    buffer_html.append(_markdown_to_html(content, text_color))
                elif kind == "inline":
                    pm = render_latex_to_pixmap(
                        content, color=latex_color, fontsize=10, dpi=110,
                    )
                    if pm is not None:
                        # Convertimos a HTML <img> guardando el pixmap en cache temporal
                        # mediante un esquema "data:" para QLabel/QTextBrowser.
                        buffer_html.append(_pixmap_to_html_img(pm, height=15))
                    else:
                        buffer_html.append(_markdown_to_html(f"${content}$", text_color))
                else:  # block
                    # Volcamos lo acumulado antes
                    if buffer_html:
                        lay.addWidget(_make_html_label("".join(buffer_html), text_color))
                        buffer_html = []
                    pm = render_latex_to_pixmap(
                        content, color=latex_color, fontsize=12, dpi=130,
                    )
                    if pm is not None:
                        img_lbl = QLabel()
                        img_lbl.setPixmap(pm)
                        img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        img_lbl.setStyleSheet("background: transparent;")
                        img_lbl.setSizePolicy(
                            QSizePolicy.Policy.Preferred,
                            QSizePolicy.Policy.Preferred,
                        )
                        lay.addWidget(img_lbl)
                    else:
                        lay.addWidget(_make_html_label(
                            f"<pre style='color:{text_color}'>$$ {html.escape(content)} $$</pre>",
                            text_color,
                        ))
            if buffer_html:
                lay.addWidget(_make_html_label("".join(buffer_html), text_color))
        else:
            html_str = _markdown_to_html(text, text_color)
            lay.addWidget(_make_html_label(html_str, text_color))

    def _role_text_color(self) -> str:
        C = self._theme
        return {
            ROLE_USER: C.WHITE,
            ROLE_AI:   C.TEXT,
            ROLE_SYS:  C.TEXT_MED,
            ROLE_ERR:  C.WHITE,
            ROLE_FILE: C.TEXT,
        }.get(self._role, C.TEXT)


def _make_html_label(html_str: str, color: str) -> QLabel:
    lbl = QLabel(html_str)
    lbl.setWordWrap(True)
    lbl.setOpenExternalLinks(True)
    lbl.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse |
        Qt.TextInteractionFlag.LinksAccessibleByMouse
    )
    lbl.setStyleSheet(
        f"color:{color}; background: transparent;"
        f" border: none; padding: 0; margin: 0;"
    )
    lbl.setFont(QFont("Segoe UI", 10))
    lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
    return lbl


# Markdown muy básico (sin dependencia externa). Soporta:
#   **negrita**, *cursiva*, `código`, ```bloque```, listas con -, enlaces [t](u)
_RE_CODE_BLOCK = re.compile(r"```(?:\w+)?\n?(.+?)```", re.DOTALL)
_RE_INLINE_CODE = re.compile(r"`([^`]+?)`")
_RE_BOLD       = re.compile(r"\*\*(.+?)\*\*")
_RE_ITALIC     = re.compile(r"(?<!\*)\*([^\*\n]+?)\*(?!\*)")
_RE_LINK       = re.compile(r"\[([^\]]+?)\]\((https?://[^\s\)]+)\)")
_RE_LIST       = re.compile(r"^[\-\*•] (.+)$", re.MULTILINE)


def _markdown_to_html(text: str, color: str) -> str:
    if not text:
        return ""

    # Extraer bloques de código primero (para no escapar su contenido)
    code_blocks: list[str] = []
    def _stash_code(m):
        code_blocks.append(m.group(1))
        return f"\x00CODE{len(code_blocks)-1}\x00"
    text = _RE_CODE_BLOCK.sub(_stash_code, text)

    text = html.escape(text)

    # Restaurar bloques con formato <pre>
    def _restore_code(m):
        idx = int(m.group(1))
        body = html.escape(code_blocks[idx])
        return (
            f"<pre style='background:#00000040; color:{color};"
            f" padding:6px; border-left:2px solid {color};"
            f" font-family:Consolas,\"Courier New\",monospace; white-space:pre-wrap;'>"
            f"{body}</pre>"
        )
    text = re.sub(r"\x00CODE(\d+)\x00", _restore_code, text)

    # Inline
    text = _RE_INLINE_CODE.sub(
        rf"<code style='background:#00000033; padding:1px 4px;"
        rf" border-radius:3px; font-family:Consolas,monospace; color:{color};'>\1</code>",
        text,
    )
    text = _RE_BOLD.sub(r"<b>\1</b>", text)
    text = _RE_ITALIC.sub(r"<i>\1</i>", text)
    text = _RE_LINK.sub(
        rf"<a href='\2' style='color:{color}; text-decoration:underline;'>\1</a>",
        text,
    )
    text = _RE_LIST.sub(r"&nbsp;&nbsp;• \1", text)

    # Saltos de línea como <br>
    text = text.replace("\n", "<br>")
    return text


def _pixmap_to_html_img(pm: QPixmap, height: int = 18) -> str:
    """Codifica un QPixmap como <img src='data:image/png;base64,...'> para QLabel.
    NOTA: QLabel SI soporta src='data:image/png;base64,...' a partir de Qt 5.
    Si por alguna razón no se ve, el contenedor cae al texto plano.
    """
    import base64
    from PyQt6.QtCore import QBuffer, QByteArray, QIODevice

    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pm.save(buf, "PNG")
    b64 = base64.b64encode(bytes(ba)).decode("ascii")
    # vertical-align:middle para que se integre al flujo del texto
    return (
        f"<img src='data:image/png;base64,{b64}'"
        f" style='vertical-align:middle;' height='{height}'>"
    )


# ── Burbuja: avatar + contenido + estilo según rol ───────────────────────────
class ChatBubble(QFrame):
    def __init__(self, text: str, role: str, theme, parent=None):
        super().__init__(parent)
        self._theme = theme
        self._role  = role
        C = theme

        outer = QHBoxLayout(self)
        outer.setContentsMargins(2, 2, 2, 2)
        outer.setSpacing(8)

        # Para el usuario, alineamos a la derecha (avatar al final)
        if role == ROLE_USER:
            outer.addStretch(1)

        # Avatar
        avatar = Avatar(role, theme, size=30)

        # Bubble interna
        bubble = QFrame()
        bubble_lay = QVBoxLayout(bubble)
        bubble_lay.setContentsMargins(12, 9, 12, 10)
        bubble_lay.setSpacing(5)

        # Pequeño header con el nombre del rol
        name_map = {
            ROLE_USER: "Tú",
            ROLE_AI:   "O.R.I.O.N",
            ROLE_SYS:  "Sistema",
            ROLE_ERR:  "Error",
            ROLE_FILE: "Archivo",
        }
        color_map = {
            ROLE_USER: C.WHITE,
            ROLE_AI:   C.PRI,
            ROLE_SYS:  C.ACC2,
            ROLE_ERR:  C.RED,
            ROLE_FILE: C.GREEN,
        }
        name_lbl = QLabel(name_map.get(role, "?"))
        name_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        name_lbl.setStyleSheet(
            f"color:{color_map.get(role, C.PRI)};"
            f" background: transparent; letter-spacing: 2px;"
            f" border: none; padding: 0; margin: 0;"
        )
        bubble_lay.addWidget(name_lbl)

        # Contenido
        content = _RichContent(text, role, theme)
        bubble_lay.addWidget(content)

        # Estilos según rol — distintos radios para diferenciar visualmente
        # los hablantes (usuario derecha, ORION izquierda) y mejorar la
        # estética del panel de conversación.
        if role == ROLE_USER:
            bg = C.PANEL2
            border = C.BORDER_B
            radii = "border-radius:10px; border-bottom-right-radius:2px;"
        elif role == ROLE_AI:
            bg = C.PANEL
            border = C.PRI_DIM
            radii = "border-radius:10px; border-bottom-left-radius:2px;"
        elif role == ROLE_ERR:
            bg = getattr(C, "BTN_BG_ERR", C.PANEL2)
            border = C.RED
            radii = "border-radius:10px;"
        elif role == ROLE_FILE:
            bg = C.PANEL2
            border = C.GREEN_D
            radii = "border-radius:10px;"
        else:
            bg = C.PANEL
            border = C.BORDER
            radii = "border-radius:10px;"

        bubble.setStyleSheet(
            f"QFrame {{ background:{bg}; border:1px solid {border}; {radii} }}"
        )
        bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        bubble.setMaximumWidth(520)

        if role == ROLE_USER:
            # avatar a la derecha
            outer.addWidget(bubble, stretch=0)
            outer.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignTop)
        else:
            outer.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignTop)
            outer.addWidget(bubble, stretch=0)
            outer.addStretch(1)


# ── Panel principal ──────────────────────────────────────────────────────────
class ChatPanel(QWidget):
    """Reemplazo del antiguo LogWidget. Misma API pública para no romper
    nada en MainWindow.

    Signals:
        dropped_text(str)   — el usuario soltó texto/URL
        dropped_file(str)   — soltó UN archivo (compatibilidad)
        dropped_files(list) — soltó UNO o VARIOS archivos
    """

    dropped_text = pyqtSignal(str)
    dropped_file = pyqtSignal(str)
    dropped_files = pyqtSignal(list)

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self._theme = theme
        self.setAcceptDrops(True)

        C = theme

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Scroll area que contiene todas las burbujas
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                background: {C.PANEL};
                border: 1px solid {C.BORDER};
                border-radius: 5px;
            }}
            QScrollBar:vertical {{
                background: {C.BG}; width: 8px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B}; border-radius: 4px; min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {C.PRI_DIM}; }}
        """)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._content = QWidget()
        self._content.setStyleSheet(f"background: {C.PANEL};")
        self._content_lay = QVBoxLayout(self._content)
        self._content_lay.setContentsMargins(8, 8, 8, 8)
        self._content_lay.setSpacing(6)
        self._content_lay.addStretch(1)  # empuja todas las burbujas hacia arriba

        self._scroll.setWidget(self._content)
        root.addWidget(self._scroll)

        # Para que el drop visual se note: borde resaltado mientras se arrastra
        self._drag_over = False

        # Auto-scroll: cuando se añade un mensaje, bajamos al final
        # Lo hacemos con un timer corto para esperar a que se calcule el tamaño
        self._scroll_tmr = QTimer(self)
        self._scroll_tmr.setSingleShot(True)
        self._scroll_tmr.timeout.connect(self._scroll_to_bottom)

        # Cap de mensajes (para no consumir memoria en sesiones largas)
        self._max_bubbles = 200

    # ── API pública ────────────────────────────────────────────────────────
    def append_log(self, text: str) -> None:
        """Misma firma que el viejo LogWidget. Detecta el rol según el prefijo."""
        text = (text or "").strip()
        if not text:
            return
        role, content = _classify(text)
        # Si el contenido quedó vacío (ej. "Sistema:") usamos el texto original
        if not content:
            content = text
        self.add_message(role, content)

    def add_message(self, role: str, content: str) -> None:
        bubble = ChatBubble(content, role, self._theme)
        # Insertar antes del stretch final
        idx = self._content_lay.count() - 1
        self._content_lay.insertWidget(idx, bubble)
        self._enforce_cap()
        self._scroll_tmr.start(30)

    def clear(self) -> None:
        while self._content_lay.count() > 1:
            item = self._content_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    # ── Internos ──────────────────────────────────────────────────────────
    def _enforce_cap(self) -> None:
        # Eliminar las burbujas más viejas si pasamos el límite
        count_bubbles = self._content_lay.count() - 1
        if count_bubbles <= self._max_bubbles:
            return
        excess = count_bubbles - self._max_bubbles
        for _ in range(excess):
            item = self._content_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _scroll_to_bottom(self) -> None:
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── Drag & drop ────────────────────────────────────────────────────────
    def dragEnterEvent(self, e):
        m = e.mimeData()
        if m.hasUrls() or m.hasText():
            e.acceptProposedAction()
            self._drag_over = True
            self._update_border()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasText():
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self._drag_over = False
        self._update_border()

    def dropEvent(self, e):
        self._drag_over = False
        self._update_border()
        m = e.mimeData()

        # Archivos: aceptar TODOS los locales
        if m.hasUrls():
            files: list[str] = []
            urls_text: list[str] = []
            for url in m.urls():
                if url.isLocalFile():
                    p = url.toLocalFile()
                    if Path(p).is_file():
                        files.append(p)
                elif url.scheme() in ("http", "https"):
                    urls_text.append(url.toString())
            if files:
                self.dropped_files.emit(files)
                # Mantener compatibilidad: emitir dropped_file solo para el primero
                self.dropped_file.emit(files[0])
                e.acceptProposedAction()
                return
            if urls_text:
                for u in urls_text:
                    self.dropped_text.emit(u)
                e.acceptProposedAction()
                return

        if m.hasText():
            t = m.text().strip()
            if t:
                self.dropped_text.emit(t)
                e.acceptProposedAction()
                return
        e.ignore()

    def _update_border(self):
        C = self._theme
        border = C.PRI if self._drag_over else C.BORDER
        self._scroll.setStyleSheet(self._scroll.styleSheet().replace(
            f"border: 1px solid {C.PRI};", f"border: 1px solid {C.BORDER};"
        ))
        # Forzar nuevo border
        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                background: {C.PANEL};
                border: 1px solid {border};
                border-radius: 5px;
            }}
            QScrollBar:vertical {{
                background: {C.BG}; width: 8px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B}; border-radius: 4px; min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {C.PRI_DIM}; }}
        """)
