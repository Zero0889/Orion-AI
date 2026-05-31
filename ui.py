from __future__ import annotations

import json
import locale
import math
import os
import platform
import random
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import psutil

from PyQt6.QtCore import (
    QEasingCurve, QMimeData, QObject, QPoint, QPointF, QRectF, QSize, Qt,
    QTimer, QUrl, pyqtSignal,
)
from PyQt6.QtGui import (
    QAction, QActionGroup, QBrush, QColor, QDragEnterEvent, QDropEvent, QFont,
    QFontDatabase, QIcon, QKeySequence, QLinearGradient, QPainter,
    QPainterPath, QPen, QPixmap, QRadialGradient, QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMenu, QPushButton, QScrollArea, QSizePolicy,
    QSystemTrayIcon, QTextEdit, QVBoxLayout, QWidget, QProgressBar,
)

import keyboard

from config.theme import (
    get_theme, list_themes, load_theme_name, save_theme_name,
)
from config import BASE_DIR
from ui_components.chat_panel import ChatPanel
from ui_components.history_panel import HistoryPanel
from ui_components.settings_panel import SettingsPanel
from ui_components.onboarding import OnboardingWizard
from ui_components.notes_panel import NotesPanel
from ui_components.sidebar import (
    SIDEBAR_WIDTH_EXPANDED, SidebarPanel, SidebarTrigger,
)
from memory.conversations import ConversationSession, get_conversation

GITHUB_URL  = "https://github.com/Zero0889/O.R.I.O.N---IA"
GITHUB_ICON = BASE_DIR / "assets" / "github-logo.png"


# ============================================================
#  Botón GitHub (imagen PNG, clickeable)
# ============================================================
class GitHubButton(QPushButton):
    """Botón pequeño que muestra el logo de GitHub y abre la URL del repo."""

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url
        self.setFixedSize(30, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"Ver código fuente · {url}")
        self.setFlat(True)
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")

        # Cargar el logo desde assets
        self._pixmap: QPixmap | None = None
        if GITHUB_ICON.exists():
            px = QPixmap(str(GITHUB_ICON))
            if not px.isNull():
                # Escalar suavemente al tamaño del botón
                self._pixmap = px.scaled(
                    22, 22,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )

        self._hover = False
        self.clicked.connect(self._open_url)

    def _open_url(self):
        try:
            webbrowser.open(self._url)
        except Exception:
            pass

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        r = min(W, H) * 0.46

        # Círculo de fondo (con un brillo del tema en hover)
        if self._hover:
            p.setBrush(QBrush(qcol(C.PRI, 70)))
            p.setPen(QPen(qcol(C.PRI), 1.5))
        else:
            p.setBrush(QBrush(qcol(C.PANEL2)))
            p.setPen(QPen(qcol(C.BORDER_B), 1))
        p.drawEllipse(QPointF(cx, cy), r, r)

        # Dibujar el PNG centrado
        if self._pixmap is not None:
            pw, ph = self._pixmap.width(), self._pixmap.height()
            x = int(cx - pw / 2)
            y = int(cy - ph / 2)
            p.drawPixmap(x, y, self._pixmap)
        else:
            # Fallback: texto si la imagen no existe
            p.setPen(QPen(qcol(C.WHITE), 1))
            p.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "GH")

# ============================================================
#  Configuración base / rutas
# ============================================================
def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR      = _base_dir()
CONFIG_DIR    = BASE_DIR / "config"
API_FILE      = CONFIG_DIR / "api_keys.json"
HOTKEYS_FILE  = CONFIG_DIR / "hotkeys.json"
TRAY_ICON_PATH = Path(os.environ.get("USERPROFILE", "")) / "Downloads" / "Gemini_Generated_Image_g9g7adg9g7adg9g7.ico"


def _load_hotkeys() -> dict:
    defaults = {
        "toggle_microphone": "ctrl+\\",
        "show_window": "ctrl+shift+o",
        "quit": "ctrl+shift+q",
    }
    try:
        with open(HOTKEYS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        defaults.update(data)
    except Exception:
        pass
    return defaults

_DEFAULT_W, _DEFAULT_H = 1080, 740
_MIN_W,     _MIN_H     = 900, 600
_LEFT_W  = 148
_RIGHT_W = 440  # Incrementado ligeramente para un mejor ratio de lectura del chat

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"

# Intentar fijar locale español para el calendario
for _loc in ("es_ES.UTF-8", "es_ES", "Spanish_Spain.1252", "es"):
    try:
        locale.setlocale(locale.LC_TIME, _loc)
        break
    except locale.Error:
        continue

# Días y meses en español (fallback si el locale no está disponible)
_DIAS_ES   = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
_MESES_ES  = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
              "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


# ============================================================
#  Paleta de colores — cargada desde config/theme.json
# ============================================================
_ACTIVE_THEME = get_theme()


class C:
    """Paleta de colores. Valores cargados del tema activo al iniciar."""
    BG        = _ACTIVE_THEME["BG"]
    PANEL     = _ACTIVE_THEME["PANEL"]
    PANEL2    = _ACTIVE_THEME["PANEL2"]
    DARK      = _ACTIVE_THEME["DARK"]
    BORDER    = _ACTIVE_THEME["BORDER"]
    BORDER_B  = _ACTIVE_THEME["BORDER_B"]
    BORDER_A  = _ACTIVE_THEME["BORDER_A"]
    PRI       = _ACTIVE_THEME["PRI"]
    PRI_DIM   = _ACTIVE_THEME["PRI_DIM"]
    PRI_GHO   = _ACTIVE_THEME["PRI_GHO"]
    ACC       = _ACTIVE_THEME["ACC"]
    ACC2      = _ACTIVE_THEME["ACC2"]
    GREEN     = _ACTIVE_THEME["GREEN"]
    GREEN_D   = _ACTIVE_THEME["GREEN_D"]
    RED       = _ACTIVE_THEME["RED"]
    MUTED_C   = _ACTIVE_THEME["MUTED_C"]
    TEXT      = _ACTIVE_THEME["TEXT"]
    TEXT_DIM  = _ACTIVE_THEME["TEXT_DIM"]
    TEXT_MED  = _ACTIVE_THEME["TEXT_MED"]
    WHITE     = _ACTIVE_THEME["WHITE"]
    BAR_BG    = _ACTIVE_THEME["BAR_BG"]
    # Paletas del orb 3D (RGB tuples)
    ORB_ACTIVE = _ACTIVE_THEME["ORB_ACTIVE"]
    ORB_MUTED  = _ACTIVE_THEME["ORB_MUTED"]
    # Colores derivados con fallback
    BG_GLOW   = _ACTIVE_THEME.get("BG_GLOW",   _ACTIVE_THEME["PRI_GHO"])
    BG_DARK   = _ACTIVE_THEME.get("BG_DARK",   _ACTIVE_THEME["DARK"])
    DROP_HOVER= _ACTIVE_THEME.get("DROP_HOVER", _ACTIVE_THEME["PRI_GHO"])
    DROP_OVER = _ACTIVE_THEME.get("DROP_OVER",  _ACTIVE_THEME["BAR_BG"])
    TEMP_C    = _ACTIVE_THEME.get("TEMP_C",      _ACTIVE_THEME["RED"])
    MUTE_BTN_BG  = _ACTIVE_THEME.get("MUTE_BTN_BG",  _ACTIVE_THEME["RED"])
    MUTE_BTN_HOV = _ACTIVE_THEME.get("MUTE_BTN_HOV", _ACTIVE_THEME["PRI_DIM"])
    BTN_BG_ERR   = _ACTIVE_THEME.get("BTN_BG_ERR",   _ACTIVE_THEME["BAR_BG"])
    BTN_BG_ERR_H = _ACTIVE_THEME.get("BTN_BG_ERR_H", _ACTIVE_THEME["PRI_GHO"])
    BTN_BG_OK    = _ACTIVE_THEME.get("BTN_BG_OK",    "#04140a")
    BTN_BG_OK_H  = _ACTIVE_THEME.get("BTN_BG_OK_H",  "#061f10")


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h); c.setAlpha(a); return c


