"""
ui_components.settings_panel — Panel de configuración nativo
=============================================================
Ventana modal con pestañas para editar las opciones de ORION sin tocar
archivos JSON manualmente.

Pestañas:
  · API & Sistema   — Gemini API key, sistema operativo
  · Hotkeys         — atajos globales
  · IoT             — puerto serial, baud rate
  · Navegador       — ruta a Chrome, perfil
  · Tema            — selector con vista previa de colores
"""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from config import (
    API_CONFIG_PATH, BROWSER_CONFIG_PATH, CONFIG_DIR, HOTKEYS_CONFIG_PATH,
    IOT_CONFIG_PATH,
)
from config.theme import list_themes, load_theme_name, save_theme_name, get_theme


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json(path: Path, data: dict) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return True
    except OSError as e:
        print(f"[Settings] Error al guardar {path}: {e}")
        return False


class _ColorSwatch(QWidget):
    """Pequeño rectángulo de color para vista previa del tema."""
    def __init__(self, hex_color: str, parent=None):
        super().__init__(parent)
        self._color = QColor(hex_color)
        self.setFixedSize(24, 16)

    def set_color(self, hex_color: str):
        self._color = QColor(hex_color)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._color)
        p.setPen(QColor(0, 0, 0, 60))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)


class SettingsPanel(QWidget):
    """Panel de configuración. Emite `theme_changed(name)` cuando cambia el tema."""

    theme_changed     = pyqtSignal(str)
    settings_changed  = pyqtSignal()

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self._theme = theme
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("O.R.I.O.N — Configuración")
        self.setMinimumSize(620, 520)
        self.resize(680, 560)
        C = theme
        self.setStyleSheet(f"background: {C.BG};")

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        hdr = QLabel("◈  CONFIGURACIÓN")
        hdr.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        hdr.setStyleSheet(
            f"color: {C.PRI}; background: transparent;"
            f" border-bottom: 1px solid {C.BORDER_B}; padding-bottom: 6px;"
        )
        root.addWidget(hdr)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(self._tabs_style(C))
        root.addWidget(self._tabs, stretch=1)

        self._tabs.addTab(self._build_api_tab(),     "🔑  API")
        self._tabs.addTab(self._build_hotkeys_tab(), "⌨  Hotkeys")
        self._tabs.addTab(self._build_iot_tab(),     "💡  IoT")
        self._tabs.addTab(self._build_browser_tab(), "🌐  Navegador")
        self._tabs.addTab(self._build_theme_tab(),   "🎨  Tema")
        self._tabs.addTab(self._build_memory_tab(),  "🧠  Memoria")

        # Footer
        footer = QHBoxLayout()
        self._status = QLabel("")
        self._status.setFont(QFont("Courier New", 8))
        self._status.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
        footer.addWidget(self._status)
        footer.addStretch()

        close = QPushButton("Cerrar")
        close.setFixedHeight(30)
        close.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet(self._btn_style(C, color=C.PRI))
        close.clicked.connect(self.close)
        footer.addWidget(close)
        root.addLayout(footer)

    # ── Estilos ────────────────────────────────────────────────────────────
    @staticmethod
    def _btn_style(C, color: str) -> str:
        return f"""
            QPushButton {{
                background: transparent; color: {color};
                border: 1px solid {C.BORDER_B}; border-radius: 4px;
                padding: 0 18px;
            }}
            QPushButton:hover {{
                background: {C.PRI_GHO}; border-color: {C.PRI};
            }}
        """

    @staticmethod
    def _input_style(C) -> str:
        return f"""
            QLineEdit, QSpinBox, QComboBox {{
                background: {C.PANEL}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 3px;
                padding: 4px 8px; font-family: 'Courier New'; font-size: 9pt;
            }}
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
                border: 1px solid {C.PRI};
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background: {C.DARK}; color: {C.TEXT};
                selection-background-color: {C.PRI_GHO};
                selection-color: {C.PRI}; border: 1px solid {C.BORDER_B};
            }}
        """

    @staticmethod
    def _tabs_style(C) -> str:
        return f"""
            QTabWidget::pane {{
                border: 1px solid {C.BORDER}; background: {C.PANEL};
                border-radius: 4px;
            }}
            QTabBar::tab {{
                background: {C.DARK}; color: {C.TEXT_MED};
                padding: 6px 14px; border: 1px solid {C.BORDER};
                border-bottom: none;
                font-family: 'Courier New'; font-size: 9pt;
            }}
            QTabBar::tab:selected {{
                background: {C.PANEL}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-bottom: 1px solid {C.PANEL};
            }}
            QTabBar::tab:hover {{ color: {C.PRI}; }}
        """

    def _label(self, txt: str, color=None) -> QLabel:
        C = self._theme
        lbl = QLabel(txt)
        lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {color or C.TEXT_MED}; background: transparent;")
        return lbl

    def _save_btn(self, on_click) -> QPushButton:
        C = self._theme
        b = QPushButton("Guardar")
        b.setFixedHeight(30)
        b.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(self._btn_style(C, color=C.GREEN))
        b.clicked.connect(on_click)
        return b

    def _show_status(self, msg: str, color=None):
        C = self._theme
        self._status.setText(msg)
        self._status.setStyleSheet(
            f"color: {color or C.GREEN}; background: transparent;"
        )

    # ── Tab: API ───────────────────────────────────────────────────────────
    def _build_api_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        cfg = _read_json(API_CONFIG_PATH)

        lay.addWidget(self._label("CLAVE API DE GEMINI"))
        self._api_key_input = QLineEdit(cfg.get("gemini_api_key", ""))
        self._api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_input.setPlaceholderText("AIza…")
        self._api_key_input.setStyleSheet(self._input_style(self._theme))
        lay.addWidget(self._api_key_input)

        show_row = QHBoxLayout()
        show_btn = QPushButton("Mostrar")
        show_btn.setFixedHeight(24)
        show_btn.setFont(QFont("Courier New", 7))
        show_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        show_btn.setStyleSheet(self._btn_style(self._theme, color=self._theme.TEXT_MED))
        show_btn.setCheckable(True)
        def _toggle_show():
            if show_btn.isChecked():
                self._api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
                show_btn.setText("Ocultar")
            else:
                self._api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
                show_btn.setText("Mostrar")
        show_btn.clicked.connect(_toggle_show)
        show_row.addWidget(show_btn)
        show_row.addStretch()
        lay.addLayout(show_row)

        lay.addSpacing(8)
        lay.addWidget(self._label("SISTEMA OPERATIVO"))
        self._os_combo = QComboBox()
        self._os_combo.addItems(["windows", "mac", "linux"])
        cur_os = cfg.get("os_system", "windows")
        idx = self._os_combo.findText(cur_os)
        if idx >= 0:
            self._os_combo.setCurrentIndex(idx)
        self._os_combo.setStyleSheet(self._input_style(self._theme))
        lay.addWidget(self._os_combo)

        lay.addStretch()
        save_row = QHBoxLayout()
        save_row.addStretch()
        save_row.addWidget(self._save_btn(self._save_api))
        lay.addLayout(save_row)
        return w

    def _save_api(self):
        key = self._api_key_input.text().strip()
        if not key:
            self._show_status("La clave no puede estar vacía", self._theme.RED)
            return
        cfg = _read_json(API_CONFIG_PATH)
        cfg["gemini_api_key"] = key
        cfg["os_system"] = self._os_combo.currentText()
        if _write_json(API_CONFIG_PATH, cfg):
            self._show_status("✓ API guardada")
            self.settings_changed.emit()
        else:
            self._show_status("Error al guardar", self._theme.RED)

    # ── Tab: Hotkeys ──────────────────────────────────────────────────────
    def _build_hotkeys_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        cfg = _read_json(HOTKEYS_CONFIG_PATH)

        defaults = {
            "toggle_microphone": "ctrl+\\",
            "show_window":       "ctrl+shift+o",
            "quit":              "ctrl+shift+q",
        }
        self._hotkey_inputs: dict[str, QLineEdit] = {}
        descriptions = {
            "toggle_microphone": "Silenciar / activar micrófono",
            "show_window":       "Mostrar la ventana de ORION",
            "quit":              "Cerrar ORION completamente",
        }
        for name, default in defaults.items():
            row = QVBoxLayout()
            row.setSpacing(2)
            row.addWidget(self._label(descriptions.get(name, name).upper()))
            inp = QLineEdit(cfg.get(name, default))
            inp.setStyleSheet(self._input_style(self._theme))
            inp.setPlaceholderText("ej. ctrl+shift+m")
            self._hotkey_inputs[name] = inp
            row.addWidget(inp)
            lay.addLayout(row)
            lay.addSpacing(4)

        info = QLabel("Sintaxis: ctrl+shift+letra · alt+letra · F1-F12")
        info.setFont(QFont("Courier New", 7))
        info.setStyleSheet(f"color: {self._theme.TEXT_DIM}; background: transparent;")
        lay.addWidget(info)

        warn = QLabel("Reinicia ORION para que los cambios tomen efecto.")
        warn.setFont(QFont("Courier New", 7))
        warn.setStyleSheet(f"color: {self._theme.ACC2}; background: transparent;")
        lay.addWidget(warn)

        lay.addStretch()
        save_row = QHBoxLayout()
        save_row.addStretch()
        save_row.addWidget(self._save_btn(self._save_hotkeys))
        lay.addLayout(save_row)
        return w

    def _save_hotkeys(self):
        data = {name: inp.text().strip() for name, inp in self._hotkey_inputs.items()}
        if _write_json(HOTKEYS_CONFIG_PATH, data):
            self._show_status("✓ Hotkeys guardadas (reinicia para aplicar)")
            self.settings_changed.emit()
        else:
            self._show_status("Error al guardar", self._theme.RED)

    # ── Tab: IoT ──────────────────────────────────────────────────────────
    def _build_iot_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        cfg = _read_json(IOT_CONFIG_PATH)

        lay.addWidget(self._label("PUERTO SERIAL (ARDUINO)"))
        self._iot_port = QLineEdit(cfg.get("serial_port", "COM1"))
        self._iot_port.setStyleSheet(self._input_style(self._theme))
        self._iot_port.setPlaceholderText("COM1 (Windows) o /dev/ttyUSB0 (Linux/Mac)")
        lay.addWidget(self._iot_port)
        lay.addSpacing(6)

        lay.addWidget(self._label("BAUD RATE"))
        self._iot_baud = QSpinBox()
        self._iot_baud.setRange(300, 1_000_000)
        self._iot_baud.setValue(int(cfg.get("baud_rate", 9600)))
        self._iot_baud.setStyleSheet(self._input_style(self._theme))
        lay.addWidget(self._iot_baud)

        lay.addSpacing(8)
        n_devices = len(cfg.get("devices", {}))
        info = QLabel(
            f"Dispositivos configurados: {n_devices}.\n"
            "Edita config/iot_config.json para añadir o eliminar dispositivos."
        )
        info.setFont(QFont("Courier New", 8))
        info.setStyleSheet(f"color: {self._theme.TEXT_DIM}; background: transparent;")
        info.setWordWrap(True)
        lay.addWidget(info)

        lay.addStretch()
        save_row = QHBoxLayout()
        save_row.addStretch()
        save_row.addWidget(self._save_btn(self._save_iot))
        lay.addLayout(save_row)
        return w

    def _save_iot(self):
        cfg = _read_json(IOT_CONFIG_PATH)
        cfg["serial_port"] = self._iot_port.text().strip() or "COM1"
        cfg["baud_rate"]   = self._iot_baud.value()
        if _write_json(IOT_CONFIG_PATH, cfg):
            self._show_status("✓ IoT guardado")
            self.settings_changed.emit()
        else:
            self._show_status("Error al guardar", self._theme.RED)

    # ── Tab: Navegador ────────────────────────────────────────────────────
    def _build_browser_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        cfg = _read_json(BROWSER_CONFIG_PATH)

        lay.addWidget(self._label("RUTA AL EJECUTABLE DE CHROME"))
        self._br_chrome = QLineEdit(cfg.get("chrome_path", ""))
        self._br_chrome.setStyleSheet(self._input_style(self._theme))
        self._br_chrome.setPlaceholderText(
            r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        )
        lay.addWidget(self._br_chrome)
        lay.addSpacing(6)

        lay.addWidget(self._label("PERFIL DE CHROME (opcional)"))
        self._br_profile = QLineEdit(cfg.get("profile_directory", ""))
        self._br_profile.setStyleSheet(self._input_style(self._theme))
        self._br_profile.setPlaceholderText("Default | Profile 1 | Profile 2…")
        lay.addWidget(self._br_profile)

        lay.addStretch()
        save_row = QHBoxLayout()
        save_row.addStretch()
        save_row.addWidget(self._save_btn(self._save_browser))
        lay.addLayout(save_row)
        return w

    def _save_browser(self):
        cfg = _read_json(BROWSER_CONFIG_PATH)
        cfg["chrome_path"]       = self._br_chrome.text().strip()
        cfg["profile_directory"] = self._br_profile.text().strip()
        cfg["use_direct_chrome"] = bool(cfg["chrome_path"])
        if _write_json(BROWSER_CONFIG_PATH, cfg):
            self._show_status("✓ Navegador guardado")
            self.settings_changed.emit()
        else:
            self._show_status("Error al guardar", self._theme.RED)

    # ── Tab: Tema ─────────────────────────────────────────────────────────
    def _build_theme_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        lay.addWidget(self._label("TEMA ACTIVO"))
        self._theme_combo = QComboBox()
        themes = list_themes()
        for tid, tname in themes:
            self._theme_combo.addItem(tname, tid)
        cur = load_theme_name()
        for i in range(self._theme_combo.count()):
            if self._theme_combo.itemData(i) == cur:
                self._theme_combo.setCurrentIndex(i)
                break
        self._theme_combo.setStyleSheet(self._input_style(self._theme))
        self._theme_combo.currentIndexChanged.connect(self._refresh_swatches)
        lay.addWidget(self._theme_combo)

        # Vista previa: paleta de colores principales
        lay.addSpacing(8)
        lay.addWidget(self._label("VISTA PREVIA"))
        self._swatch_row = QHBoxLayout()
        self._swatch_row.setSpacing(4)
        self._swatch_widgets: list[tuple[QLabel, _ColorSwatch]] = []
        keys_to_show = [
            ("PRI",   "Primario"),
            ("ACC",   "Acento"),
            ("ACC2",  "Acento 2"),
            ("GREEN", "Verde"),
            ("RED",   "Rojo"),
            ("TEXT",  "Texto"),
        ]
        for color_key, _ in keys_to_show:
            box = QVBoxLayout()
            box.setSpacing(2)
            sw = _ColorSwatch("#000000")
            lbl = QLabel(color_key)
            lbl.setFont(QFont("Courier New", 7))
            lbl.setStyleSheet(
                f"color: {self._theme.TEXT_DIM}; background: transparent;"
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(sw, alignment=Qt.AlignmentFlag.AlignCenter)
            box.addWidget(lbl)
            self._swatch_row.addLayout(box)
            self._swatch_widgets.append((lbl, sw))
        self._swatch_keys = keys_to_show
        lay.addLayout(self._swatch_row)
        self._refresh_swatches()

        warn = QLabel("Reinicia ORION para aplicar el tema completo.")
        warn.setFont(QFont("Courier New", 7))
        warn.setStyleSheet(f"color: {self._theme.ACC2}; background: transparent;")
        lay.addSpacing(8)
        lay.addWidget(warn)

        lay.addStretch()
        save_row = QHBoxLayout()
        save_row.addStretch()
        save_row.addWidget(self._save_btn(self._save_theme))
        lay.addLayout(save_row)
        return w

    def _refresh_swatches(self):
        tid = self._theme_combo.currentData()
        if not tid:
            return
        th = get_theme(tid)
        for (lbl, sw), (key, _) in zip(self._swatch_widgets, self._swatch_keys):
            sw.set_color(th.get(key, "#000000"))

    def _save_theme(self):
        tid = self._theme_combo.currentData()
        if not tid:
            return
        save_theme_name(tid)
        self.theme_changed.emit(tid)
        self._show_status("✓ Tema guardado (reinicia para aplicar)")

    # ── Tab: Memoria ──────────────────────────────────────────────────────
    def _build_memory_tab(self) -> QWidget:
        from ui_components.memory_panel import MemoryPanel
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(0)
        self._memory_panel = MemoryPanel(theme=self._theme, embedded=True)
        self._memory_panel.memory_changed.connect(
            lambda: self.settings_changed.emit()
        )
        lay.addWidget(self._memory_panel)
        return w
