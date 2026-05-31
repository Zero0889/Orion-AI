"""
ui_components.notes_panel — Notas rápidas
===========================================
Ventana modal con:
  - Lista de notas a la izquierda (pinneadas arriba, recientes primero)
  - Editor a la derecha (textarea + botones guardar/pin/borrar)
  - Botón "+ Nueva nota"
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSplitter,
    QTextEdit, QVBoxLayout, QWidget,
)

from memory.quick_notes import (
    add_note, delete_note, list_notes, update_note,
)


class _NoteCard(QFrame):
    clicked = pyqtSignal(str)   # note_id

    def __init__(self, note: dict, theme, selected: bool = False, parent=None):
        super().__init__(parent)
        self._note  = note
        self._theme = theme
        self._selected = selected
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFrameShape(QFrame.Shape.StyledPanel)

        C = theme
        border = C.PRI if selected else C.BORDER
        bg     = C.PRI_GHO if selected else C.PANEL2
        pin_mark = "📌 " if note.get("pinned") else ""

        self.setStyleSheet(f"""
            QFrame {{
                background: {bg}; border: 1px solid {border};
                border-radius: 5px;
            }}
            QFrame:hover {{
                border: 1px solid {C.PRI_DIM};
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(2)

        text  = note.get("text", "")
        first = text.splitlines()[0] if text else "(vacío)"
        if len(first) > 60:
            first = first[:57] + "…"

        title = QLabel(pin_mark + first)
        title.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        title.setStyleSheet(
            f"color: {C.TEXT}; background: transparent; border: none;"
        )
        title.setWordWrap(True)
        lay.addWidget(title)

        meta = QLabel(note.get("updated", "")[:16].replace("T", " "))
        meta.setFont(QFont("Courier New", 7))
        meta.setStyleSheet(
            f"color: {C.TEXT_DIM}; background: transparent; border: none;"
        )
        lay.addWidget(meta)

    def mousePressEvent(self, e):
        self.clicked.emit(self._note.get("id", ""))


class NotesPanel(QWidget):
    """Ventana modal de notas rápidas."""

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self._theme = theme
        self._current_id: str | None = None
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowTitle("O.R.I.O.N — Notas rápidas")
        self.setMinimumSize(720, 480)
        self.resize(820, 560)
        C = theme
        self.setStyleSheet(f"background: {C.BG};")

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        # Header
        hdr_row = QHBoxLayout()
        hdr = QLabel("◈  NOTAS RÁPIDAS")
        hdr.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        hdr.setStyleSheet(
            f"color: {C.PRI}; background: transparent;"
            f" border-bottom: 1px solid {C.BORDER_B}; padding-bottom: 6px;"
        )
        hdr_row.addWidget(hdr, stretch=1)

        new_btn = QPushButton("➕  Nueva nota")
        new_btn.setFixedHeight(30)
        new_btn.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setStyleSheet(self._btn_style(C, color=C.GREEN))
        new_btn.clicked.connect(self._on_new)
        hdr_row.addWidget(new_btn)
        root.addLayout(hdr_row)

        # Splitter: lista a la izquierda, editor a la derecha
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)
        splitter.setStyleSheet(f"QSplitter::handle {{ background: {C.BORDER}; }}")

        # ── Lista de notas ──
        list_container = QWidget()
        list_container.setStyleSheet(f"background: {C.PANEL};")
        list_lay = QVBoxLayout(list_container)
        list_lay.setContentsMargins(0, 0, 0, 0)
        list_lay.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(self._scroll_style(C))
        self._list_inner = QWidget()
        self._list_inner.setStyleSheet(f"background: {C.PANEL};")
        self._list_lay = QVBoxLayout(self._list_inner)
        self._list_lay.setContentsMargins(8, 8, 8, 8)
        self._list_lay.setSpacing(6)
        self._scroll.setWidget(self._list_inner)
        list_lay.addWidget(self._scroll)

        splitter.addWidget(list_container)

        # ── Editor ──
        edit_container = QWidget()
        edit_container.setStyleSheet(f"background: {C.PANEL};")
        edit_lay = QVBoxLayout(edit_container)
        edit_lay.setContentsMargins(8, 8, 8, 8)
        edit_lay.setSpacing(6)

        self._editor = QTextEdit()
        self._editor.setFont(QFont("Segoe UI", 10))
        self._editor.setPlaceholderText(
            "Escribe aquí tu nota… (autoguardado al cambiar de nota o al cerrar)"
        )
        self._editor.setStyleSheet(self._editor_style(C))
        edit_lay.addWidget(self._editor, stretch=1)

        # Botones del editor
        btn_row = QHBoxLayout()
        self._pin_btn = QPushButton("📌  Fijar")
        self._pin_btn.setFixedHeight(28)
        self._pin_btn.setFont(QFont("Courier New", 8))
        self._pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pin_btn.setStyleSheet(self._btn_style(C, color=C.ACC2))
        self._pin_btn.clicked.connect(self._on_toggle_pin)
        btn_row.addWidget(self._pin_btn)

        save_btn = QPushButton("💾  Guardar")
        save_btn.setFixedHeight(28)
        save_btn.setFont(QFont("Courier New", 8))
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(self._btn_style(C, color=C.GREEN))
        save_btn.clicked.connect(self._save_current)
        btn_row.addWidget(save_btn)

        btn_row.addStretch()

        del_btn = QPushButton("🗑  Borrar")
        del_btn.setFixedHeight(28)
        del_btn.setFont(QFont("Courier New", 8))
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(self._btn_style(C, color=C.RED))
        del_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(del_btn)
        edit_lay.addLayout(btn_row)

        splitter.addWidget(edit_container)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([260, 540])
        root.addWidget(splitter, stretch=1)

        # Footer
        footer = QHBoxLayout()
        self._status = QLabel("")
        self._status.setFont(QFont("Courier New", 8))
        self._status.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        footer.addWidget(self._status, stretch=1)

        close = QPushButton("Cerrar")
        close.setFixedHeight(28)
        close.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet(self._btn_style(C, color=C.PRI))
        close.clicked.connect(self.close)
        footer.addWidget(close)
        root.addLayout(footer)

        self.reload()

    # ── Estilos ────────────────────────────────────────────────────────────
    @staticmethod
    def _btn_style(C, color: str) -> str:
        return f"""
            QPushButton {{
                background: transparent; color: {color};
                border: 1px solid {C.BORDER_B}; border-radius: 4px;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background: {C.PRI_GHO}; border-color: {C.PRI};
            }}
        """

    @staticmethod
    def _editor_style(C) -> str:
        return f"""
            QTextEdit {{
                background: {C.PANEL2}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 5px;
                padding: 8px; font-family: 'Segoe UI'; font-size: 10pt;
                selection-background-color: {C.PRI_GHO};
            }}
            QTextEdit:focus {{ border: 1px solid {C.PRI}; }}
        """

    @staticmethod
    def _scroll_style(C) -> str:
        return f"""
            QScrollArea {{
                background: {C.PANEL}; border: 1px solid {C.BORDER};
                border-radius: 5px;
            }}
            QScrollBar:vertical {{
                background: {C.BG}; width: 8px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B}; border-radius: 4px; min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {C.PRI_DIM}; }}
        """

    # ── Lógica ────────────────────────────────────────────────────────────
    def reload(self):
        # Vaciar lista
        while self._list_lay.count():
            it = self._list_lay.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

        notes = list_notes()
        if not notes:
            empty = QLabel("No tienes notas aún.\nHaz clic en \"Nueva nota\".")
            empty.setFont(QFont("Courier New", 8))
            empty.setStyleSheet(
                f"color: {self._theme.TEXT_DIM}; padding: 30px;"
                f" background: transparent;"
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._list_lay.addWidget(empty)
            self._list_lay.addStretch()
            self._editor.clear()
            self._current_id = None
            self._refresh_pin_btn()
            return

        # Si no hay seleccionada, elegir la primera
        if not self._current_id or not any(n["id"] == self._current_id for n in notes):
            self._current_id = notes[0]["id"]

        for n in notes:
            card = _NoteCard(n, self._theme, selected=(n["id"] == self._current_id))
            card.clicked.connect(self._on_select)
            self._list_lay.addWidget(card)
        self._list_lay.addStretch()

        # Cargar contenido de la nota actual en el editor
        cur = next((n for n in notes if n["id"] == self._current_id), None)
        if cur:
            self._editor.blockSignals(True)
            self._editor.setPlainText(cur.get("text", ""))
            self._editor.blockSignals(False)
        self._refresh_pin_btn()
        self._status.setText(f"{len(notes)} nota(s)")

    def _refresh_pin_btn(self):
        notes = list_notes()
        cur = next((n for n in notes if n["id"] == self._current_id), None)
        if cur and cur.get("pinned"):
            self._pin_btn.setText("📌  Desfijar")
        else:
            self._pin_btn.setText("📌  Fijar")

    def _on_new(self):
        # Guardar la actual antes
        self._save_current(silent=True)
        n = add_note("")
        if n:
            self._current_id = n.get("id")
            self.reload()
            self._editor.setFocus()

    def _on_select(self, note_id: str):
        if note_id == self._current_id:
            return
        # Guardar la actual antes de cambiar
        self._save_current(silent=True)
        self._current_id = note_id
        self.reload()

    def _on_toggle_pin(self):
        if not self._current_id:
            return
        notes = list_notes()
        cur = next((n for n in notes if n["id"] == self._current_id), None)
        if cur:
            update_note(self._current_id, pinned=not cur.get("pinned", False))
            self.reload()

    def _on_delete(self):
        if not self._current_id:
            return
        delete_note(self._current_id)
        self._current_id = None
        self.reload()

    def _save_current(self, silent: bool = False):
        if not self._current_id:
            return
        text = self._editor.toPlainText()
        update_note(self._current_id, text=text)
        if not silent:
            self._status.setText("✓ Guardada")
            self.reload()

    def closeEvent(self, e):
        self._save_current(silent=True)
        super().closeEvent(e)