# ============================================================
#  Métricas del sistema (CPU, RAM, GPU, RED, TEMP)
# ============================================================
class _SysMetrics:
    def __init__(self):
        self.cpu  = 0.0
        self.mem  = 0.0
        self.net = 0.0
        self.gpu  = -1.0
        self.tmp  = -1.0
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(1.5)

    def _update(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent

        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = now - self._last_net_t
        if dt > 0:
            sent = (nc.bytes_sent - self._last_net.bytes_sent) / dt
            recv = (nc.bytes_recv - self._last_net.bytes_recv) / dt
            net  = (sent + recv) / (1024 * 1024)
        else:
            net = 0.0
        self._last_net   = nc
        self._last_net_t = now

        gpu = self._get_gpu()
        tmp = self._get_temp()

        with self._lock:
            self.cpu = cpu
            self.mem = mem
            self.net = net
            self.gpu = gpu
            self.tmp = tmp

    def _get_gpu(self) -> float:
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2
            )
            if r.returncode == 0:
                vals = [float(v.strip()) for v in r.stdout.strip().split("\n") if v.strip()]
                if vals:
                    return sum(vals) / len(vals)
        except Exception:
            pass

        if _OS == "Linux":
            try:
                r = subprocess.run(
                    ["rocm-smi", "--showuse", "--csv"],
                    capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0:
                    for line in r.stdout.strip().split("\n"):
                        parts = line.split(",")
                        if len(parts) >= 2:
                            try:
                                return float(parts[1].strip().replace("%", ""))
                            except ValueError:
                                pass
            except Exception:
                pass

            try:
                r = subprocess.run(
                    ["intel_gpu_top", "-J", "-s", "500"],
                    capture_output=True, text=True, timeout=1
                )
                if r.returncode == 0 and "Render/3D" in r.stdout:
                    import re
                    m = re.search(r'"busy":\s*([\d.]+)', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["sudo", "-n", "powermetrics", "-n", "1", "-i", "500",
                     "--samplers", "gpu_power"],
                    capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0 and "GPU" in r.stdout:
                    import re
                    m = re.search(r'GPU\s+Active:\s+([\d.]+)%', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        return -1.0

    def _get_temp(self) -> float:
        try:
            temps = psutil.sensors_temperatures()
            candidates = ["coretemp", "k10temp", "cpu_thermal", "acpitz",
                          "cpu-thermal", "zenpower", "it8688"]
            for name in candidates:
                if name in temps:
                    entries = temps[name]
                    if entries:
                        return entries[0].current
            for entries in temps.values():
                if entries:
                    return entries[0].current
        except Exception:
            pass

        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["osx-cpu-temp"], capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0:
                    import re
                    m = re.search(r"([\d.]+)", r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        if _OS == "Windows":
            try:
                r = subprocess.run(
                    ["powershell", "-Command",
                     "(Get-WmiObject MSAcpi_ThermalZoneTemperature -Namespace root/wmi).CurrentTemperature"],
                    capture_output=True, text=True, timeout=3
                )
                if r.returncode == 0 and r.stdout.strip():
                    raw = float(r.stdout.strip().split("\n")[0])
                    return (raw / 10.0) - 273.15
            except Exception:
                pass

        return -1.0

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cpu": self.cpu,
                "mem": self.mem,
                "net": self.net,
                "gpu": self.gpu,
                "tmp": self.tmp,
            }


_metrics = _SysMetrics()


# ============================================================
#  HUD central (rostro/orbe animado)
# ============================================================
class HudCanvas(QWidget):
    def __init__(self, face_path: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted    = False
        self.speaking = False
        self.state    = "INICIALIZANDO"
        self._paused  = False

        self._tick       = 0
        self._scale      = 1.0
        self._tgt_scale  = 1.0
        self._halo       = 55.0
        self._tgt_halo   = 55.0
        self._last_t     = time.time()
        self._scan       = 0.0
        self._scan2      = 180.0
        self._rings      = [0.0, 120.0, 240.0]
        self._pulses: list[float] = [0.0, 50.0, 100.0]
        self._blink      = True
        self._blink_tick = 0
        self._particles: list[list[float]] = []
        self._face_px: QPixmap | None = None
        self._load_face(face_path)

        # Esfera de partículas (Mantenida por requerimiento explícito)
        self._orb_particles: list[dict] = []
        N_ORB = 140
        for _ in range(N_ORB):
            self._orb_particles.append({
                "theta":      random.uniform(0, 2 * math.pi),
                "phi":        math.acos(2 * random.random() - 1),
                "spd_theta":  random.uniform(0.005, 0.020),
                "spd_phi":    random.uniform(0.002, 0.010),
                "base_size":  random.uniform(1.6, 3.4),
                "pulse_t":    random.uniform(0, 100),
                "pulse_spd":  random.uniform(0.02, 0.07),
                "color_idx":  random.randint(0, 3),
            })
        self._orb_rot_x   = 0.0
        self._orb_rot_y   = 0.0
        self._orb_speed   = 0.18
        self._orb_tgt_spd = 0.18

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(16)

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        if paused:
            self._tmr.stop()
        elif not self._tmr.isActive():
            self._tmr.start(16)

    def _load_face(self, path: str):
        try:
            from PIL import Image, ImageDraw
            import io
            img = Image.open(path).convert("RGBA")
            sz  = min(img.size)
            img = img.resize((sz, sz), Image.LANCZOS)
            mk  = Image.new("L", (sz, sz), 0)
            ImageDraw.Draw(mk).ellipse((2, 2, sz - 2, sz - 2), fill=255)
            img.putalpha(mk)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            px = QPixmap(); px.loadFromData(buf.getvalue())
            self._face_px = px
        except Exception:
            self._face_px = None

    def _step(self):
        self._tick += 1
        now = time.time()
        if now - self._last_t > (0.12 if self.speaking else 0.5):
            if self.speaking:
                self._tgt_scale = random.uniform(1.06, 1.14)
                self._tgt_halo  = random.uniform(145, 190)
            elif self.muted:
                self._tgt_scale = random.uniform(0.998, 1.002)
                self._tgt_halo  = random.uniform(15, 28)
            else:
                self._tgt_scale = random.uniform(1.001, 1.008)
                self._tgt_halo  = random.uniform(48, 68)
            self._last_t = now

        sp = 0.38 if self.speaking else 0.15
        self._scale += (self._tgt_scale - self._scale) * sp
        self._halo  += (self._tgt_halo  - self._halo)  * sp

        speeds = [1.3, -0.9, 2.0] if self.speaking else [0.55, -0.35, 0.9]
        for i, spd in enumerate(speeds):
            self._rings[i] = (self._rings[i] + spd) % 360

        self._scan  = (self._scan  + (3.0 if self.speaking else 1.3)) % 360
        self._scan2 = (self._scan2 + (-2.0 if self.speaking else -0.75)) % 360

        fw  = min(self.width(), self.height())
        lim = fw * 0.74
        spd = 4.2 if self.speaking else 2.0
        self._pulses = [r + spd for r in self._pulses if r + spd < lim]
        if len(self._pulses) < 3 and random.random() < (0.07 if self.speaking else 0.025):
            self._pulses.append(0.0)

        if self.speaking and random.random() < 0.28:
            cx, cy = self.width() / 2, self.height() / 2
            ang = random.uniform(0, 2 * math.pi)
            r_s = fw * 0.28
            self._particles.append([
                cx + math.cos(ang) * r_s, cy + math.sin(ang) * r_s,
                math.cos(ang) * random.uniform(0.9, 2.4),
                math.sin(ang) * random.uniform(0.9, 2.4) - 0.4, 1.0,
            ])
        self._particles = [
            [p[0]+p[2], p[1]+p[3], p[2]*0.97, p[3]*0.97, p[4]-0.028]
            for p in self._particles if p[4] > 0
        ]

        self._blink_tick += 1
        if self._blink_tick >= 38:
            self._blink = not self._blink
            self._blink_tick = 0

        if self.state == "PENSANDO" or self.state == "PROCESANDO":
            self._orb_tgt_spd = 2.8
        elif self.speaking:
            self._orb_tgt_spd = 1.5
        elif self.muted:
            self._orb_tgt_spd = 0.08
        else:
            self._orb_tgt_spd = 0.35

        self._orb_speed += (self._orb_tgt_spd - self._orb_speed) * 0.08
        self._orb_rot_x += 0.004 * self._orb_speed * 2.5
        self._orb_rot_y += 0.006 * self._orb_speed * 2.5

        for op in self._orb_particles:
            op["theta"]   += op["spd_theta"] * self._orb_speed * 3.0
            op["phi"]     += op["spd_phi"]   * self._orb_speed * 1.5
            op["pulse_t"] += op["pulse_spd"]

        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        rg = QRadialGradient(cx, cy, max(W, H) * 0.65)
        rg.setColorAt(0.0, qcol(C.BG_GLOW))
        rg.setColorAt(0.55, qcol(C.BG))
        rg.setColorAt(1.0, qcol(C.BG_DARK))
        p.fillRect(self.rect(), QBrush(rg))

        fw = min(W, H)

        p.setPen(QPen(qcol(C.PRI_GHO), 1))
        for x in range(0, W, 48):
            for y in range(0, H, 48):
                p.drawPoint(x, y)

        r_face = fw * 0.31

        for i in range(10):
            r   = r_face * (1.8 - i * 0.08)
            frc = 1.0 - i / 10
            a   = max(0, min(255, int(self._halo * 0.085 * frc)))
            col = qcol(C.MUTED_C if self.muted else C.PRI, a)
            p.setPen(QPen(col, 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        for pr in self._pulses:
            a   = max(0, int(230 * (1.0 - pr / (fw * 0.74))))
            col = qcol(C.MUTED_C if self.muted else C.PRI, a)
            p.setPen(QPen(col, 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - pr, cy - pr, pr * 2, pr * 2))

        for idx, (r_frac, w_r, arc_l, gap) in enumerate(
            [(0.48, 3, 115, 78), (0.40, 2, 78, 55), (0.32, 1, 56, 40)]
        ):
            ring_r = fw * r_frac
            base   = self._rings[idx]
            a_val  = max(0, min(255, int(self._halo * (1.0 - idx * 0.18))))
            col    = qcol(C.MUTED_C if self.muted else C.PRI, a_val)
            p.setPen(QPen(col, w_r)); p.setBrush(Qt.BrushStyle.NoBrush)
            angle = base
            rect  = QRectF(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)
            while angle < base + 360:
                p.drawArc(rect, int(angle * 16), int(arc_l * 16))
                angle += arc_l + gap

        sr = fw * 0.50
        sa = min(255, int(self._halo * 1.5))
        ex = 75 if self.speaking else 44
        p.setPen(QPen(qcol(C.MUTED_C if self.muted else C.PRI, sa), 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        srect = QRectF(cx - sr, cy - sr, sr * 2, sr * 2)
        p.drawArc(srect, int(self._scan * 16), int(ex * 16))
        p.setPen(QPen(qcol(C.ACC, sa // 2), 1.5))
        p.drawArc(srect, int(self._scan2 * 16), int(ex * 16))

        t_out, t_in = fw * 0.497, fw * 0.474
        p.setPen(QPen(qcol(C.PRI, 140), 1))
        for deg in range(0, 360, 10):
            rad = math.radians(deg)
            inn = t_in if deg % 30 == 0 else t_in + 6
            p.drawLine(
                QPointF(cx + t_out * math.cos(rad), cy - t_out * math.sin(rad)),
                QPointF(cx + inn  * math.cos(rad), cy - inn  * math.sin(rad)),
            )

        ch_r, gap_h = fw * 0.51, fw * 0.16
        p.setPen(QPen(qcol(C.PRI, int(self._halo * 0.5)), 1))
        p.drawLine(QPointF(cx - ch_r, cy), QPointF(cx - gap_h, cy))
        p.drawLine(QPointF(cx + gap_h, cy), QPointF(cx + ch_r, cy))
        p.drawLine(QPointF(cx, cy - ch_r), QPointF(cx, cy - gap_h))
        p.drawLine(QPointF(cx, cy + gap_h), QPointF(cx, cy + ch_r))

        bl = 24
        bc = qcol(C.PRI, 210)
        hl, hr = cx - fw // 2, cx + fw // 2
        ht, hb = cy - fw // 2, cy + fw // 2
        p.setPen(QPen(bc, 2))
        for bx, by, dx, dy in [(hl,ht,1,1),(hr,ht,-1,1),(hl,hb,1,-1),(hr,hb,-1,-1)]:
            p.drawLine(QPointF(bx, by), QPointF(bx + dx * bl, by))
            p.drawLine(QPointF(bx, by), QPointF(bx, by + dy * bl))

        orb_colors = C.ORB_MUTED if self.muted else C.ORB_ACTIVE
        halo_rgb = orb_colors[0]
        orb_radius = fw * 0.22 * self._scale
        cos_y = math.cos(self._orb_rot_y); sin_y = math.sin(self._orb_rot_y)
        cos_x = math.cos(self._orb_rot_x); sin_x = math.sin(self._orb_rot_x)

        halo_r = orb_radius * 1.05
        halo_gr = QRadialGradient(QPointF(cx, cy), halo_r)
        halo_gr.setColorAt(0.0, QColor(halo_rgb[0], halo_rgb[1], halo_rgb[2], 110 if not self.muted else 90))
        halo_gr.setColorAt(0.55, QColor(halo_rgb[0], halo_rgb[1], halo_rgb[2], 40))
        halo_gr.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(halo_gr)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), halo_r, halo_r)

        rendered: list[tuple[float, float, float, float, float, tuple]] = []
        for op in self._orb_particles:
            theta = op["theta"]; phi = op["phi"]
            x3 = orb_radius * math.sin(phi) * math.cos(theta)
            y3 = orb_radius * math.sin(phi) * math.sin(theta)
            z3 = orb_radius * math.cos(phi)

            xR = x3 * cos_y - z3 * sin_y
            zR = x3 * sin_y + z3 * cos_y
            yR = y3 * cos_x - zR * sin_x
            zF = y3 * sin_x + zR * cos_x

            depth = (zF + orb_radius) / (orb_radius * 2)
            depth = max(0.0, min(1.0, depth))

            size  = (op["base_size"] + math.sin(op["pulse_t"]) * 0.5) * (0.4 + depth * 1.2)
            alpha = 0.15 + depth * 0.85
            col   = orb_colors[op["color_idx"]]

            rendered.append((cx + xR, cy + yR, zF, size, alpha, col))

        rendered.sort(key=lambda t: t[2])

        for x, y, z, size, alpha, col in rendered:
            glow_r = size * 4.0
            gr = QRadialGradient(QPointF(x, y), glow_r)
            gr.setColorAt(0.0, QColor(col[0], col[1], col[2], int(alpha * 200)))
            gr.setColorAt(0.35, QColor(col[0], col[1], col[2], int(alpha * 60)))
            gr.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setBrush(QBrush(gr)); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x, y), glow_r, glow_r)

            core_a = int(min(255, alpha * 230))
            core_qcol = QColor(C.WHITE)
            core_qcol.setAlpha(core_a)
            p.setBrush(QBrush(core_qcol))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x, y), size, size)

        for pt in self._particles:
            a = max(0, min(255, int(pt[4] * 255)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(qcol(C.PRI, a)))
            p.drawEllipse(QPointF(pt[0], pt[1]), 2.5, 2.5)

        sy = cy + fw * 0.40
        if self.muted:
            txt, col = "⊘  SILENCIADO",     qcol(C.MUTED_C)
        elif self.speaking:
            txt, col = "●  HABLANDO",       qcol(C.ACC)
        elif self.state == "PENSANDO":
            sym = "◈" if self._blink else "◇"
            txt, col = f"{sym}  PENSANDO",   qcol(C.ACC2)
        elif self.state == "PROCESANDO":
            sym = "▷" if self._blink else "▶"
            txt, col = f"{sym}  PROCESANDO", qcol(C.ACC2)
        elif self.state == "ESCUCHANDO":
            sym = "●" if self._blink else "○"
            txt, col = f"{sym}  ESCUCHANDO", qcol(C.GREEN)
        else:
            sym = "●" if self._blink else "○"
            txt, col = f"{sym}  {self.state}", qcol(C.PRI)

        p.setPen(QPen(col, 1))
        p.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        p.drawText(QRectF(0, sy, W, 26), Qt.AlignmentFlag.AlignCenter, txt)

        wy = sy + 30
        N, bw = 36, 8
        wx0 = (W - N * bw) / 2
        for i in range(N):
            if self.muted:
                hgt, cl = 2, qcol(C.MUTED_C)
            elif self.speaking:
                hgt = random.randint(3, 20)
                cl  = qcol(C.PRI) if hgt > 12 else qcol(C.PRI_DIM)
            else:
                hgt = int(3 + 2 * math.sin(self._tick * 0.09 + i * 0.6))
                cl  = qcol(C.BORDER_B)
            p.fillRect(QRectF(wx0 + i * bw, wy + 20 - hgt, bw - 1, hgt), cl)


# ============================================================
#  Barra de métrica individual (CPU, MEM, etc.)
# ============================================================
class MetricBar(QWidget):
    def __init__(self, label: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._value = 0.0
        self._text  = "--"
        self.setFixedHeight(40)
        self.setMinimumWidth(80)

    def set_value(self, pct: float, text: str):
        self._value = max(0.0, min(100.0, pct))
        self._text  = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        grad = QLinearGradient(0, 0, 0, H)
        grad.setColorAt(0.0, qcol(C.PANEL2))
        grad.setColorAt(1.0, qcol(C.PANEL))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(qcol(C.BORDER_A), 1))
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 5, 5)

        bar_h   = 5
        bar_y   = H - bar_h - 6
        bar_w   = W - 14
        bar_x   = 7
        fill_w  = int(bar_w * self._value / 100)

        p.setBrush(QBrush(qcol(C.BAR_BG)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 2, 2)

        if self._value > 85:
            bar_col = qcol(C.RED)
        elif self._value > 65:
            bar_col = qcol(C.ACC)
        else:
            bar_col = qcol(self._color)

        if fill_w > 0:
            gb = QLinearGradient(bar_x, 0, bar_x + fill_w, 0)
            gb.setColorAt(0.0, bar_col)
            light = QColor(bar_col); light.setAlpha(180)
            gb.setColorAt(1.0, light)
            p.setBrush(QBrush(gb))
            p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 2, 2)

        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_MED), 1))
        p.drawText(QRectF(9, 5, 60, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._label)

        p.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        p.setPen(QPen(bar_col if self._text != "--" else qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, 4, W - 8, 16),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._text)


# ============================================================
#  Widget de log con efecto máquina de escribir
# ============================================================
class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)
    dropped_text = pyqtSignal(str)
    dropped_file = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setAcceptDrops(True)
        self.setFont(QFont("Courier New", 9))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C.PANEL};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 6px;
                padding: 10px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG};
                width: 6px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {C.PRI_DIM};
            }}
        """)
        self._queue: list[str] = []
        self._typing  = False
        self._text    = ""
        self._pos     = 0
        self._tag     = "sys"
        self.document().setMaximumBlockCount(500)
        self._max_queue = 200
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._sig.connect(self._enqueue)

    def append_log(self, text: str):
        self._sig.emit(text)

    def _enqueue(self, text: str):
        if len(self._queue) >= self._max_queue:
            self._queue = self._queue[-(self._max_queue - 1):]
        self._queue.append(text)
        if not self._typing:
            self._next()

    def _next(self):
        if not self._queue:
            self._typing = False
            return
        self._typing = True
        self._text    = self._queue.pop(0)
        self._pos     = 0
        tl = self._text.lower()
        if   tl.startswith("tú:") or tl.startswith("tu:"): self._tag = "you"
        elif tl.startswith("orion:"):                       self._tag = "ai"
        elif tl.startswith("archivo:"):                     self._tag = "file"
        elif tl.startswith("sistema:") or tl.startswith("sys:"): self._tag = "sys"
        elif "error" in tl or "err" in tl:                  self._tag = "err"
        else:                                               self._tag = "sys"
        if len(self._queue) > 5:
            self._flush_instant()
        else:
            self._tmr.start(6)

    def _flush_instant(self):
        cur = self.textCursor()
        fmt = cur.charFormat()
        col = {
            "you":  qcol(C.WHITE),
            "ai":    qcol(C.PRI),
            "err":  qcol(C.RED),
            "file": qcol(C.GREEN),
            "sys":  qcol(C.ACC2),
        }.get(self._tag, qcol(C.TEXT))
        fmt.setForeground(QBrush(col))
        cur.movePosition(cur.MoveOperation.End)
        cur.insertText(self._text + "\n", fmt)
        self.setTextCursor(cur)
        self.ensureCursorVisible()
        self._pos = len(self._text)
        QTimer.singleShot(5, self._next)

    def _step(self):
        if self._pos < len(self._text):
            ch  = self._text[self._pos]
            cur = self.textCursor()
            fmt = cur.charFormat()
            col = {
                "you":  qcol(C.WHITE),
                "ai":    qcol(C.PRI),
                "err":  qcol(C.RED),
                "file": qcol(C.GREEN),
                "sys":  qcol(C.ACC2),
            }.get(self._tag, qcol(C.TEXT))
            fmt.setForeground(QBrush(col))
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText(ch, fmt)
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            self._pos += 1
        else:
            self._tmr.stop()
            cur = self.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText("\n")
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            QTimer.singleShot(20, self._next)

    def dragEnterEvent(self, e):
        mime = e.mimeData()
        if mime.hasUrls() or mime.hasText() or mime.hasImage():
            e.acceptProposedAction()
            self.setStyleSheet(self.styleSheet() + f"\nQTextEdit {{ border: 1px solid {C.PRI}; }}")
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        self._reset_border()
        super().dragLeaveEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasText():
            e.acceptProposedAction()

    def _reset_border(self):
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C.PANEL};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 6px;
                padding: 10px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG};
                width: 6px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {C.PRI_DIM};
            }}
        """)

    def dropEvent(self, e):
        mime = e.mimeData()
        self._reset_border()

        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    if Path(path).is_file():
                        self.dropped_file.emit(path)
                        e.acceptProposedAction()
                        return
                if url.scheme() in ("http", "https"):
                    self.dropped_text.emit(url.toString())
                    e.acceptProposedAction()
                    return

        if mime.hasText():
            text = mime.text().strip()
            if text:
                self.dropped_text.emit(text)
                e.acceptProposedAction()
                return

        e.ignore()


