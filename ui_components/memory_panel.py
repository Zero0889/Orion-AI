"""
ui_components.memory_panel — Panel de memoria de ORION
=========================================================
Muestra las categorías de memoria (identity, preferences, …) con edición
inline. Se usa tanto como ventana modal independiente como embebido en un
tab del SettingsPanel.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout,
    QWidget,
)


class MemoryPanel(QWidget):
    """Panel de memoria. Puede usarse:
      · como ventana modal: pass `embedded=False` (por defecto)
      · embebido en otro widget (p.ej. en un tab): pass `embedded=True`
    """

    memory_changed = pyqtSignal()

    _CATEGORIES = [
        ("identity",      "Identidad",     "#ff2a4d"),
        ("preferences",   "Preferencias",  "#ffb84d"),
        ("projects",      "Proyectos",     "#33ff99"),
        ("relationships", "Relaciones",    "#ff6b1a"),
        ("wishes",        "Deseos",        "#cc44ff"),
        ("notes",         "Notas",         "#aaaaaa"),
    ]

    def __init__(self, theme, parent=None, embedded: bool = False):
        super().__init__(parent)
        self._theme = theme
        self._embedded = embedded

        C = theme
        if not embedded:
            self.setWindowFlags(
                Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint
            )
            self.setWindowTitle("O.R.I.O.N — Memoria")
            self.setMinimumSize(560, 480)
            self.resize(640, 540)
            self.setStyleSheet(f"background: {C.BG};")

        root = QVBoxLayout(self)
        if embedded:
            root.setContentsMargins(0, 0, 0, 0)
        else:
            root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        if not embedded:
            hdr = QLabel("◈  MEMORIA DE O.R.I.O.N")
            hdr.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
            hdr.setStyleSheet(
                f"color: {C.PRI}; background: transparent;"
                f" border-bottom: 1px solid {C.BORDER_B}; padding-bottom: 6px;"
            )
            root.addWidget(hdr)

        sub = QLabel("Lo que ORION recuerda de ti. Edita o borra cualquier entrada.")
        sub.setFont(QFont("Courier New", 8))
        sub.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        root.addWidget(sub)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: 1px solid {C.BORDER}; border-radius: 5px; }}
            QScrollBar:vertical {{
                background: {C.BG}; width: 10px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B}; border-radius: 4px; min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {C.PRI_DIM}; }}
        """)

        self._content = QWidget()
        self._content.setStyleSheet(f"background: {C.PANEL};")
        self._content_lay = QVBoxLayout(self._content)
        self._content_lay.setContentsMargins(10, 10, 10, 10)
        self._content_lay.setSpacing(8)
        scroll.setWidget(self._content)
        root.addWidget(scroll, stretch=1)

        # Footer
        footer = QHBoxLayout()
        footer.setSpacing(6)
        refresh_btn = QPushButton("⟳  Recargar")
        refresh_btn.setFixedHeight(28)
        refresh_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet(self._btn_style(C, color=C.TEXT_MED))
        refresh_btn.clicked.connect(self.reload)
        footer.addWidget(refresh_btn)
        footer.addStretch()
        if not embedded:
            close_btn = QPushButton("Cerrar")
            close_btn.setFixedHeight(28)
            close_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
            close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            close_btn.setStyleSheet(self._btn_style(C, color=C.PRI))
            close_btn.clicked.connect(self.close)
            footer.addWidget(close_btn)
        root.addLayout(footer)

        self.reload()

    @staticmethod
    def _btn_style(C, color: str) -> str:
        return f"""
            QPushButton {{
                background: transparent; color: {color};
                border: 1px solid {C.BORDER}; border-radius: 4px;
                padding: 0 14px;
            }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.PRI}; }}
        """

    def reload(self):
        while self._content_lay.count():
            item = self._content_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        try:
            from memory.memory_manager import load_memory
            memory = load_memory()
        except Exception as e:
            err = QLabel(f"Error al cargar memoria: {e}")
            err.setStyleSheet(f"color: {self._theme.RED};")
            self._content_lay.addWidget(err)
            return

        C = self._theme
        total = 0
        for cat_id, cat_name, cat_color in self._CATEGORIES:
            entries = memory.get(cat_id, {}) or {}
            section = self._build_section(cat_id, cat_name, cat_color, entries)
            self._content_lay.addWidget(section)
            total += len(entries)

        if total == 0:
            empty = QLabel(
                "Aún no hay entradas en la memoria.\n"
                "Cuéntale algo a ORION sobre ti y aparecerá aquí."
            )
            empty.setStyleSheet(
                f"color: {C.TEXT_DIM}; padding: 30px; background: transparent;"
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._content_lay.addWidget(empty)

        self._content_lay.addStretch()

    def _build_section(self, cat_id: str, cat_name: str, color: str,
                        entries: dict) -> QWidget:
        C = self._theme
        wrap = QWidget()
        wrap.setStyleSheet(
            f"background: {C.PANEL2}; border: 1px solid {C.BORDER};"
            f" border-radius: 5px;"
        )
        v = QVBoxLayout(wrap)
        v.setContentsMargins(10, 8, 10, 10)
        v.setSpacing(6)

        hdr_row = QHBoxLayout()
        title = QLabel(f"▸  {cat_name.upper()}  ({len(entries)})")
        title.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {color}; background: transparent; border: none;")
        hdr_row.addWidget(title)
        hdr_row.addStretch()
        v.addLayout(hdr_row)

        if not entries:
            lbl = QLabel("    Vacío")
            lbl.setFont(QFont("Courier New", 8))
            lbl.setStyleSheet(
                f"color: {C.TEXT_DIM}; background: transparent; border: none;"
            )
            v.addWidget(lbl)
            return wrap

        for key, entry in entries.items():
            val = entry.get("value", "") if isinstance(entry, dict) else str(entry)
            updated = entry.get("updated", "") if isinstance(entry, dict) else ""
            v.addLayout(self._build_entry_row(cat_id, key, val, updated))

        return wrap

    def _build_entry_row(self, cat_id: str, key: str, value: str,
                          updated: str) -> QHBoxLayout:
        C = self._theme
        row = QHBoxLayout()
        row.setSpacing(6)

        key_lbl = QLabel(key)
        key_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        key_lbl.setStyleSheet(
            f"color: {C.TEXT_MED}; background: transparent; border: none;"
        )
        key_lbl.setFixedWidth(130)
        key_lbl.setWordWrap(True)
        row.addWidget(key_lbl)

        editor = QLineEdit(value)
        editor.setFont(QFont("Courier New", 9))
        editor.setStyleSheet(f"""
            QLineEdit {{
                background: {C.BG}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 3px;
                padding: 3px 6px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        row.addWidget(editor, stretch=1)

        save_btn = QPushButton("✓")
        save_btn.setFixedSize(28, 26)
        save_btn.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setToolTip("Guardar cambios")
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.GREEN};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.GREEN}; }}
        """)
        save_btn.clicked.connect(lambda: self._save_entry(cat_id, key, editor.text()))
        row.addWidget(save_btn)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(28, 26)
        del_btn.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setToolTip("Borrar entrada")
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.RED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ background: #2a060f; border-color: {C.RED}; }}
        """)
        del_btn.clicked.connect(lambda: self._delete_entry(cat_id, key))
        row.addWidget(del_btn)

        return row

    def _save_entry(self, cat_id: str, key: str, value: str):
        try:
            from memory.memory_manager import update_memory
            update_memory({cat_id: {key: {"value": value.strip()}}})
            self.memory_changed.emit()
            self.reload()
        except Exception as e:
            print(f"[MemoryPanel] Error guardando: {e}")

    def _delete_entry(self, cat_id: str, key: str):
        try:
            from memory.memory_manager import forget
            forget(key, category=cat_id)
            self.memory_changed.emit()
            self.reload()
        except Exception as e:
            print(f"[MemoryPanel] Error borrando: {e}")
