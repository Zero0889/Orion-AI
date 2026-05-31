"""
ui_components.onboarding — Wizard de configuración inicial
============================================================
Reemplazo del SetupOverlay de página única con un asistente multi-paso:

  1) Bienvenida
  2) Clave API de Gemini (con enlace a la consola y validación)
  3) Confirmación de sistema operativo
  4) Selección de tema con vista previa
  5) Resumen y "Inicializar"

Emite la señal `done(api_key: str, os_name: str, theme_id: str)` al finalizar.
"""

from __future__ import annotations

import platform
import webbrowser

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from config.theme import load_theme_name


_GEMINI_KEY_URL = "https://aistudio.google.com/app/apikey"
_OS = platform.system().lower()


class OnboardingWizard(QWidget):
    done = pyqtSignal(str, str, str)   # api_key, os_name, theme_id

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self._theme = theme
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        C = theme
        self.setStyleSheet(f"""
            OnboardingWizard {{
                background: rgba(10, 2, 5, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 8px;
            }}
        """)

        # Detectar OS
        detected_os = {"darwin": "mac", "windows": "windows"}.get(_OS, "linux")
        self._state: dict = {
            "api_key":  "",
            "os":       detected_os,
            "theme":    load_theme_name(),
        }

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(10)

        # Cabecera con título dinámico
        self._step_label = QLabel("PASO 1 DE 5")
        self._step_label.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        self._step_label.setStyleSheet(
            f"color: {C.PRI_DIM}; background: transparent; letter-spacing: 2px;"
        )
        self._step_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._step_label)

        self._title_label = QLabel("◈  BIENVENIDO A O.R.I.O.N")
        self._title_label.setFont(QFont("Courier New", 14, QFont.Weight.Bold))
        self._title_label.setStyleSheet(
            f"color: {C.PRI}; background: transparent;"
        )
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._title_label)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};")
        root.addWidget(sep)

        # Stack de páginas (el tema se elige luego en Ajustes)
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_welcome())
        self._stack.addWidget(self._build_api_step())
        self._stack.addWidget(self._build_os_step(detected_os))
        self._stack.addWidget(self._build_done_step())
        root.addWidget(self._stack, stretch=1)

        # Footer: Atrás / Siguiente
        nav = QHBoxLayout()
        self._back_btn = QPushButton("◂  Atrás")
        self._back_btn.setFixedHeight(34)
        self._back_btn.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet(self._btn_style(C, color=C.TEXT_MED))
        self._back_btn.clicked.connect(self._go_back)
        nav.addWidget(self._back_btn)
        nav.addStretch()

        self._next_btn = QPushButton("Siguiente  ▸")
        self._next_btn.setFixedHeight(34)
        self._next_btn.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.setStyleSheet(self._btn_style(C, color=C.PRI))
        self._next_btn.clicked.connect(self._go_next)
        nav.addWidget(self._next_btn)
        root.addLayout(nav)

        self._refresh_step_meta()

    # ── Estilos ───────────────────────────────────────────────────────────
    @staticmethod
    def _btn_style(C, color: str) -> str:
        return f"""
            QPushButton {{
                background: transparent; color: {color};
                border: 1px solid {C.BORDER_B}; border-radius: 4px;
                padding: 0 20px;
            }}
            QPushButton:hover {{
                background: {C.PRI_GHO}; border-color: {C.PRI};
            }}
            QPushButton:disabled {{
                color: {C.TEXT_DIM}; border-color: {C.BORDER};
            }}
        """

    @staticmethod
    def _input_style(C) -> str:
        return f"""
            QLineEdit {{
                background: #15040a; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 4px;
                padding: 6px 10px; font-family: 'Courier New'; font-size: 10pt;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """

    def _lbl(self, txt: str, *, big=False, color=None,
             align=Qt.AlignmentFlag.AlignCenter) -> QLabel:
        C = self._theme
        l = QLabel(txt)
        l.setAlignment(align)
        l.setFont(QFont(
            "Courier New",
            12 if big else 9,
            QFont.Weight.Bold if big else QFont.Weight.Normal,
        ))
        l.setStyleSheet(
            f"color: {color or (C.PRI if big else C.TEXT)};"
            f" background: transparent;"
        )
        l.setWordWrap(True)
        return l

    # ── Pasos ─────────────────────────────────────────────────────────────
    def _build_welcome(self) -> QWidget:
        C = self._theme
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 18, 0, 0)
        lay.setSpacing(10)

        lay.addWidget(self._lbl(
            "Asistente personal con voz, visión, automatización del PC,\n"
            "memoria a largo plazo y un montón más.",
            color=C.TEXT,
        ))
        lay.addSpacing(6)
        lay.addWidget(self._lbl(
            "Te guiaremos en 4 pasos rápidos para dejarlo listo.",
            color=C.PRI_DIM,
        ))
        lay.addStretch()
        return w

    def _build_api_step(self) -> QWidget:
        C = self._theme
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 14, 0, 0)
        lay.setSpacing(8)

        lay.addWidget(self._lbl(
            "Pega tu clave de Gemini para que ORION pueda pensar.",
            color=C.TEXT,
        ))

        self._api_input = QLineEdit()
        self._api_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_input.setPlaceholderText("AIza…")
        self._api_input.setStyleSheet(self._input_style(C))
        self._api_input.textChanged.connect(self._validate_api_step)
        lay.addWidget(self._api_input)

        row = QHBoxLayout()
        get_key_btn = QPushButton("🔑  Obtener clave (aistudio.google.com)")
        get_key_btn.setFixedHeight(28)
        get_key_btn.setFont(QFont("Courier New", 8))
        get_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        get_key_btn.setStyleSheet(self._btn_style(C, color=C.ACC2))
        get_key_btn.clicked.connect(lambda: webbrowser.open(_GEMINI_KEY_URL))
        row.addWidget(get_key_btn)

        self._api_show_btn = QPushButton("Mostrar")
        self._api_show_btn.setFixedHeight(28)
        self._api_show_btn.setFont(QFont("Courier New", 8))
        self._api_show_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._api_show_btn.setStyleSheet(self._btn_style(C, color=C.TEXT_MED))
        self._api_show_btn.setCheckable(True)
        self._api_show_btn.clicked.connect(self._toggle_api_visibility)
        row.addWidget(self._api_show_btn)
        row.addStretch()
        lay.addLayout(row)

        info = self._lbl(
            "La clave se guarda solo en este equipo, en config/api_keys.json.",
            color=C.TEXT_DIM,
        )
        info.setAlignment(Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(info)

        self._api_error = self._lbl("", color=C.RED, align=Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self._api_error)
        lay.addStretch()
        return w

    def _toggle_api_visibility(self):
        if self._api_show_btn.isChecked():
            self._api_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self._api_show_btn.setText("Ocultar")
        else:
            self._api_input.setEchoMode(QLineEdit.EchoMode.Password)
            self._api_show_btn.setText("Mostrar")

    def _validate_api_step(self):
        # Limpia el error al editar
        self._api_error.setText("")

    def _build_os_step(self, detected: str) -> QWidget:
        C = self._theme
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 14, 0, 0)
        lay.setSpacing(8)

        det_name = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}[detected]
        lay.addWidget(self._lbl(
            f"Detecté que estás en {det_name}. ¿Es correcto?",
            color=C.TEXT,
        ))

        row = QHBoxLayout()
        row.setSpacing(6)
        self._os_btns: dict[str, QPushButton] = {}
        labels = {"windows": "⊞  Windows", "mac": "  macOS", "linux": "🐧  Linux"}
        for key in ("windows", "mac", "linux"):
            b = QPushButton(labels[key])
            b.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            b.setFixedHeight(38)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _, k=key: self._select_os(k))
            row.addWidget(b)
            self._os_btns[key] = b
        lay.addLayout(row)
        self._select_os(detected)
        lay.addStretch()
        return w

    def _select_os(self, key: str):
        C = self._theme
        self._state["os"] = key
        pal = {
            "windows": (C.PRI, C.PRI_GHO),
            "mac":     (C.ACC2, "#221400"),
            "linux":   (C.GREEN, "#001a0d"),
        }
        for k, btn in self._os_btns.items():
            if k == key:
                fg, bg = pal[k]
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {fg}; color: {C.DARK};
                        border: none; border-radius: 4px; font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #15040a; color: {C.TEXT_DIM};
                        border: 1px solid {C.BORDER}; border-radius: 4px;
                    }}
                    QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
                """)

    def _build_done_step(self) -> QWidget:
        C = self._theme
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 14, 0, 0)
        lay.setSpacing(8)

        self._done_lbl = self._lbl(
            "Todo listo. Pulsa INICIALIZAR para arrancar ORION.",
            color=C.TEXT,
        )
        lay.addWidget(self._done_lbl)

        self._summary = QLabel("")
        self._summary.setFont(QFont("Courier New", 8))
        self._summary.setStyleSheet(
            f"color: {C.TEXT_DIM}; background: transparent;"
            f" border: 1px solid {C.BORDER}; border-radius: 4px; padding: 8px;"
        )
        self._summary.setWordWrap(True)
        lay.addWidget(self._summary)

        tip = self._lbl(
            "Tip: Atajo F9 → modo compacto · F11 → pantalla completa · F4 → mute.",
            color=C.PRI_DIM,
        )
        tip.setAlignment(Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(tip)
        lay.addStretch()
        return w

    # ── Navegación ────────────────────────────────────────────────────────
    def _refresh_step_meta(self):
        i = self._stack.currentIndex()
        titles = [
            "◈  BIENVENIDO A O.R.I.O.N",
            "🔑  CLAVE API DE GEMINI",
            "💻  SISTEMA OPERATIVO",
            "▸  TODO LISTO",
        ]
        self._step_label.setText(f"PASO {i + 1} DE {self._stack.count()}")
        self._title_label.setText(titles[i])
        # Botones
        self._back_btn.setEnabled(i > 0)
        if i == self._stack.count() - 1:
            self._next_btn.setText("▸  INICIALIZAR")
            self._refresh_summary()
        else:
            self._next_btn.setText("Siguiente  ▸")

    def _refresh_summary(self):
        os_names = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}
        masked = "(no establecida)"
        if self._state["api_key"]:
            k = self._state["api_key"]
            masked = k[:4] + "…" + k[-4:] if len(k) > 12 else "•••"
        self._summary.setText(
            f"• Clave Gemini:  {masked}\n"
            f"• Sistema:        {os_names.get(self._state['os'], '?')}\n"
            f"\nPuedes cambiar el tema en Ajustes una vez dentro."
        )

    def _go_back(self):
        i = self._stack.currentIndex()
        if i > 0:
            self._stack.setCurrentIndex(i - 1)
            self._refresh_step_meta()

    def _go_next(self):
        i = self._stack.currentIndex()
        # Validación por paso
        if i == 1:  # API step
            key = self._api_input.text().strip()
            if not key:
                self._api_error.setText("Pega tu clave para continuar, señor.")
                return
            if len(key) < 20:
                self._api_error.setText("La clave parece demasiado corta.")
                return
            self._state["api_key"] = key

        if i < self._stack.count() - 1:
            self._stack.setCurrentIndex(i + 1)
            self._refresh_step_meta()
            return

        # Último paso → emitir done
        self.done.emit(
            self._state["api_key"],
            self._state["os"],
            self._state["theme"],
        )