# ============================================================
#  Iconos por categoría de archivo
# ============================================================
_FILE_ICONS = {
    "image":   ("🖼", "#ff4d6e"), "video":   ("🎬", "#ff6b1a"),
    "audio":   ("🎵", "#cc44ff"), "pdf":     ("📄", "#ff4444"),
    "word":    ("📝", "#4488ff"), "excel":   ("📊", "#44bb44"),
    "code":    ("💻", "#ffb84d"), "archive": ("📦", "#ff8844"),
    "pptx":    ("📊", "#ff6622"), "text":    ("📃", "#cc9999"),
    "data":    ("🔧", "#ff88aa"), "unknown": ("📎", "#aa8888"),
}
_EXT_TO_CAT = {
    **dict.fromkeys(["jpg","jpeg","png","gif","webp","bmp","tiff","svg","ico"], "image"),
    **dict.fromkeys(["mp4","avi","mov","mkv","wmv","flv","webm","m4v"],         "video"),
    **dict.fromkeys(["mp3","wav","ogg","m4a","aac","flac","wma","opus"],        "audio"),
    **dict.fromkeys(["pdf"],                                                     "pdf"),
    **dict.fromkeys(["doc","docx"],                                              "word"),
    **dict.fromkeys(["xls","xlsx","ods"],                                        "excel"),
    **dict.fromkeys(["ppt","pptx"],                                              "pptx"),
    **dict.fromkeys(["py","js","ts","jsx","tsx","html","css","java","c","cpp",
                     "cs","go","rs","rb","php","swift","kt","sh","sql","lua"],   "code"),
    **dict.fromkeys(["zip","rar","tar","gz","7z","bz2","xz"],                   "archive"),
    **dict.fromkeys(["txt","md","rst","log"],                                    "text"),
    **dict.fromkeys(["csv","tsv","json","xml"],                                  "data"),
}

