"""
ui_components.history_panel — Ventana de historial de conversaciones
=====================================================================
Muestra la lista de conversaciones pasadas. Al hacer clic, emite la señal
`conversation_selected(conv_id)` para que la MainWindow la cargue al chat.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from memory.conversations import (
    delete_conversation, list_conversations,
)


class HistoryPanel(QWidget):
    conversation_selected = pyqtSignal(str)   # conv_id

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self._theme = theme
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowTitle("O.R.I.O.N — Historial")
        self.setMinimumSize(440, 480)
        self.resize(500, 560)
        C = theme
        self.setStyleSheet(f"background: {C.BG};")

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        hdr = QLabel("◈  HISTORIAL DE CONVERSACIONES")
        hdr.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        hdr.setStyleSheet(
            f"color: {C.PRI}; background: transparent;"
            f" border-bottom: 1px solid {C.BORDER_B}; padding-bottom: 6px;"
        )
        root.addWidget(hdr)

        sub = QLabel("Haz clic en una conversación para cargarla.")
        sub.setFont(QFont("Courier New", 8))
        sub.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        root.addWidget(sub)

        # Lista scrollable
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
        self._content_lay.setContentsMargins(8, 8, 8, 8)
        self._content_lay.setSpacing(6)
        scroll.setWidget(self._content)
        root.addWidget(scroll, stretch=1)

        # Footer
        footer = QHBoxLayout()
        refresh = QPushButton("⟳  Recargar")
        refresh.setFixedHeight(28)
        refresh.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh.setStyleSheet(self._btn_style(C, color=C.TEXT_MED))
        refresh.clicked.connect(self.reload)
        footer.addWidget(refresh)
        footer.addStretch()

        close = QPushButton("Cerrar")
        close.setFixedHeight(28)
        close.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet(self._btn_style(C, color=C.PRI))
        close.clicked.connect(self.close)
        footer.addWidget(close)
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

    def reload(self) -> None:
        # Limpiar contenido actual
        while self._content_lay.count():
            it = self._content_lay.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

        convs = list_conversations()
        if not convs:
            empty = QLabel(
                "Aún no hay conversaciones guardadas.\n"
                "Cuando hables con ORION aparecerán aquí."
            )
            empty.setStyleSheet(
                f"color: {self._theme.TEXT_DIM}; padding: 30px;"
                f" background: transparent;"
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._content_lay.addWidget(empty)
            self._content_lay.addStretch()
            return

        for c in convs:
            self._content_lay.addWidget(self._build_item(c))
        self._content_lay.addStretch()

    def _build_item(self, conv: dict) -> QWidget:
        C = self._theme
        item = QWidget()
        item.setStyleSheet(
            f"QWidget {{ background: {C.PANEL2}; border: 1px solid {C.BORDER};"
            f" border-radius: 5px; }}"
            f"QWidget:hover {{ border: 1px solid {C.PRI_DIM}; }}"
        )
        item.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(item)
        lay.setContentsMargins(10, 8, 8, 8)
        lay.setSpacing(6)

        col = QVBoxLayout()
        col.setSpacing(2)

        title = QLabel(conv.get("title", "Conversación"))
        title.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.TEXT}; background: transparent; border: none;")
        title.setWordWrap(True)
        col.addWidget(title)

        meta_text = f"{conv.get('started', '')}  ·  {conv.get('msg_count', 0)} mensajes"
        meta = QLabel(meta_text)
        meta.setFont(QFont("Courier New", 7))
        meta.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        col.addWidget(meta)

        lay.addLayout(col, stretch=1)

        # Botón cargar
        load_btn = QPushButton("Abrir")
        load_btn.setFixedHeight(26)
        load_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        load_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        load_btn.setStyleSheet(self._btn_style(C, color=C.GREEN))
        cid = conv.get("id", "")
        load_btn.clicked.connect(lambda _=False, _id=cid: self._on_load(_id))
        lay.addWidget(load_btn)

        # Botón borrar
        del_btn = QPushButton("✕")
        del_btn.setFixedSize(26, 26)
        del_btn.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(self._btn_style(C, color=C.RED))
        del_btn.clicked.connect(lambda _=False, _id=cid: self._on_delete(_id))
        lay.addWidget(del_btn)

        return item

    def _on_load(self, conv_id: str):
        if not conv_id:
            return
        self.conversation_selected.emit(conv_id)
        self.close()

    def _on_delete(self, conv_id: str):
        if not conv_id:
            return
        if delete_conversation(conv_id):
            self.reload()