def _file_category(path: Path) -> str:
    return _EXT_TO_CAT.get(path.suffix.lower().lstrip("."), "unknown")

def _fmt_size(size: int) -> str:
    if   size < 1024:    return f"{size} B"
    elif size < 1024**2: return f"{size/1024:.1f} KB"
    elif size < 1024**3: return f"{size/1024**2:.1f} MB"
    else:                return f"{size/1024**3:.1f} GB"


# ============================================================
#  Zona de arrastrar y soltar
# ============================================================
class FileDropZone(QWidget):
    file_selected  = pyqtSignal(str)
    files_selected = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(90)  # Compactado sutilmente para balancear pesos
        self._current_file: str | None = None
        self._current_files: list[str] = []
        self._hovering  = False
        self._drag_over = False
        self._dash_offset = 0.0
        self._anim_tmr = QTimer(self)
        self._anim_tmr.timeout.connect(self._animate)
        self._anim_tmr.start(40)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._canvas = _DropCanvas(self)
        layout.addWidget(self._canvas)

    def _animate(self):
        self._dash_offset = (self._dash_offset + 0.8) % 20
        self._canvas.update()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drag_over = True; self._canvas.update()

    def dragLeaveEvent(self, e):
        self._drag_over = False; self._canvas.update()

    def dropEvent(self, e: QDropEvent):
        self._drag_over = False
        urls = e.mimeData().urls()
        paths: list[str] = []
        for url in urls:
            p = url.toLocalFile()
            if p and Path(p).is_file():
                paths.append(p)
        if paths:
            self._set_files(paths)
        self._canvas.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._browse()

    def enterEvent(self, e):
        self._hovering = True; self._canvas.update()

    def leaveEvent(self, e):
        self._hovering = False; self._canvas.update()

    def current_file(self) -> str | None:
        return self._current_file

    def current_files(self) -> list[str]:
        return list(self._current_files)

    def clear_file(self):
        self._current_file = None
        self._current_files = []
        self._canvas.update()

    def _browse(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Seleccionar archivo(s) para ORION", str(Path.home()),
            "Todos los archivos (*.*);;"
            "Imágenes (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documentos (*.pdf *.docx *.txt *.md *.pptx);;"
            "Datos (*.csv *.xlsx *.json *.xml);;"
            "Código (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archivos comprimidos (*.zip *.rar *.tar *.gz *.7z)",
        )
        if paths:
            self._set_files(paths)

    def _set_file(self, path: str):
        self._set_files([path])

    def _set_files(self, paths: list[str]):
        if not paths:
            return
        self._current_files = list(paths)
        self._current_file  = paths[0]
        self._canvas.update()
        self.files_selected.emit(paths)
        self.file_selected.emit(paths[0])


class _DropCanvas(QWidget):
    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z    = self._z
        W, H = self.width(), self.height()
        pad  = 2
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        bg_col = qcol(C.DROP_OVER if z._drag_over else (C.DROP_HOVER if z._hovering else C.PANEL2))
        p.setBrush(QBrush(bg_col)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 8, 8)

        if z._current_file:   border_col = qcol(C.GREEN, 180)
        elif z._drag_over:    border_col = qcol(C.PRI, 220)
        elif z._hovering:     border_col = qcol(C.PRI_DIM, 180)
        else:                 border_col = qcol(C.BORDER, 110)

        pen = QPen(border_col, 1.2, Qt.PenStyle.DashLine)
        pen.setDashOffset(z._dash_offset)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 8, 8)

        if len(z._current_files) > 1:
            self._paint_multi(p, W, H, z._current_files)
        elif z._current_file:
            self._paint_file(p, W, H)
        elif z._drag_over:
            self._paint_drag_over(p, W, H)
        else:
            self._paint_idle(p, W, H, z._hovering)

    def _paint_multi(self, p, W, H, files):
        n = len(files)
        p.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.GREEN), 1))
        p.drawText(QRectF(14, 10, W - 40, 18),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"📎  {n} archivos cargados")

        p.setFont(QFont("Courier New", 8))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        max_show = 2
        for i, fp in enumerate(files[:max_show]):
            name = Path(fp).name
            if len(name) > 42: name = name[:39] + "..."
            p.drawText(QRectF(18, 32 + i * 14, W - 50, 14),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       f"• {name}")
        if n > max_show:
            p.setPen(QPen(qcol(C.TEXT_MED), 1))
            p.drawText(QRectF(18, 32 + max_show * 14, W - 50, 14),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       f"  …y {n - max_show} más")

        p.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.RED, 200), 1))
        p.drawText(QRectF(W - 30, 0, 20, H), Qt.AlignmentFlag.AlignCenter, "✕")

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2
        col = qcol(C.PRI_DIM if not hover else C.PRI)
        p.setPen(QPen(col, 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx, cy - 16), QPointF(cx, cy + 2))
        p.drawLine(QPointF(cx - 6, cy - 10), QPointF(cx, cy - 16))
        p.drawLine(QPointF(cx + 6, cy - 10), QPointF(cx, cy - 16))
        p.drawLine(QPointF(cx - 12, cy + 2), QPointF(cx + 12, cy + 2))
        
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold if hover else QFont.Weight.Normal))
        p.setPen(QPen(qcol(C.TEXT if hover else C.TEXT_MED), 1))
        p.drawText(QRectF(0, cy + 8, W, 16), Qt.AlignmentFlag.AlignCenter,
                   "Arrastra archivos aquí o haz clic para explorar")

    def _paint_drag_over(self, p, W, H):
        cx, cy = W / 2, H / 2
        p.setFont(QFont("Courier New", 18))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy - 20, W, 26), Qt.AlignmentFlag.AlignCenter, "⬇")
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy + 10, W, 16), Qt.AlignmentFlag.AlignCenter,
                   "Suelta los elementos para inicializar")

    def _paint_file(self, p, W, H):
        path = Path(self._z._current_file)
        cat  = _file_category(path)
        icon, icon_col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size_str = _fmt_size(path.stat().st_size)
        ext_str  = path.suffix.upper().lstrip(".") or "DATA"

        block_x, block_w = 12, 50
        p.setFont(QFont("Segoe UI Emoji", 20) if _OS == "Windows" else QFont("Arial", 20))
        p.setPen(QPen(qcol(icon_col), 1))
        p.drawText(QRectF(block_x, 0, block_w, H), Qt.AlignmentFlag.AlignCenter, icon)

        tx = block_x + block_w + 4
        tw = W - tx - 34

        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.WHITE), 1))
        name = path.name if len(path.name) <= 36 else path.name[:33] + "..."
        p.drawText(QRectF(tx, H * 0.22, tw, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(tx, H * 0.22 + 16, tw, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{ext_str}  ·  {size_str}")

        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.RED, 200), 1))
        p.drawText(QRectF(W - 30, 0, 20, H), Qt.AlignmentFlag.AlignCenter, "✕")

    def mousePressEvent(self, e):
        z = self._z
        if z._current_file and e.pos().x() > self.width() - 34:
            z.clear_file()
        else:
            z.mousePressEvent(e)


# ============================================================
#  Ventana de modo compacto (Picture-in-Picture)
# ============================================================
class CompactWindow(QMainWindow):
    restore_requested = pyqtSignal()

    _RESIZE_MARGIN = 6
    _RESIZE_NONE  = 0
    _RESIZE_LEFT  = 1
    _RESIZE_RIGHT = 2
    _RESIZE_TOP   = 4
    _RESIZE_BOT   = 8

    def __init__(self, face_path: str, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.resize(240, 280)
        self.setMinimumSize(180, 220)
        self.setMaximumSize(900, 900)
        self.setWindowTitle("O.R.I.O.N — Compacto")
        self.setMouseTracking(True)

        central = QWidget()
        central.setMouseTracking(True)
        self.setCentralWidget(central)

        lay = QVBoxLayout(central)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(2)

        self._top_bar = QWidget()
        self._top_bar.setMouseTracking(True)
        self._top_bar.setFixedHeight(22)
        top = QHBoxLayout(self._top_bar)
        top.setContentsMargins(2, 0, 2, 0)
        top.setSpacing(4)

        title = QLabel("◈  O.R.I.O.N")
        title.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        top.addWidget(title)
        top.addStretch()

        note_btn = QPushButton("📝")
        note_btn.setFixedSize(20, 20)
        note_btn.setFont(QFont("Segoe UI Emoji", 9))
        note_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        note_btn.setToolTip("Tomar una nota rápida (Enter para guardar)")
        note_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.PRI}; }}
        """)
        note_btn.clicked.connect(self._toggle_note_popup)
        self._note_btn = note_btn
        top.addWidget(note_btn)

        restore_btn = QPushButton("⛶")
        restore_btn.setFixedSize(20, 20)
        restore_btn.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        restore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        restore_btn.setToolTip("Restaurar ventana principal")
        restore_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.PRI}; }}
        """)
        restore_btn.clicked.connect(self.restore_requested.emit)
        top.addWidget(restore_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Cerrar compacto")
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ color: {C.RED}; border-color: {C.RED}; }}
        """)
        close_btn.clicked.connect(self.restore_requested.emit)
        top.addWidget(close_btn)

        lay.addWidget(self._top_bar)

        from ui_components.orb_widget import make_orion_orb
        self.hud = make_orion_orb(face_path)
        self.hud.setMinimumSize(150, 150)
        self.hud.setMouseTracking(True)
        lay.addWidget(self.hud, stretch=1)

        self._resize_hint = QLabel("⤡")
        self._resize_hint.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        self._resize_hint.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self._resize_hint.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; padding-right: 2px;")
        self._resize_hint.setFixedHeight(12)
        self._resize_hint.setMouseTracking(True)
        lay.addWidget(self._resize_hint)

        central.setStyleSheet(
            f"QWidget {{ background: {C.BG}; }}"
            f"QWidget#wrap {{ border: 1px solid {C.BORDER_B}; border-radius: 6px; }}"
        )
        central.setObjectName("wrap")

        self._drag_pos = None
        self._resize_edge = self._RESIZE_NONE
        self._resize_start_geom = None
        self._resize_start_mouse = None

    def set_state(self, state: str):
        self.hud.state    = state
        self.hud.speaking = (state == "HABLANDO")

    def set_muted(self, muted: bool):
        self.hud.muted = muted

    def _toggle_note_popup(self):
        popup = getattr(self, "_note_popup", None)
        if popup is not None and popup.isVisible():
            popup.hide()
            return
        if popup is None:
            popup = QFrame(self)
            popup.setObjectName("notepop")
            popup.setStyleSheet(f"""
                QFrame#notepop {{
                    background: {C.PANEL2};
                    border: 1px solid {C.BORDER_B};
                    border-radius: 6px;
                }}
            """)
            lay = QVBoxLayout(popup)
            lay.setContentsMargins(8, 6, 8, 6)
            lay.setSpacing(4)

            hint = QLabel("📝  NUEVA NOTA  (Enter para guardar · Esc para cancelar)")
            hint.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
            hint.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none; letter-spacing: 1px;")
            lay.addWidget(hint)

            edit = QLineEdit()
            edit.setPlaceholderText("Escribe la nota…")
            edit.setFont(QFont("Segoe UI", 9))
            edit.setStyleSheet(f"""
                QLineEdit {{
                    background: {C.PANEL}; color: {C.TEXT};
                    border: 1px solid {C.BORDER}; border-radius: 4px;
                    padding: 4px 6px;
                }}
                QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
            """)
            edit.returnPressed.connect(self._save_note_from_popup)
            try:
                sc = QShortcut(QKeySequence("Escape"), edit)
                sc.activated.connect(lambda: (edit.clear(), popup.hide()))
            except Exception:
                pass
            lay.addWidget(edit)

            popup.adjustSize()
            self._note_popup = popup
            self._note_edit  = edit

        btn = self._note_btn
        p = btn.mapTo(self, QPoint(0, btn.height() + 2))
        w = max(220, self.width() - 12)
        popup.setGeometry(6, p.y(), w, popup.sizeHint().height())
        popup.show()
        popup.raise_()
        self._note_edit.setFocus()

    def _save_note_from_popup(self):
        edit = getattr(self, "_note_edit", None)
        if edit is None: return
        text = edit.text().strip()
        if not text: return
        try:
            from memory.quick_notes import add_note
            add_note(text)
        except Exception as exc:
            print(f"[Compact] No se pudo guardar la nota: {exc}")
            return
        edit.clear()
        if hasattr(self, "_note_popup"):
            self._note_popup.hide()
        try:
            self._note_btn.setText("✓")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(900, lambda: self._note_btn.setText("📝"))
        except Exception:
            pass

    def _edge_at(self, pos: QPoint) -> int:
        m = self._RESIZE_MARGIN
        w, h = self.width(), self.height()
        edge = self._RESIZE_NONE
        if pos.x() <= m:           edge |= self._RESIZE_LEFT
        if pos.x() >= w - m:       edge |= self._RESIZE_RIGHT
        if pos.y() <= m:           edge |= self._RESIZE_TOP
        if pos.y() >= h - m:       edge |= self._RESIZE_BOT
        return edge

    def _cursor_for_edge(self, edge: int) -> Qt.CursorShape:
        if edge == (self._RESIZE_LEFT | self._RESIZE_TOP) or edge == (self._RESIZE_RIGHT | self._RESIZE_BOT):
            return Qt.CursorShape.SizeFDiagCursor
        if edge == (self._RESIZE_RIGHT | self._RESIZE_TOP) or edge == (self._RESIZE_LEFT | self._RESIZE_BOT):
            return Qt.CursorShape.SizeBDiagCursor
        if edge & (self._RESIZE_LEFT | self._RESIZE_RIGHT):
            return Qt.CursorShape.SizeHorCursor
        if edge & (self._RESIZE_TOP | self._RESIZE_BOT):
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            edge = self._edge_at(e.position().toPoint())
            if edge != self._RESIZE_NONE:
                self._resize_edge = edge
                self._resize_start_geom = self.geometry()
                self._resize_start_mouse = e.globalPosition().toPoint()
                e.accept()
                return
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._resize_edge != self._RESIZE_NONE and (e.buttons() & Qt.MouseButton.LeftButton):
            self._do_resize(e.globalPosition().toPoint())
            e.accept()
            return
        if self._drag_pos is not None and (e.buttons() & Qt.MouseButton.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()
            return
        edge = self._edge_at(pos)
        self.setCursor(self._cursor_for_edge(edge))

    def mouseReleaseEvent(self, e):
        self._drag_pos = None
        self._resize_edge = self._RESIZE_NONE
        self._resize_start_geom = None
        self._resize_start_mouse = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def _do_resize(self, global_pos: QPoint):
        if self._resize_start_geom is None or self._resize_start_mouse is None: return
        dx = global_pos.x() - self._resize_start_mouse.x()
        dy = global_pos.y() - self._resize_start_mouse.y()
        g = self._resize_start_geom
        x, y, w, h = g.x(), g.y(), g.width(), g.height()
        min_w = self.minimumWidth()
        min_h = self.minimumHeight()
        max_w = self.maximumWidth()
        max_h = self.maximumHeight()

        if self._resize_edge & self._RESIZE_RIGHT: w = max(min_w, min(max_w, w + dx))
        if self._resize_edge & self._RESIZE_BOT:   h = max(min_h, min(max_h, h + dy))
        if self._resize_edge & self._RESIZE_LEFT:
            new_w = max(min_w, min(max_w, w - dx))
            x = x + (w - new_w)
            w = new_w
        if self._resize_edge & self._RESIZE_TOP:
            new_h = max(min_h, min(max_h, h - dy))
            y = y + (h - new_h)
            h = new_h

        self.setGeometry(x, y, w, h)

    def closeEvent(self, e):
        self.restore_requested.emit()
        e.accept()


# ============================================================
#  Overlay de configuración inicial
# ============================================================
class SetupOverlay(QWidget):
    done = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"SetupOverlay {{ background: rgba(10, 2, 5, 245); border: 1px solid {C.BORDER_B}; border-radius: 8px; }}")

        detected = {"darwin": "mac", "windows": "windows"}.get(_OS.lower(), "linux")
        self._sel_os = detected

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 22, 30, 22)
        layout.setSpacing(8)

        def _lbl(txt, font_size=9, bold=False, color=C.PRI, align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont("Courier New", font_size, QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        layout.addWidget(_lbl("◈  CONFIGURACIÓN REQUERIDA", 13, True))
        layout.addWidget(_lbl("Configura ORION antes del primer inicio.", 9, color=C.PRI_DIM))
        layout.addSpacing(6)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep)
        layout.addSpacing(4)

        layout.addWidget(_lbl("CLAVE API DE GEMINI", 8, color=C.TEXT_DIM, align=Qt.AlignmentFlag.AlignLeft))
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("AIza…")
        self._key_input.setFont(QFont("Courier New", 10))
        self._key_input.setFixedHeight(32)
        self._key_input.setStyleSheet(f"QLineEdit {{ background: {C.PANEL2}; color: {C.TEXT}; border: 1px solid {C.BORDER}; border-radius: 4px; padding: 4px 8px; }} QLineEdit:focus {{ border: 1px solid {C.PRI}; }}")
        layout.addWidget(self._key_input)
        layout.addSpacing(12)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep2)
        layout.addSpacing(4)

        layout.addWidget(_lbl("SISTEMA OPERATIVO", 8, color=C.TEXT_DIM, align=Qt.AlignmentFlag.AlignLeft))
        det_name = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}[detected]
        layout.addWidget(_lbl(f"Detectado automáticamente: {det_name}", 8, color=C.ACC2, align=Qt.AlignmentFlag.AlignLeft))

        os_row = QHBoxLayout(); os_row.setSpacing(6)
        self._os_btns: dict[str, QPushButton] = {}
        for key, label in [("windows","⊞  Windows"),("mac","  macOS"),("linux","🐧  Linux")]:
            btn = QPushButton(label)
            btn.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            btn.setFixedHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._sel(k))
            os_row.addWidget(btn)
            self._os_btns[key] = btn
        layout.addLayout(os_row)
        self._sel(detected)
        layout.addSpacing(12)

        init_btn = QPushButton("▸  INICIALIZAR SISTEMAS")
        init_btn.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        init_btn.setFixedHeight(38)
        init_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        init_btn.setStyleSheet(f"QPushButton {{ background: transparent; color: {C.PRI}; border: 1px solid {C.PRI_DIM}; border-radius: 4px; }} QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}")
        init_btn.clicked.connect(self._submit)
        layout.addWidget(init_btn)

    def _sel(self, key: str):
        self._sel_os = key
        pal = {"windows":(C.PRI, C.PRI_GHO),"mac":(C.ACC2, C.PANEL2),"linux":(C.GREEN, C.DARK)}
        for k, btn in self._os_btns.items():
            if k == key:
                fg, bg = pal[k]
                btn.setStyleSheet(f"QPushButton {{ background: {fg}; color: {bg}; border: none; border-radius: 4px; font-weight: bold; }}")
            else:
                btn.setStyleSheet(f"QPushButton {{ background: {C.PANEL2}; color: {C.TEXT_DIM}; border: 1px solid {C.BORDER}; border-radius: 4px; }} QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}")

    def _submit(self):
        key = self._key_input.text().strip()
        if not key:
            self._key_input.setStyleSheet(self._key_input.styleSheet() + f" QLineEdit {{ border: 1px solid {C.RED}; }}")
            return
        self.done.emit(key, self._sel_os)


# ============================================================
#  Ventana principal (Rediseño Espectacular UI de Conversación)
# ============================================================
class MainWindow(QMainWindow):
    _log_sig   = pyqtSignal(str)
    _state_sig = pyqtSignal(str)

    def __init__(self, face_path: str):
        super().__init__()
        self.setWindowTitle("O.R.I.O.N")
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width()  - _DEFAULT_W) // 2,
            (screen.height() - _DEFAULT_H) // 2,
        )

        self.on_text_command  = None
        self.on_interrupt     = None
        self._muted           = False
        self._current_file: str | None = None

        central = QWidget()
        central.setStyleSheet(f"background: {C.BG};")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._left_panel = self._build_left_panel()
        body.addWidget(self._left_panel, stretch=0)

        from ui_components.orb_widget import make_orion_orb
        self.hud = make_orion_orb(face_path)
        self.hud.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        body.addWidget(self.hud, stretch=5)

        self._right_panel = self._build_right_panel()
        body.addWidget(self._right_panel, stretch=0)

        root.addLayout(body, stretch=1)
        root.addWidget(self._build_footer())

        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        self._metric_tmr = QTimer(self)
        self._metric_tmr.timeout.connect(self._update_metrics)
        self._metric_tmr.start(2000)
        self._update_metrics()

        self._log_sig.connect(self._log.append_log)
        self._state_sig.connect(self._apply_state)

        self._overlay = None
        self._ready = self._check_config()
        if not self._ready:
            self._show_setup()

        sc_mute = QShortcut(QKeySequence("F4"), self)
        sc_mute.activated.connect(self._toggle_mute)
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)

        sc_compact = QShortcut(QKeySequence("F9"), self)
        sc_compact.activated.connect(self._toggle_compact_mode)

        self._face_path = face_path
        self._compact_window = None

        self._setup_tray()

        self._hotkeys = _load_hotkeys()
        self._setup_global_hotkeys()

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _show_settings_panel(self):
        if not hasattr(self, "_settings_panel") or self._settings_panel is None:
            self._settings_panel = SettingsPanel(theme=C, parent=self)
            self._settings_panel.theme_changed.connect(
                lambda t: self._tray.showMessage(
                    "O.R.I.O.N — Tema",
                    f"Tema cambiado a '{t}'. Reinicia para aplicar.",
                    QSystemTrayIcon.MessageIcon.Information, 3000,
                ) if hasattr(self, "_tray") else None
            )
            self._settings_panel.settings_changed.connect(
                lambda: self._log.append_log("SISTEMA: Configuración actualizada.")
            )
        self._settings_panel.show()
        self._settings_panel.raise_()
        self._settings_panel.activateWindow()

    def _persist_log(self, text: str) -> None:
        if not text or self._conversation is None:
            return
        t = text.strip()
        tl = t.lower()
        try:
            if tl.startswith(("tú:", "tu:")):
                role, body = "user", t.split(":", 1)[1].strip()
            elif tl.startswith(("orion:", "o.r.i.o.n:")):
                role, body = "ai", t.split(":", 1)[1].strip()
            elif tl.startswith(("sistema:", "sys:")):
                role, body = "sys", t.split(":", 1)[1].strip()
            elif tl.startswith("error"):
                role, body = "err", t
            elif tl.startswith("archivo:"):
                role, body = "file", t.split(":", 1)[1].strip()
            else:
                role, body = "sys", t
        except (IndexError, ValueError):
            role, body = "sys", t
        if not body:
            return
        self._conversation.add(role, body)

    def _show_history_panel(self):
        if self._history_panel is None:
            self._history_panel = HistoryPanel(theme=C, parent=self)
            self._history_panel.conversation_selected.connect(self._load_conversation)
        self._history_panel.reload()
        self._history_panel.show()
        self._history_panel.raise_()
        self._history_panel.activateWindow()

    def _load_conversation(self, conv_id: str) -> None:
        conv = get_conversation(conv_id)
        if not conv: return
        self._log.clear()
        valid_roles = {"user", "ai", "sys", "err", "file"}
        for msg in conv.get("messages", []):
            role = msg.get("role", "sys")
            if role not in valid_roles: role = "sys"
            txt = msg.get("text", "")
            if txt: self._log.add_message(role, txt)
        self._conversation = ConversationSession()
        self._log.append_log(f"SISTEMA: Conversación cargada ({len(conv.get('messages', []))} mensajes).")

    def _toggle_compact_mode(self):
        if self._compact_window and self._compact_window.isVisible():
            self._close_compact()
            return

        if self._compact_window is None:
            self._compact_window = CompactWindow(self._face_path)
            self._compact_window.restore_requested.connect(self._close_compact)
            self._state_sig.connect(self._compact_window.set_state)
            self._compact_window.set_muted(self._muted)
            self._compact_window.set_state(self.hud.state)

        screen = QApplication.primaryScreen().availableGeometry()
        cw = self._compact_window
        cw.move(screen.right() - cw.width() - 20, screen.bottom() - cw.height() - 20)
        cw.show()
        cw.raise_()
        self.hide()

    def _close_compact(self):
        if self._compact_window: self._compact_window.hide()
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _show_notes_panel(self):
        if not hasattr(self, "_notes_panel") or self._notes_panel is None:
            self._notes_panel = NotesPanel(theme=C, parent=self)
        self._notes_panel.reload()
        self._notes_panel.show()
        self._notes_panel.raise_()
        self._notes_panel.activateWindow()

    def changeEvent(self, event):
        from PyQt6.QtCore import QEvent
        if event.type() == QEvent.Type.WindowStateChange:
            paused = self.isMinimized()
            if hasattr(self, "hud"): self.hud.set_paused(paused)
            if hasattr(self, "_metric_tmr"): self._metric_tmr.setInterval(8000 if paused else 2000)
        super().changeEvent(event)

    def _setup_tray(self):
        self._tray = QSystemTrayIcon(self)
        icon_path = str(TRAY_ICON_PATH)
        if TRAY_ICON_PATH.exists():
            self._tray.setIcon(QIcon(icon_path))
        else:
            self._tray.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon))

        tray_menu = QMenu()
        tray_menu.setStyleSheet(f"QMenu {{ background: {C.DARK}; color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }} QMenu::item:selected {{ background: {C.PRI_GHO}; color: {C.PRI}; }}")

        show_action = QAction("Mostrar O.R.I.O.N", self)
        show_action.triggered.connect(self._tray_show)
        tray_menu.addAction(show_action)

        self._tray_mic_action = QAction("Activar Mic", self)
        self._tray_mic_action.triggered.connect(self._toggle_mute)
        tray_menu.addAction(self._tray_mic_action)

        tray_menu.addSeparator()

        quit_action = QAction("Salir", self)
        quit_action.triggered.connect(self._quit_app)
        tray_menu.addAction(quit_action)

        self._tray.setContextMenu(tray_menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick: self._tray_show()

    def _tray_show(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _quit_app(self):
        self._really_quit = True
        try: keyboard.unhook_all()
        except Exception: pass
        try:
            if hasattr(self, "_clock_tmr"): self._clock_tmr.stop()
            if hasattr(self, "_metric_tmr"): self._metric_tmr.stop()
        except Exception: pass
        if self._compact_window: self._compact_window.close()
        self._tray.hide()
        QApplication.quit()

    def _setup_global_hotkeys(self):
        hk = self._hotkeys
        try: keyboard.add_hotkey(hk.get("toggle_microphone", "ctrl+\\"), self._global_toggle_mic, suppress=False)
        except Exception as e: print(f"[ORION] Hotkey toggle_microphone falló: {e}")
        try: keyboard.add_hotkey(hk.get("show_window", "ctrl+shift+o"), self._global_show_window, suppress=False)
        except Exception as e: print(f"[ORION] Hotkey show_window falló: {e}")

    def _global_toggle_mic(self): QTimer.singleShot(0, self._toggle_mute)
    def _global_show_window(self): QTimer.singleShot(0, self._tray_show)

    def closeEvent(self, event):
        if getattr(self, "_really_quit", False):
            try: keyboard.unhook_all()
            except Exception: pass
            try:
                if hasattr(self, "_clock_tmr"): self._clock_tmr.stop()
                if hasattr(self, "_metric_tmr"): self._metric_tmr.stop()
            except Exception: pass
            super().closeEvent(event)
            return

        event.ignore()
        self.hide()
        if not self._muted: self._toggle_mute()

        hotkey_str = self._hotkeys.get("toggle_microphone", "ctrl+\\")
        self._tray.showMessage("O.R.I.O.N", f"Minimizado a la bandeja. Mic apagado.\nUsa {hotkey_str} para activar el mic.", QSystemTrayIcon.MessageIcon.Information, 3000)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._overlay and self._overlay.isVisible():
            ow, oh = 540, 470
            cw = self.centralWidget()
            self._overlay.setGeometry((cw.width() - ow) // 2, (cw.height() - oh) // 2, ow, oh)
        if (hasattr(self, "_sidebar_trigger")
                and self._sidebar_trigger.isVisible()):
            self._position_sidebar_trigger()

    def _update_metrics(self):
        snap = _metrics.snapshot()
        cpu = snap["cpu"]
        self._bar_cpu.set_value(cpu, f"{cpu:.0f}%")
        mem = snap["mem"]
        self._bar_mem.set_value(mem, f"{mem:.0f}%")
        net = snap["net"]
        net_str = f"{net*1024:.0f}KB/s" if net < 1.0 else f"{net:.1f}MB/s"
        self._bar_net.set_value(min(100, net * 10), net_str)
        gpu = snap["gpu"]
        self._bar_gpu.set_value(gpu if gpu >= 0 else 0, f"{gpu:.0f}%" if gpu >= 0 else "N/D")
        tmp = snap["tmp"]
        self._bar_tmp.set_value(min(100, tmp) if tmp >= 0 else 0, f"{tmp:.0f}°C" if tmp >= 0 else "N/D")

        try:
            boot_t  = psutil.boot_time()
            elapsed = time.time() - boot_t
            self._uptime_lbl.setText(f"ENCENDIDO  {int(elapsed // 3600):02d}:{int((elapsed % 3600) // 60):02d}")
        except Exception: self._uptime_lbl.setText("ENCENDIDO  --:--")

        try: self._proc_lbl.setText(f"PROCESOS  {len(psutil.pids())}")
        except Exception: self._proc_lbl.setText("PROCESOS  --")

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(56)
        w.setStyleSheet(f"background: {C.DARK}; border-bottom: 1px solid {C.BORDER_B};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(18, 0, 18, 0)

        gh_btn = GitHubButton(GITHUB_URL)
        lay.addWidget(gh_btn)
        lay.addSpacing(8)
        lbl_v = QLabel("Versión 1.0")
        lbl_v.setFont(QFont("Courier New", 8))
        lbl_v.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        lay.addWidget(lbl_v)
        lay.addStretch()

        mid = QVBoxLayout(); mid.setSpacing(1)
        title = QLabel("O.R.I.O.N")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Courier New", 18, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent; letter-spacing: 2px;")
        mid.addWidget(title)
        sub = QLabel("Operador de Redes Inteligentes y Optimización Neural")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setFont(QFont("Courier New", 7))
        sub.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        mid.addWidget(sub)
        lay.addLayout(mid)
        lay.addStretch()

        right_col = QVBoxLayout(); right_col.setSpacing(2)
        self._clock_lbl = QLabel("00:00:00")
        self._clock_lbl.setFont(QFont("Courier New", 15, QFont.Weight.Bold))
        self._clock_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._clock_lbl)
        self._date_lbl = QLabel("")
        self._date_lbl.setFont(QFont("Courier New", 7))
        self._date_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._date_lbl)
        lay.addLayout(right_col)
        return w

    def _tick_clock(self):
        self._clock_lbl.setText(time.strftime("%H:%M:%S"))
        t = time.localtime()
        self._date_lbl.setText(f"{_DIAS_ES[t.tm_wday]} {t.tm_mday:02d} {_MESES_ES[t.tm_mon - 1]} {t.tm_year}")

    def _build_left_panel(self) -> QWidget:
        """Construye la sidebar premium reconstruida en Fase 2,
        ahora con telemetría avanzada de Fase 5.

        Mantiene los atributos `_bar_cpu/_mem/_net/_gpu/_tmp` y los labels
        de info como antes para preservar `_update_metrics` sin cambios.
        """
        # Telemetría avanzada (MetricCard tiene la misma firma set_value que MetricBar)
        from ui_components.telemetry_panel import MetricCard, SystemInfoBlock
        from ui_components.design_system import theme_dict_from_class
        theme_dict = theme_dict_from_class(C)

        self._bar_cpu = MetricCard("CPU", color_key="PRI",  theme=theme_dict)
        self._bar_mem = MetricCard("MEM", color_key="ACC2", theme=theme_dict)
        self._bar_net = MetricCard("RED", color_key="GREEN", theme=theme_dict)
        self._bar_gpu = MetricCard("GPU", color_key="ACC",  theme=theme_dict)
        self._bar_tmp = MetricCard("TEMP", color_key="TEMP_C", theme=theme_dict)

        # Bloque de información (uptime / procesos / SO)
        self._info_block = SystemInfoBlock(theme=theme_dict)

        self._uptime_lbl = QLabel("ENCENDIDO  --:--")
        self._uptime_lbl.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        self._uptime_lbl.setStyleSheet(
            f"color: {C.GREEN}; background: transparent; border: none;"
        )
        self._info_block.add_label(self._uptime_lbl)

        self._proc_lbl = QLabel("PROCESOS  --")
        self._proc_lbl.setFont(QFont("Courier New", 7))
        self._proc_lbl.setStyleSheet(
            f"color: {C.TEXT_MED}; background: transparent; border: none;"
        )
        self._info_block.add_label(self._proc_lbl)

        os_short = {"Windows": "WIN", "Darwin": "macOS", "Linux": "LINUX"}.get(
            _OS, _OS.upper()
        )
        os_lbl = QLabel(f"SO  {os_short}")
        os_lbl.setFont(QFont("Courier New", 7))
        os_lbl.setStyleSheet(
            f"color: {C.ACC2}; background: transparent; border: none;"
        )
        self._info_block.add_label(os_lbl)

        # Sidebar premium
        sidebar = SidebarPanel(theme_dict, parent=self)

        # Inyectar métricas e info
        for bar in (self._bar_cpu, self._bar_mem, self._bar_net,
                    self._bar_gpu, self._bar_tmp):
            sidebar.attach_metric_widget(bar)
        sidebar.attach_info_widget(self._info_block)

        # Cargar conversaciones recientes al construir
        sidebar.reload_recents()

        # Cablear navegación
        sidebar.nav_home_requested.connect(self._on_nav_home)
        sidebar.nav_agents_requested.connect(self._on_nav_agents)
        sidebar.nav_notes_requested.connect(self._show_notes_panel)
        sidebar.nav_history_requested.connect(self._show_history_panel)
        sidebar.nav_settings_requested.connect(self._show_settings_panel)
        sidebar.new_chat_requested.connect(self._on_new_chat)
        sidebar.conversation_clicked.connect(self._load_conversation)
        sidebar.collapse_toggled.connect(self._on_sidebar_collapsed)

        self._sidebar = sidebar

        # Trigger flotante para reabrir la sidebar (anclado al body)
        self._sidebar_trigger = SidebarTrigger(theme_dict, parent=self)
        self._sidebar_trigger.clicked.connect(self._on_sidebar_trigger)
        self._sidebar_trigger.hide()

        return sidebar

    # ── Slots de la sidebar ────────────────────────────────────────────────
    def _on_nav_home(self) -> None:
        """Volver al estado por defecto del workspace (foco en el chat)."""
        if hasattr(self, "_input"):
            self._input.setFocus()

    def _on_nav_agents(self) -> None:
        """Abre el centro de agentes (Fase 6)."""
        if not hasattr(self, "_agents_hub") or self._agents_hub is None:
            from ui_components.agents_hub import AgentsHubPanel
            from ui_components.design_system import theme_dict_from_class
            self._agents_hub = AgentsHubPanel(
                theme=theme_dict_from_class(C), parent=self
            )
            # Cableado mínimo de feedback en el chat
            self._agents_hub.deploy_clicked.connect(
                lambda: self._log.append_log(
                    "SISTEMA: Despliegue de ORION solicitado desde el hub."))
            self._agents_hub.room_clicked.connect(
                lambda room_id: self._log.append_log(
                    f"SISTEMA: Sala '{room_id}' seleccionada."))
            self._agents_hub.new_room_requested.connect(
                lambda: self._log.append_log(
                    "SISTEMA: Crear nueva sala — pendiente de implementación."))
        self._agents_hub.show()
        self._agents_hub.raise_()
        self._agents_hub.activateWindow()

    def _on_new_chat(self) -> None:
        """Limpia el chat y abre una nueva sesión de conversación."""
        try:
            self._log.clear()
        except Exception:
            pass
        try:
            self._conversation = ConversationSession()
        except Exception as e:
            print(f"[Conv] no se pudo iniciar sesión: {e}")
            self._conversation = None
        self._log.append_log("SISTEMA: Nuevo hilo iniciado.")
        if hasattr(self, "_sidebar"):
            try:
                self._sidebar.reload_recents()
            except Exception:
                pass

    def _on_sidebar_collapsed(self, collapsed: bool) -> None:
        if collapsed:
            self._position_sidebar_trigger()
            self._sidebar_trigger.show()
            self._sidebar_trigger.raise_()
        else:
            self._sidebar_trigger.hide()

    def _on_sidebar_trigger(self) -> None:
        if hasattr(self, "_sidebar"):
            self._sidebar.set_collapsed(False)

    def _position_sidebar_trigger(self) -> None:
        """Coloca el trigger flotante en la esquina superior-izquierda del body."""
        if not hasattr(self, "_sidebar_trigger"):
            return
        # 16px del borde izquierdo, debajo del header (~70)
        self._sidebar_trigger.move(16, 72)


    # ============================================================
    #  REDISEÑO DE CONVERSACIÓN (UI/UX Premium Profesional)
    # ============================================================
    def _build_right_panel(self) -> QWidget:
        """Crea el panel lateral derecho con un rediseño espectacular e interactivo."""
        w = QWidget()
        w.setFixedWidth(_RIGHT_W)
        w.setStyleSheet(f"background: {C.DARK}; border-left: 1px solid {C.BORDER};")
        
        # Layout principal del panel derecho
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(12)

        # Helper para generar los headers de cada sección de forma limpia y moderna
        def _section_header(title: str, subtitle: str = "") -> QWidget:
            box = QWidget()
            vlay = QVBoxLayout(box)
            vlay.setContentsMargins(2, 0, 2, 2)
            vlay.setSpacing(1)
            
            main_lbl = QLabel(title)
            main_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
            main_lbl.setStyleSheet(f"color: {C.PRI}; letter-spacing: 1.5px; background: transparent;")
            vlay.addWidget(main_lbl)
            
            if subtitle:
                sub_lbl = QLabel(subtitle)
                sub_lbl.setFont(QFont("Courier New", 6))
                sub_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
                vlay.addWidget(sub_lbl)
            return box

        # --- SECCIÓN 1: CHAT/CONVERSACIÓN ---
        lay.addWidget(_section_header("// TERMINAL DE COMUNICACIÓN", "INTERFAZ DE CONTROL NEURAL"))
        
        self._log = ChatPanel(theme=C)
        self._log.dropped_text.connect(self._on_log_drop_text)
        self._log.dropped_files.connect(self._on_files_selected)
        
        try:
            self._conversation = ConversationSession()
        except Exception as e:
            print(f"[Conv] no se pudo iniciar sesión: {e}")
            self._conversation = None
            
        self._history_panel = None
        _orig_append = self._log.append_log
        
        def _append_and_persist(text: str):
            try: _orig_append(text)
            except Exception as e: print(f"[Chat] append_log falló: {e}"); return
            try: self._persist_log(text)
            except Exception as e: print(f"[Conv] error persistiendo: {e}")
                
        self._log.append_log = _append_and_persist  # type: ignore[method-assign]
        lay.addWidget(self._log, stretch=1)

        # --- SECCIÓN 2: ARRASTRAR Y SOLTAR ---
        lay.addWidget(_section_header("// TRANSFERENCIA DE DATOS", "SOPORTE MULTI-FORMATO"))
        
        self._drop_zone = FileDropZone()
        self._drop_zone.files_selected.connect(self._on_files_selected)
        lay.addWidget(self._drop_zone)

        self._file_hint = QLabel("Esperando secuencia de archivos externos...")
        self._file_hint.setFont(QFont("Courier New", 7))
        self._file_hint.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; padding-left: 4px;")
        self._file_hint.setWordWrap(True)
        lay.addWidget(self._file_hint)

        # --- SECCIÓN 3: COMANDOS ENTRADA ---
        lay.addWidget(_section_header("// COMANDOS DE NÚCLEO", "EJECUCIÓN DIRECTA"))
        lay.addLayout(self._build_input_row())

        # --- SECCIÓN 4: ACCIONES E INTERRUPCIONES ---
        # Botón Interrumpir Premium (Fluye dinámicamente)
        self._stop_btn = QPushButton("⏹  INTERRUMPIR PROCESO VOZ")
        self._stop_btn.setFixedHeight(36)
        self._stop_btn.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.RED}; color: {C.WHITE};
                border: none; border-radius: 6px;
                font-weight: bold; letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background: {C.MUTE_BTN_BG};
            }}
            QPushButton:pressed {{
                background: {C.MUTE_BTN_HOV};
            }}
        """)
        self._stop_btn.clicked.connect(self._on_stop_clicked)
        self._stop_btn.hide()
        lay.addWidget(self._stop_btn)

        # Botón Micrófono Integrado Premium
        self._mute_btn = QPushButton()
        self._mute_btn.setFixedHeight(34)
        self._mute_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.clicked.connect(self._toggle_mute)
        self._style_mute_btn()
        lay.addWidget(self._mute_btn)

        # Fila de utilidades de pantalla y PiP (Diseño ultra-limpio lado a lado)
        utility_layout = QHBoxLayout()
        utility_layout.setSpacing(8)

        fs_btn = QPushButton("⛶  FULLSCREEN")
        fs_btn.setFixedHeight(28)
        fs_btn.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        fs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fs_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL2}; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 4px;
            }}
            QPushButton:hover {{
                color: {C.PRI}; border-color: {C.PRI}; background: {C.PRI_GHO};
            }}
        """)
        fs_btn.clicked.connect(self._toggle_fullscreen)
        utility_layout.addWidget(fs_btn)

        compact_btn = QPushButton("◰  PIP COMPACTO")
        compact_btn.setFixedHeight(28)
        compact_btn.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        compact_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        compact_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL2}; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 4px;
            }}
            QPushButton:hover {{
                color: {C.PRI}; border-color: {C.PRI}; background: {C.PRI_GHO};
            }}
        """)
        compact_btn.clicked.connect(self._toggle_compact_mode)
        utility_layout.addWidget(compact_btn)

        lay.addLayout(utility_layout)
        return w

    def _build_input_row(self) -> QHBoxLayout:
        """Crea una barra de comandos estilizada de forma espectacular."""
        row = QHBoxLayout()
        row.setSpacing(6)
        
        self._input = QLineEdit()
        self._input.setPlaceholderText("Introducir instrucción cuántica o consulta...")
        self._input.setFont(QFont("Courier New", 9))
        self._input.setFixedHeight(34)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.PANEL2}; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 6px; 
                padding: 2px 10px;
            }}
            QLineEdit:focus {{ 
                border: 1px solid {C.PRI};
                background: {C.PANEL};
            }}
        """)
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input)

        send = QPushButton("▸")
        send.setFixedSize(34, 34)
        send.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(f"""
            QPushButton {{
                background: {C.PRI_GHO}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 6px;
            }}
            QPushButton:hover {{ 
                background: {C.PRI}; color: {C.DARK}; border-color: {C.PRI}; 
            }}
            QPushButton:pressed {{ 
                background: {C.PRI_DIM}; 
            }}
        """)
        send.clicked.connect(self._send)
        row.addWidget(send)
        return row

    def _style_mute_btn(self):
        """Aplica estilos dinámicos de alto nivel según el estado del micrófono."""
        if self._muted:
            self._mute_btn.setText("🔇  MICRÓFONO DESACTIVADO")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C.BTN_BG_ERR}; color: {C.MUTED_C};
                    border: 1px solid {C.MUTED_C}; border-radius: 6px;
                    font-weight: bold; letter-spacing: 0.5px;
                }}
                QPushButton:hover {{ background: {C.BTN_BG_ERR_H}; }}
            """)
        else:
            self._mute_btn.setText("🎙  SISTEMA DE ESCUCHA ACTIVO")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C.BTN_BG_OK}; color: {C.GREEN};
                    border: 1px solid {C.GREEN}; border-radius: 6px;
                    font-weight: bold; letter-spacing: 0.5px;
                }}
                QPushButton:hover {{ background: {C.BTN_BG_OK_H}; }}
            """)

    # --------- Resto de Métodos de Eventos (Mantenidos intactos) ---------
    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(24)
        w.setStyleSheet(f"background: {C.DARK}; border-top: 1px solid {C.BORDER};")
        lay = QHBoxLayout(w); lay.setContentsMargins(14, 0, 14, 0)

        def _fl(txt, color=C.TEXT_MED):
            l = QLabel(txt); l.setFont(QFont("Courier New", 7))
            l.setStyleSheet(f"color: {color}; background: transparent;")
            return l

        hk_mic = _load_hotkeys().get("toggle_microphone", "ctrl+\\")
        lay.addWidget(_fl(f"[F4/{hk_mic}] Silenciar  ·  [F11] Pantalla completa  ·  [F9] Compacto"))
        lay.addStretch()
        lay.addWidget(_fl("O.R.I.O.N  ·  En línea", C.PRI_DIM))
        return w

    def _on_file_selected(self, path: str):
        self._current_file = path
        p    = Path(path)
        cat  = _file_category(p)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size = _fmt_size(p.stat().st_size)
        self._file_hint.setText(f"{icon}  {p.name} ({size}) cargado con éxito.")
        self._log.append_log(f"ARCHIVO: {p.name} ({size}) cargado")
        if self.on_text_command:
            msg = (
                f"[ARCHIVO_CARGADO] ruta={path} | nombre={p.name} | "
                f"tipo={p.suffix.lstrip('.')} | tamaño={size} | "
                f"Indica brevemente al usuario que puedes ver el archivo "
                f"'{p.name}' ({size}) y pregunta qué desea hacer con él."
            )
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def _on_files_selected(self, paths: list[str]):
        if not paths: return
        if len(paths) == 1:
            self._on_file_selected(paths[0])
            return

        self._current_file = paths[0]
        lines = []
        for p_str in paths:
            p = Path(p_str)
            try: size = _fmt_size(p.stat().st_size)
            except OSError: size = "?"
            cat = _file_category(p)
            icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
            lines.append(f"  {icon}  {p.name}  ·  {size}")
            self._log.append_log(f"ARCHIVO: {p.name} ({size}) cargado")

        self._file_hint.setText(f"📎  {len(paths)} matrices cargadas  ·  Foco: {Path(paths[0]).name}")

        if self.on_text_command:
            files_summary = "\n".join(lines)
            paths_csv = "|".join(paths)
            msg = (
                f"[ARCHIVOS_CARGADOS] count={len(paths)} | "
                f"rutas={paths_csv} | activo={paths[0]} | "
                f"Indica brevemente al usuario que recibiste {len(paths)} "
                f"archivos y pregunta qué desea hacer con ellos. Lista:\n{files_summary}"
            )
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def _toggle_mute(self):
        self._muted = not self._muted
        self.hud.muted = self._muted
        if self._compact_window: self._compact_window.set_muted(self._muted)
        self._style_mute_btn()
        if hasattr(self, "_tray_mic_action"):
            self._tray_mic_action.setText("Activar Mic" if self._muted else "Silenciar Mic")
        if self._muted:
            self._apply_state("SILENCIADO")
            self._log.append_log("SISTEMA: Micrófono silenciado.")
        else:
            self._apply_state("ESCUCHANDO")
            self._log.append_log("SISTEMA: Micrófono activo.")

    def _send(self):
        txt = self._input.text().strip()
        if not txt: return
        self._input.clear()
        self._log.append_log(f"Tú: {txt}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(txt,), daemon=True).start()

    def _apply_state(self, state: str):
        self.hud.state    = state
        self.hud.speaking = (state == "HABLANDO")
        if hasattr(self, "_stop_btn"):
            if state == "HABLANDO": self._stop_btn.show()
            else: self._stop_btn.hide()

    def _on_log_drop_text(self, text: str):
        if not text: return
        preview = text if len(text) <= 80 else text[:77] + "..."
        self._log.append_log(f"ARCHIVO: Texto recibido → {preview}")
        if text.startswith(("http://", "https://")):
            msg = f"[CONTENIDO_ARRASTRADO] tipo=URL valor={text} | Procesa esta URL."
        else:
            msg = f"[CONTENIDO_ARRASTRADO] tipo=texto valor={text[:500]} | Procesa este texto."
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def _on_stop_clicked(self):
        self._log.append_log("SISTEMA: Interrupción solicitada por el usuario.")
        if self.on_interrupt:
            try: threading.Thread(target=self.on_interrupt, daemon=True).start()
            except Exception as e: self._log.append_log(f"ERROR al interrumpir: {e}")

    def _check_config(self) -> bool:
        if not API_FILE.exists(): return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(d.get("gemini_api_key")) and bool(d.get("os_system"))
        except Exception: return False

    def _show_setup(self):
        ov = OnboardingWizard(theme=C, parent=self.centralWidget())
        cw = self.centralWidget()
        ow, oh = 540, 470
        ov.setGeometry((cw.width() - ow) // 2, (cw.height() - oh) // 2, ow, oh)
        ov.done.connect(self._on_setup_done)
        ov.show()
        self._overlay = ov

    def _on_setup_done(self, key: str, os_name: str, theme_id: str = ""):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        API_FILE.write_text(json.dumps({"gemini_api_key": key, "os_system": os_name}, indent=4), encoding="utf-8")
        if theme_id:
            try: save_theme_name(theme_id)
            except Exception: pass
        self._ready = True
        if self._overlay:
            self._overlay.hide()
            self._overlay = None
        self._apply_state("ESCUCHANDO")
        self._log.append_log(f"SISTEMA: Inicializado. SO={os_name.upper()}. ORION en línea.")


# ============================================================
#  Capa de compatibilidad / API pública
# ============================================================
class _RootShim:
    def __init__(self, app: QApplication, win: MainWindow):
        self._app = app
        self._win = win
    def mainloop(self): self._app.exec()
    def protocol(self, *_): pass
    def quit(self): self._win._quit_app()


class OrionUI:
    """Clase principal de la interfaz de O.R.I.O.N."""

    def __init__(self, face_path: str, size=None):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self._win = MainWindow(face_path)
        self._win.show()
        self.root = _RootShim(self._app, self._win)

    @property
    def muted(self) -> bool: return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if v != self._win._muted: self._win._toggle_mute()

    @property
    def current_file(self) -> str | None: return self._win._drop_zone.current_file()

    @property
    def current_files(self) -> list[str]: return self._win._drop_zone.current_files()

    @property
    def on_text_command(self): return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb): self._win.on_text_command = cb

    @property
    def on_interrupt(self): return self._win.on_interrupt

    @on_interrupt.setter
    def on_interrupt(self, cb): self._win.on_interrupt = cb

    def set_state(self, state: str): self._win._state_sig.emit(state)

    def write_log(self, text: str): self._win._log_sig.emit(text)

    def wait_for_api_key(self):
        while not self._win._ready: time.sleep(0.1)

    def start_speaking(self): self.set_state("HABLANDO")

    def stop_speaking(self):
        if not self.muted: self.set_state("ESCUCHANDO")

    def notes_changed(self) -> None:
        """Notifica que el panel de notas debe refrescar.

        Encapsula el reach-in previo de ``main.py`` a ``_win._notes_panel``
        (auditoría R-02). Si el panel no está abierto, no hace nada.
        En modo web este método lo expone ``OrionEventBus`` como evento WS.
        """
        try:
            panel = getattr(self._win, "_notes_panel", None)
            if panel is not None and panel.isVisible():
                # El refresh debe ocurrir en el thread Qt principal.
                QTimer.singleShot(0, panel.reload)
        except Exception:
            pass