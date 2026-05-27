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
            # Si está en hover, aplicar un poco de opacidad menor al fondo
            # y dibujamos la imagen tal cual (es blanca sobre cualquier fondo)
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

_DEFAULT_W, _DEFAULT_H = 980, 700
_MIN_W,     _MIN_H     = 820, 580
_LEFT_W  = 158
_RIGHT_W = 350

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


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h); c.setAlpha(a); return c


# ============================================================
#  Métricas del sistema (CPU, RAM, GPU, RED, TEMP)
# ============================================================
class _SysMetrics:
    def __init__(self):
        self.cpu  = 0.0
        self.mem  = 0.0
        self.net  = 0.0
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
        # NVIDIA
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
        # Performance: pausar la animación cuando el widget no es visible
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

        # ── Esfera 3D de partículas ──
        # Cada partícula es un punto en una esfera, en coords esféricas (theta, phi).
        # La esfera completa rota sobre dos ejes; la velocidad cambia con el estado.
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
        self._orb_speed   = 0.18   # factor global de velocidad (0.18 reposo)
        self._orb_tgt_spd = 0.18

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(16)

    def set_paused(self, paused: bool) -> None:
        """Pausa la animación (cuando la ventana está minimizada/oculta)."""
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

        # ── Velocidad de la esfera 3D según el estado ──
        if self.state == "PENSANDO" or self.state == "PROCESANDO":
            self._orb_tgt_spd = 2.8      # giro rápido (pensando)
        elif self.speaking:
            self._orb_tgt_spd = 1.5      # giro medio (hablando)
        elif self.muted:
            self._orb_tgt_spd = 0.08     # casi quieto (mute)
        else:
            self._orb_tgt_spd = 0.35     # giro lento (escuchando/reposo)

        # suavizado
        self._orb_speed += (self._orb_tgt_spd - self._orb_speed) * 0.08

        # rotación global de la esfera
        self._orb_rot_x += 0.004 * self._orb_speed * 2.5
        self._orb_rot_y += 0.006 * self._orb_speed * 2.5

        # actualiza cada partícula
        for op in self._orb_particles:
            op["theta"]   += op["spd_theta"] * self._orb_speed * 3.0
            op["phi"]     += op["spd_phi"]   * self._orb_speed * 1.5
            op["pulse_t"] += op["pulse_spd"]

        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ---- Fondo radial sutil (más estético que un fill plano) ----
        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        rg = QRadialGradient(cx, cy, max(W, H) * 0.65)
        rg.setColorAt(0.0, qcol("#1a0410"))
        rg.setColorAt(0.55, qcol(C.BG))
        rg.setColorAt(1.0, qcol("#050103"))
        p.fillRect(self.rect(), QBrush(rg))

        fw = min(W, H)

        # puntos de cuadrícula
        p.setPen(QPen(qcol(C.PRI_GHO), 1))
        for x in range(0, W, 48):
            for y in range(0, H, 48):
                p.drawPoint(x, y)

        r_face = fw * 0.31

        # halo
        for i in range(10):
            r   = r_face * (1.8 - i * 0.08)
            frc = 1.0 - i / 10
            a   = max(0, min(255, int(self._halo * 0.085 * frc)))
            col = qcol(C.MUTED_C if self.muted else C.PRI, a)
            p.setPen(QPen(col, 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # anillos de pulso
        for pr in self._pulses:
            a   = max(0, int(230 * (1.0 - pr / (fw * 0.74))))
            col = qcol(C.MUTED_C if self.muted else C.PRI, a)
            p.setPen(QPen(col, 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - pr, cy - pr, pr * 2, pr * 2))

        # anillos giratorios
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

        # scanners
        sr = fw * 0.50
        sa = min(255, int(self._halo * 1.5))
        ex = 75 if self.speaking else 44
        p.setPen(QPen(qcol(C.MUTED_C if self.muted else C.PRI, sa), 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        srect = QRectF(cx - sr, cy - sr, sr * 2, sr * 2)
        p.drawArc(srect, int(self._scan * 16), int(ex * 16))
        p.setPen(QPen(qcol(C.ACC, sa // 2), 1.5))
        p.drawArc(srect, int(self._scan2 * 16), int(ex * 16))

        # marcas de tick
        t_out, t_in = fw * 0.497, fw * 0.474
        p.setPen(QPen(qcol(C.PRI, 140), 1))
        for deg in range(0, 360, 10):
            rad = math.radians(deg)
            inn = t_in if deg % 30 == 0 else t_in + 6
            p.drawLine(
                QPointF(cx + t_out * math.cos(rad), cy - t_out * math.sin(rad)),
                QPointF(cx + inn  * math.cos(rad), cy - inn  * math.sin(rad)),
            )

        # cruz
        ch_r, gap_h = fw * 0.51, fw * 0.16
        p.setPen(QPen(qcol(C.PRI, int(self._halo * 0.5)), 1))
        p.drawLine(QPointF(cx - ch_r, cy), QPointF(cx - gap_h, cy))
        p.drawLine(QPointF(cx + gap_h, cy), QPointF(cx + ch_r, cy))
        p.drawLine(QPointF(cx, cy - ch_r), QPointF(cx, cy - gap_h))
        p.drawLine(QPointF(cx, cy + gap_h), QPointF(cx, cy + ch_r))

        # corchetes esquinas
        bl = 24
        bc = qcol(C.PRI, 210)
        hl, hr = cx - fw // 2, cx + fw // 2
        ht, hb = cy - fw // 2, cy + fw // 2
        p.setPen(QPen(bc, 2))
        for bx, by, dx, dy in [(hl,ht,1,1),(hr,ht,-1,1),(hl,hb,1,-1),(hr,hb,-1,-1)]:
            p.drawLine(QPointF(bx, by), QPointF(bx + dx * bl, by))
            p.drawLine(QPointF(bx, by), QPointF(bx, by + dy * bl))

        # ── Esfera 3D de partículas ──
        # Paleta del tema activo
        orb_colors = C.ORB_MUTED if self.muted else C.ORB_ACTIVE

        # Color del halo derivado del primer color del orb
        halo_rgb = orb_colors[0]

        orb_radius = fw * 0.22 * self._scale
        cos_y = math.cos(self._orb_rot_y); sin_y = math.sin(self._orb_rot_y)
        cos_x = math.cos(self._orb_rot_x); sin_x = math.sin(self._orb_rot_x)

        # halo central detrás de la esfera (un brillo difuso)
        halo_r = orb_radius * 1.05
        halo_gr = QRadialGradient(QPointF(cx, cy), halo_r)
        halo_gr.setColorAt(0.0, QColor(halo_rgb[0], halo_rgb[1], halo_rgb[2], 110 if not self.muted else 90))
        halo_gr.setColorAt(0.55, QColor(halo_rgb[0], halo_rgb[1], halo_rgb[2], 40))
        halo_gr.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(halo_gr)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), halo_r, halo_r)

        # proyección 3D de las partículas y dibujado
        rendered: list[tuple[float, float, float, float, float, tuple]] = []
        for op in self._orb_particles:
            theta = op["theta"]; phi = op["phi"]
            x3 = orb_radius * math.sin(phi) * math.cos(theta)
            y3 = orb_radius * math.sin(phi) * math.sin(theta)
            z3 = orb_radius * math.cos(phi)

            # rotación Y luego X
            xR = x3 * cos_y - z3 * sin_y
            zR = x3 * sin_y + z3 * cos_y
            yR = y3 * cos_x - zR * sin_x
            zF = y3 * sin_x + zR * cos_x

            # escala de profundidad (0..1) — más al frente = más grande/brillante
            depth = (zF + orb_radius) / (orb_radius * 2)
            depth = max(0.0, min(1.0, depth))

            size  = (op["base_size"] + math.sin(op["pulse_t"]) * 0.5) * (0.4 + depth * 1.2)
            alpha = 0.15 + depth * 0.85
            col   = orb_colors[op["color_idx"]]

            rendered.append((cx + xR, cy + yR, zF, size, alpha, col))

        # ordenar por Z (más al fondo primero) para que las del frente queden encima
        rendered.sort(key=lambda t: t[2])

        for x, y, z, size, alpha, col in rendered:
            # destello exterior
            glow_r = size * 4.0
            gr = QRadialGradient(QPointF(x, y), glow_r)
            gr.setColorAt(0.0, QColor(col[0], col[1], col[2], int(alpha * 200)))
            gr.setColorAt(0.35, QColor(col[0], col[1], col[2], int(alpha * 60)))
            gr.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setBrush(QBrush(gr)); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x, y), glow_r, glow_r)

            # núcleo brillante
            core_a = int(min(255, alpha * 230))
            p.setBrush(QBrush(QColor(255, 245, 230, core_a)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x, y), size, size)

        # partículas
        for pt in self._particles:
            a = max(0, min(255, int(pt[4] * 255)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(qcol(C.PRI, a)))
            p.drawEllipse(QPointF(pt[0], pt[1]), 2.5, 2.5)

        # texto de estado
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

        # forma de onda
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
        self._value = 0.0       # 0–100
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

        # Fondo con un degradado sutil para que se vea más pulido
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

        # fondo de la barra
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
            # degradado de la barra rellena
            gb = QLinearGradient(bar_x, 0, bar_x + fill_w, 0)
            gb.setColorAt(0.0, bar_col)
            light = QColor(bar_col); light.setAlpha(180)
            gb.setColorAt(1.0, light)
            p.setBrush(QBrush(gb))
            p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 2, 2)

        # etiqueta
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_MED), 1))
        p.drawText(QRectF(9, 5, 60, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._label)

        # valor numérico
        p.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        p.setPen(QPen(bar_col if self._text != "--" else qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, 4, W - 8, 16),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._text)


# ============================================================
#  Widget de log con efecto máquina de escribir
# ============================================================
class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)
    # Señal emitida cuando el usuario suelta contenido en el log
    dropped_text = pyqtSignal(str)     # texto plano o link
    dropped_file = pyqtSignal(str)     # ruta absoluta a un archivo

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
                border-radius: 5px;
                padding: 7px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG};
                width: 8px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B};
                border-radius: 4px;
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
        # Límite de líneas visibles para evitar fuga de memoria en sesiones largas
        self.document().setMaximumBlockCount(500)
        # Tamaño máximo de la cola de mensajes pendientes
        self._max_queue = 200
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._sig.connect(self._enqueue)

    def append_log(self, text: str):
        self._sig.emit(text)

    def _enqueue(self, text: str):
        # Ring buffer: si la cola está llena, descarta los más viejos
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
        self._text   = self._queue.pop(0)
        self._pos    = 0
        tl = self._text.lower()
        if   tl.startswith("tú:") or tl.startswith("tu:"): self._tag = "you"
        elif tl.startswith("orion:"):                       self._tag = "ai"
        elif tl.startswith("archivo:"):                     self._tag = "file"
        elif tl.startswith("sistema:") or tl.startswith("sys:"): self._tag = "sys"
        elif "error" in tl or "err" in tl:                  self._tag = "err"
        else:                                               self._tag = "sys"
        # Performance: si hay muchos mensajes acumulados, omitir la animación
        # de máquina de escribir y volcar el texto de golpe.
        if len(self._queue) > 5:
            self._flush_instant()
        else:
            self._tmr.start(6)

    def _flush_instant(self):
        cur = self.textCursor()
        fmt = cur.charFormat()
        col = {
            "you":  qcol(C.WHITE),
            "ai":   qcol(C.PRI),
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
                "ai":   qcol(C.PRI),
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

    # ── Drag & Drop ─────────────────────────────────────────────────────
    def dragEnterEvent(self, e):
        mime = e.mimeData()
        if mime.hasUrls() or mime.hasText() or mime.hasImage():
            e.acceptProposedAction()
            # Resaltado visual del log
            self.setStyleSheet(self.styleSheet() +
                f"\nQTextEdit {{ border: 1px solid {C.PRI}; }}")
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        # Re-aplicar estilo base
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
                border-radius: 5px;
                padding: 7px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG};
                width: 8px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B};
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {C.PRI_DIM};
            }}
        """)

    def dropEvent(self, e):
        mime = e.mimeData()
        self._reset_border()

        # 1) Archivo local
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    if Path(path).is_file():
                        self.dropped_file.emit(path)
                        e.acceptProposedAction()
                        return
                # Si es URL web, enviarla como texto
                if url.scheme() in ("http", "https"):
                    self.dropped_text.emit(url.toString())
                    e.acceptProposedAction()
                    return

        # 2) Texto plano
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
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(100)
        self._current_file: str | None = None
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
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_file():
                self._set_file(path)
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

    def clear_file(self):
        self._current_file = None; self._canvas.update()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar archivo para ORION", str(Path.home()),
            "Todos los archivos (*.*);;"
            "Imágenes (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documentos (*.pdf *.docx *.txt *.md *.pptx);;"
            "Datos (*.csv *.xlsx *.json *.xml);;"
            "Código (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archivos comprimidos (*.zip *.rar *.tar *.gz *.7z)",
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        self._canvas.update()
        self.file_selected.emit(path)


class _DropCanvas(QWidget):
    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z    = self._z
        W, H = self.width(), self.height()
        pad  = 6
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        bg_col = qcol("#220612" if z._drag_over else ("#1a0410" if z._hovering else C.PANEL))
        p.setBrush(QBrush(bg_col)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 7, 7)

        if z._current_file:   border_col = qcol(C.GREEN, 200)
        elif z._drag_over:    border_col = qcol(C.PRI, 230)
        elif z._hovering:     border_col = qcol(C.BORDER_B, 200)
        else:                 border_col = qcol(C.BORDER, 160)

        pen = QPen(border_col, 1.5, Qt.PenStyle.DashLine)
        pen.setDashOffset(z._dash_offset)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 7, 7)

        if z._current_file:   self._paint_file(p, W, H)
        elif z._drag_over:    self._paint_drag_over(p, W, H)
        else:                 self._paint_idle(p, W, H, z._hovering)

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2
        col = qcol(C.PRI_DIM if not hover else C.PRI)
        p.setPen(QPen(col, 2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx, cy - 14), QPointF(cx, cy + 4))
        p.drawLine(QPointF(cx - 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx + 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx - 14, cy + 4), QPointF(cx + 14, cy + 4))
        p.setFont(QFont("Courier New", 8))
        p.setPen(QPen(qcol(C.PRI_DIM if not hover else C.TEXT), 1))
        p.drawText(QRectF(0, cy + 8, W, 16), Qt.AlignmentFlag.AlignCenter,
                   "Suelta un archivo aquí  o  haz clic para buscar")
        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol("#5a1a2a"), 1))
        p.drawText(QRectF(0, cy + 24, W, 14), Qt.AlignmentFlag.AlignCenter,
                   "Imágenes · Video · Audio · PDF · Documentos · Código · Datos")

    def _paint_drag_over(self, p, W, H):
        cx, cy = W / 2, H / 2
        p.setFont(QFont("Courier New", 20))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy - 24, W, 32), Qt.AlignmentFlag.AlignCenter, "⬇")
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy + 12, W, 16), Qt.AlignmentFlag.AlignCenter,
                   "Suelta para cargar el archivo")

    def _paint_file(self, p, W, H):
        path = Path(self._z._current_file)
        cat  = _file_category(path)
        icon, icon_col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size_str = _fmt_size(path.stat().st_size)
        ext_str  = path.suffix.upper().lstrip(".") or "ARCHIVO"

        block_x, block_w = 10, 60
        p.setFont(QFont("Segoe UI Emoji", 22) if _OS == "Windows" else QFont("Arial", 22))
        p.setPen(QPen(qcol(icon_col), 1))
        p.drawText(QRectF(block_x, 0, block_w, H), Qt.AlignmentFlag.AlignCenter, icon)

        tx = block_x + block_w + 6
        tw = W - tx - 38

        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.WHITE), 1))
        name = path.name if len(path.name) <= 34 else path.name[:31] + "..."
        p.drawText(QRectF(tx, H * 0.18, tw, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(tx, H * 0.18 + 18, tw, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{ext_str}  ·  {size_str}")

        p.setFont(QFont("Courier New", 6))
        p.setPen(QPen(qcol("#5c1a26"), 1))
        par = str(path.parent)
        if len(par) > 42: par = "…" + par[-41:]
        p.drawText(QRectF(tx, H * 0.18 + 34, tw, 12),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, par)

        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.RED, 200), 1))
        p.drawText(QRectF(W - 34, 0, 28, H), Qt.AlignmentFlag.AlignCenter, "✕")

    def mousePressEvent(self, e):
        z = self._z
        if z._current_file and e.pos().x() > self.width() - 34:
            z.clear_file()
        else:
            z.mousePressEvent(e)


# ============================================================
#  Panel de memoria — ver y editar long_term.json
# ============================================================
class MemoryPanel(QWidget):
    """Ventana modal que muestra las categorías de memoria con edición."""

    memory_changed = pyqtSignal()

    _CATEGORIES = [
        ("identity",      "Identidad",     "#ff2a4d"),
        ("preferences",   "Preferencias",  "#ffb84d"),
        ("projects",      "Proyectos",     "#33ff99"),
        ("relationships", "Relaciones",    "#ff6b1a"),
        ("wishes",        "Deseos",        "#cc44ff"),
        ("notes",         "Notas",         "#aaaaaa"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowTitle("O.R.I.O.N — Memoria")
        self.setMinimumSize(560, 480)
        self.resize(640, 540)
        self.setStyleSheet(f"background: {C.BG};")

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        # Header
        hdr = QLabel("◈  MEMORIA DE O.R.I.O.N")
        hdr.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        hdr.setStyleSheet(
            f"color: {C.PRI}; background: transparent; "
            f"border-bottom: 1px solid {C.BORDER_B}; padding-bottom: 6px;"
        )
        root.addWidget(hdr)

        sub = QLabel("Lo que ORION recuerda de ti. Edita o borra cualquier entrada.")
        sub.setFont(QFont("Courier New", 8))
        sub.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        root.addWidget(sub)

        # Área scrollable de entradas
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

        # Pie con botones
        footer = QHBoxLayout()
        footer.setSpacing(6)

        refresh_btn = QPushButton("⟳  Recargar")
        refresh_btn.setFixedHeight(28)
        refresh_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 4px;
                padding: 0 14px;
            }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.PRI}; }}
        """)
        refresh_btn.clicked.connect(self.reload)
        footer.addWidget(refresh_btn)

        footer.addStretch()

        close_btn = QPushButton("Cerrar")
        close_btn.setFixedHeight(28)
        close_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 4px;
                padding: 0 18px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
        """)
        close_btn.clicked.connect(self.close)
        footer.addWidget(close_btn)

        root.addLayout(footer)

        self.reload()

    def reload(self):
        """Lee long_term.json y reconstruye la vista."""
        # Limpiar layout
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
            err.setStyleSheet(f"color: {C.RED};")
            self._content_lay.addWidget(err)
            return

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

    def _build_section(self, cat_id: str, cat_name: str, color: str, entries: dict) -> QWidget:
        wrap = QWidget()
        wrap.setStyleSheet(
            f"background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 5px;"
        )
        v = QVBoxLayout(wrap)
        v.setContentsMargins(10, 8, 10, 10)
        v.setSpacing(6)

        # Cabecera de la sección
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
            lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
            v.addWidget(lbl)
            return wrap

        for key, entry in entries.items():
            val = entry.get("value", "") if isinstance(entry, dict) else str(entry)
            updated = entry.get("updated", "") if isinstance(entry, dict) else ""
            v.addLayout(self._build_entry_row(cat_id, key, val, updated))

        return wrap

    def _build_entry_row(self, cat_id: str, key: str, value: str, updated: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)

        key_lbl = QLabel(key)
        key_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        key_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
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


# ============================================================
#  Ventana de modo compacto (Picture-in-Picture)
# ============================================================
class CompactWindow(QMainWindow):
    """Ventana flotante always-on-top con solo el HUD del orb.
    Permite mantener ORION visible mientras se trabaja en otra app.

    Soporta:
      - Mover arrastrando desde el área del HUD.
      - Redimensionar arrastrando cualquier borde o esquina con el mouse.
    """

    restore_requested = pyqtSignal()

    # Tamaño del borde sensible al resize (en px)
    _RESIZE_MARGIN = 6

    # Flags internos para resize
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
        # Tamaño inicial + límites en lugar de fijo
        self.resize(240, 280)
        self.setMinimumSize(180, 220)
        self.setMaximumSize(900, 900)
        self.setWindowTitle("O.R.I.O.N — Compacto")
        # Mover el seguimiento de mouse para detectar el cursor sobre bordes
        self.setMouseTracking(True)

        central = QWidget()
        central.setMouseTracking(True)
        self.setCentralWidget(central)

        lay = QVBoxLayout(central)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(2)

        # Barra superior con título y botones (área de "drag")
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

        # HUD redimensionable
        self.hud = HudCanvas(face_path)
        self.hud.setMinimumSize(150, 150)
        self.hud.setMouseTracking(True)
        lay.addWidget(self.hud, stretch=1)

        # Pequeña "esquina" visual de resize en la esquina inferior derecha
        self._resize_hint = QLabel("⤡")
        self._resize_hint.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        self._resize_hint.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self._resize_hint.setStyleSheet(
            f"color: {C.TEXT_DIM}; background: transparent; padding-right: 2px;"
        )
        self._resize_hint.setFixedHeight(12)
        self._resize_hint.setMouseTracking(True)
        lay.addWidget(self._resize_hint)

        # Borde sutil alrededor de la ventana
        central.setStyleSheet(
            f"QWidget {{ background: {C.BG}; }}"
            f"QWidget#wrap {{ border: 1px solid {C.BORDER_B}; border-radius: 6px; }}"
        )
        central.setObjectName("wrap")

        # Estado interno para mover/redimensionar
        self._drag_pos: QPoint | None = None
        self._resize_edge: int = self._RESIZE_NONE
        self._resize_start_geom = None
        self._resize_start_mouse = None

    # Sincronización de estado con la ventana principal
    def set_state(self, state: str):
        self.hud.state    = state
        self.hud.speaking = (state == "HABLANDO")

    def set_muted(self, muted: bool):
        self.hud.muted = muted

    # ── Detección del borde bajo el cursor ──────────────────────────────
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
        if edge == (self._RESIZE_LEFT | self._RESIZE_TOP) or \
           edge == (self._RESIZE_RIGHT | self._RESIZE_BOT):
            return Qt.CursorShape.SizeFDiagCursor
        if edge == (self._RESIZE_RIGHT | self._RESIZE_TOP) or \
           edge == (self._RESIZE_LEFT | self._RESIZE_BOT):
            return Qt.CursorShape.SizeBDiagCursor
        if edge & (self._RESIZE_LEFT | self._RESIZE_RIGHT):
            return Qt.CursorShape.SizeHorCursor
        if edge & (self._RESIZE_TOP | self._RESIZE_BOT):
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    # ── Eventos de mouse ────────────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            edge = self._edge_at(e.position().toPoint())
            if edge != self._RESIZE_NONE:
                # Iniciar redimensionado
                self._resize_edge = edge
                self._resize_start_geom = self.geometry()
                self._resize_start_mouse = e.globalPosition().toPoint()
                e.accept()
                return
            # Solo mover si el clic fue en la barra superior o el HUD
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        # Si está en proceso de redimensionado
        if self._resize_edge != self._RESIZE_NONE and (e.buttons() & Qt.MouseButton.LeftButton):
            self._do_resize(e.globalPosition().toPoint())
            e.accept()
            return
        # Si está moviendo la ventana
        if self._drag_pos is not None and (e.buttons() & Qt.MouseButton.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()
            return
        # Si no, solo actualizar cursor según borde
        edge = self._edge_at(pos)
        self.setCursor(self._cursor_for_edge(edge))

    def mouseReleaseEvent(self, e):
        self._drag_pos = None
        self._resize_edge = self._RESIZE_NONE
        self._resize_start_geom = None
        self._resize_start_mouse = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def _do_resize(self, global_pos: QPoint):
        if self._resize_start_geom is None or self._resize_start_mouse is None:
            return
        dx = global_pos.x() - self._resize_start_mouse.x()
        dy = global_pos.y() - self._resize_start_mouse.y()
        g = self._resize_start_geom
        x, y, w, h = g.x(), g.y(), g.width(), g.height()
        min_w = self.minimumWidth()
        min_h = self.minimumHeight()
        max_w = self.maximumWidth()
        max_h = self.maximumHeight()

        if self._resize_edge & self._RESIZE_RIGHT:
            w = max(min_w, min(max_w, w + dx))
        if self._resize_edge & self._RESIZE_BOT:
            h = max(min_h, min(max_h, h + dy))
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
        # Al cerrar el compacto, restaurar la principal
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
        self.setStyleSheet(f"""
            SetupOverlay {{
                background: rgba(10, 2, 5, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 8px;
            }}
        """)

        detected = {"darwin": "mac", "windows": "windows"}.get(
            _OS.lower(), "linux"
        )
        self._sel_os = detected

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 22, 30, 22)
        layout.setSpacing(8)

        def _lbl(txt, font_size=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont("Courier New", font_size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        layout.addWidget(_lbl("◈  CONFIGURACIÓN REQUERIDA", 13, True))
        layout.addWidget(_lbl("Configura ORION antes del primer inicio.", 9, color=C.PRI_DIM))
        layout.addSpacing(6)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep)
        layout.addSpacing(4)

        layout.addWidget(_lbl("CLAVE API DE GEMINI", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("AIza…")
        self._key_input.setFont(QFont("Courier New", 10))
        self._key_input.setFixedHeight(32)
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background: #15040a; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 4px; padding: 4px 8px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        layout.addWidget(self._key_input)
        layout.addSpacing(12)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep2)
        layout.addSpacing(4)

        layout.addWidget(_lbl("SISTEMA OPERATIVO", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        det_name = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}[detected]
        layout.addWidget(_lbl(f"Detectado automáticamente: {det_name}", 8, color=C.ACC2,
                               align=Qt.AlignmentFlag.AlignLeft))

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
        init_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 4px;
            }}
            QPushButton:hover {{
                background: {C.PRI_GHO}; border: 1px solid {C.PRI};
            }}
        """)
        init_btn.clicked.connect(self._submit)
        layout.addWidget(init_btn)

    def _sel(self, key: str):
        self._sel_os = key
        pal = {"windows":(C.PRI,"#220612"),"mac":(C.ACC2,"#221400"),"linux":(C.GREEN,"#001a0d")}
        for k, btn in self._os_btns.items():
            if k == key:
                fg, bg = pal[k]
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {fg}; color: {bg};
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

    def _submit(self):
        key = self._key_input.text().strip()
        if not key:
            self._key_input.setStyleSheet(
                self._key_input.styleSheet() +
                f" QLineEdit {{ border: 1px solid {C.RED}; }}"
            )
            return
        self.done.emit(key, self._sel_os)


# ============================================================
#  Ventana principal
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

        self.hud = HudCanvas(face_path)
        self.hud.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        body.addWidget(self.hud, stretch=5)

        self._right_panel = self._build_right_panel()
        body.addWidget(self._right_panel, stretch=0)

        root.addLayout(body, stretch=1)
        root.addWidget(self._build_footer())

        # Reloj
        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        # Métricas
        self._metric_tmr = QTimer(self)
        self._metric_tmr.timeout.connect(self._update_metrics)
        self._metric_tmr.start(2000)
        self._update_metrics()

        self._log_sig.connect(self._log.append_log)
        self._state_sig.connect(self._apply_state)

        self._overlay: SetupOverlay | None = None
        self._ready = self._check_config()
        if not self._ready:
            self._show_setup()

        sc_mute = QShortcut(QKeySequence("F4"), self)
        sc_mute.activated.connect(self._toggle_mute)
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)

        sc_compact = QShortcut(QKeySequence("F9"), self)
        sc_compact.activated.connect(self._toggle_compact_mode)

        # Path para crear la ventana compacta más tarde (lazy init)
        self._face_path = face_path
        self._compact_window: CompactWindow | None = None
        self._memory_panel: "MemoryPanel | None" = None

        # ── System Tray ──
        self._setup_tray()

        # ── Global Hotkeys ──
        self._hotkeys = _load_hotkeys()
        self._setup_global_hotkeys()

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    # ── Panel de memoria ─────────────────────────────────────────────────
    def _show_memory_panel(self):
        if not hasattr(self, "_memory_panel") or self._memory_panel is None:
            self._memory_panel = MemoryPanel(self)
            self._memory_panel.memory_changed.connect(
                lambda: self._log.append_log("SISTEMA: Memoria actualizada.")
            )
        self._memory_panel.reload()
        self._memory_panel.show()
        self._memory_panel.raise_()
        self._memory_panel.activateWindow()

    # ── Modo compacto (PiP) ──────────────────────────────────────────────
    def _toggle_compact_mode(self):
        if self._compact_window and self._compact_window.isVisible():
            self._close_compact()
            return

        if self._compact_window is None:
            self._compact_window = CompactWindow(self._face_path)
            self._compact_window.restore_requested.connect(self._close_compact)
            # Sincronizar estado actual
            self._state_sig.connect(self._compact_window.set_state)
            self._compact_window.set_muted(self._muted)
            self._compact_window.set_state(self.hud.state)

        # Posicionar en la esquina inferior derecha de la pantalla
        screen = QApplication.primaryScreen().availableGeometry()
        cw = self._compact_window
        cw.move(
            screen.right() - cw.width() - 20,
            screen.bottom() - cw.height() - 20,
        )
        cw.show()
        cw.raise_()
        # Ocultar la principal
        self.hide()

    def _close_compact(self):
        if self._compact_window:
            self._compact_window.hide()
        self.showNormal()
        self.activateWindow()
        self.raise_()

    # ── Selector de tema ─────────────────────────────────────────────────
    def _show_theme_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {C.DARK}; color: {C.TEXT};
                border: 1px solid {C.BORDER_B}; padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 24px; font-family: 'Courier New'; font-size: 9pt;
            }}
            QMenu::item:selected {{
                background: {C.PRI_GHO}; color: {C.PRI};
            }}
            QMenu::separator {{ height: 1px; background: {C.BORDER}; margin: 4px 0; }}
        """)

        title = QAction("◈  ELEGIR TEMA", self)
        title.setEnabled(False)
        menu.addAction(title)
        menu.addSeparator()

        current = load_theme_name()
        group = QActionGroup(self)
        group.setExclusive(True)

        for theme_id, theme_name in list_themes():
            act = QAction(("● " if theme_id == current else "  ") + theme_name, self)
            act.setCheckable(True)
            act.setChecked(theme_id == current)
            act.triggered.connect(lambda _, t=theme_id: self._apply_theme_choice(t))
            group.addAction(act)
            menu.addAction(act)

        menu.addSeparator()
        info = QAction("Reinicia ORION para aplicar", self)
        info.setEnabled(False)
        menu.addAction(info)

        # Mostrar bajo el botón
        if hasattr(self, "_theme_btn"):
            pos = self._theme_btn.mapToGlobal(QPoint(0, self._theme_btn.height()))
            menu.exec(pos)
        else:
            menu.exec(self.cursor().pos())

    def _apply_theme_choice(self, theme_id: str):
        save_theme_name(theme_id)
        self._log.append_log(
            f"SISTEMA: Tema cambiado a '{theme_id}'. Reinicia ORION para aplicar."
        )
        if hasattr(self, "_tray"):
            self._tray.showMessage(
                "O.R.I.O.N — Tema",
                f"Tema cambiado a '{theme_id}'. Reinicia para aplicar.",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )

    # ── Pausar animaciones cuando se minimiza ────────────────────────────
    def changeEvent(self, event):
        from PyQt6.QtCore import QEvent
        if event.type() == QEvent.Type.WindowStateChange:
            paused = self.isMinimized()
            if hasattr(self, "hud"):
                self.hud.set_paused(paused)
            # Reducir frecuencia de actualización de métricas al minimizar
            if hasattr(self, "_metric_tmr"):
                self._metric_tmr.setInterval(8000 if paused else 2000)
        super().changeEvent(event)

    # ── System Tray ──────────────────────────────────────────────────────
    def _setup_tray(self):
        self._tray = QSystemTrayIcon(self)

        icon_path = str(TRAY_ICON_PATH)
        if TRAY_ICON_PATH.exists():
            self._tray.setIcon(QIcon(icon_path))
        else:
            self._tray.setIcon(self.style().standardIcon(
                self.style().StandardPixmap.SP_ComputerIcon
            ))

        tray_menu = QMenu()
        tray_menu.setStyleSheet(f"""
            QMenu {{
                background: {C.DARK}; color: {C.TEXT};
                border: 1px solid {C.BORDER_B};
            }}
            QMenu::item:selected {{
                background: {C.PRI_GHO}; color: {C.PRI};
            }}
        """)

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
        self._tray.setToolTip("O.R.I.O.N — Asistente IA")
        self._tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._tray_show()

    def _tray_show(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _quit_app(self):
        self._really_quit = True
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        try:
            if hasattr(self, "_clock_tmr"):
                self._clock_tmr.stop()
            if hasattr(self, "_metric_tmr"):
                self._metric_tmr.stop()
        except Exception:
            pass
        if self._compact_window:
            self._compact_window.close()
        self._tray.hide()
        QApplication.quit()

    # ── Global Hotkeys ───────────────────────────────────────────────────
    def _setup_global_hotkeys(self):
        hk = self._hotkeys
        try:
            keyboard.add_hotkey(
                hk.get("toggle_microphone", "ctrl+\\"),
                self._global_toggle_mic,
                suppress=False,
            )
        except Exception as e:
            print(f"[ORION] Hotkey toggle_microphone falló: {e}")
        try:
            keyboard.add_hotkey(
                hk.get("show_window", "ctrl+shift+o"),
                self._global_show_window,
                suppress=False,
            )
        except Exception as e:
            print(f"[ORION] Hotkey show_window falló: {e}")

    def _global_toggle_mic(self):
        QTimer.singleShot(0, self._toggle_mute)

    def _global_show_window(self):
        QTimer.singleShot(0, self._tray_show)

    # ── Close Event (minimize to tray + mute mic) ────────────────────────
    def closeEvent(self, event):
        if getattr(self, "_really_quit", False):
            try:
                keyboard.unhook_all()
            except Exception:
                pass
            try:
                if hasattr(self, "_clock_tmr"):
                    self._clock_tmr.stop()
                if hasattr(self, "_metric_tmr"):
                    self._metric_tmr.stop()
            except Exception:
                pass
            super().closeEvent(event)
            return

        event.ignore()
        self.hide()

        if not self._muted:
            self._toggle_mute()

        hotkey_str = self._hotkeys.get("toggle_microphone", "ctrl+\\")
        self._tray.showMessage(
            "O.R.I.O.N",
            f"Minimizado a la bandeja. Mic apagado.\nUsa {hotkey_str} para activar el mic.",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._overlay and self._overlay.isVisible():
            ow, oh = 460, 390
            cw = self.centralWidget()
            self._overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )

    def _update_metrics(self):
        snap = _metrics.snapshot()

        # CPU
        cpu = snap["cpu"]
        self._bar_cpu.set_value(cpu, f"{cpu:.0f}%")

        # MEM
        mem = snap["mem"]
        self._bar_mem.set_value(mem, f"{mem:.0f}%")

        # NET
        net = snap["net"]
        if net < 1.0:
            net_str = f"{net*1024:.0f}KB/s"
        else:
            net_str = f"{net:.1f}MB/s"
        net_pct = min(100, net * 10)  # 10 MB/s = 100%
        self._bar_net.set_value(net_pct, net_str)

        # GPU
        gpu = snap["gpu"]
        if gpu >= 0:
            self._bar_gpu.set_value(gpu, f"{gpu:.0f}%")
        else:
            self._bar_gpu.set_value(0, "N/D")

        # TMP
        tmp = snap["tmp"]
        if tmp >= 0:
            tmp_pct = min(100, (tmp / 100) * 100)
            self._bar_tmp.set_value(tmp_pct, f"{tmp:.0f}°C")
        else:
            self._bar_tmp.set_value(0, "N/D")

        # Tiempo encendido
        try:
            boot_t  = psutil.boot_time()
            elapsed = time.time() - boot_t
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            self._uptime_lbl.setText(f"ENCENDIDO  {h:02d}:{m:02d}")
        except Exception:
            self._uptime_lbl.setText("ENCENDIDO  --:--")

        # Procesos
        try:
            proc_count = len(psutil.pids())
            self._proc_lbl.setText(f"PROCESOS  {proc_count}")
        except Exception:
            self._proc_lbl.setText("PROCESOS  --")

    # --------- Encabezado ---------
    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(56)
        w.setStyleSheet(f"background: {C.DARK}; border-bottom: 1px solid {C.BORDER_B};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(18, 0, 18, 0)

        def _badge(txt, color=C.TEXT_MED):
            l = QLabel(txt)
            l.setFont(QFont("Courier New", 8))
            l.setStyleSheet(f"color: {color}; background: transparent;")
            return l

        gh_btn = GitHubButton(GITHUB_URL)
        lay.addWidget(gh_btn)
        lay.addSpacing(8)
        lay.addWidget(_badge("Versión 1.0", C.PRI_DIM))
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
        # Fecha en español (independiente del locale del sistema)
        t = time.localtime()
        dia_sem  = _DIAS_ES[t.tm_wday]
        mes_es   = _MESES_ES[t.tm_mon - 1]
        self._date_lbl.setText(f"{dia_sem} {t.tm_mday:02d} {mes_es} {t.tm_year}")

    # --------- Panel izquierdo (monitor del sistema) ---------
    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_LEFT_W)
        w.setStyleSheet(f"background: {C.DARK}; border-right: 1px solid {C.BORDER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(9, 11, 9, 11)
        lay.setSpacing(7)

        hdr = QLabel("◈  MONITOR DEL SISTEMA")
        hdr.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent; "
                          f"border-bottom: 1px solid {C.BORDER}; padding-bottom: 5px;")
        lay.addWidget(hdr)
        lay.addSpacing(3)

        self._bar_cpu = MetricBar("CPU", C.PRI)
        self._bar_mem = MetricBar("MEM", C.ACC2)
        self._bar_net = MetricBar("RED", C.GREEN)
        self._bar_gpu = MetricBar("GPU", C.ACC)
        self._bar_tmp = MetricBar("TEMP", "#ff7799")

        for bar in [self._bar_cpu, self._bar_mem, self._bar_net,
                    self._bar_gpu, self._bar_tmp]:
            lay.addWidget(bar)

        lay.addSpacing(6)

        # Panel de información del sistema
        info_panel = QWidget()
        info_panel.setStyleSheet(
            f"background: {C.PANEL2}; border: 1px solid {C.BORDER};"
            f" border-radius: 5px;"
        )
        ip_lay = QVBoxLayout(info_panel)
        ip_lay.setContentsMargins(8, 7, 8, 7)
        ip_lay.setSpacing(4)

        info_hdr = QLabel("▸  INFORMACIÓN")
        info_hdr.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        info_hdr.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        ip_lay.addWidget(info_hdr)

        self._uptime_lbl = QLabel("ENCENDIDO  --:--")
        self._uptime_lbl.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        self._uptime_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent; border: none;")
        ip_lay.addWidget(self._uptime_lbl)

        self._proc_lbl = QLabel("PROCESOS  --")
        self._proc_lbl.setFont(QFont("Courier New", 7))
        self._proc_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        ip_lay.addWidget(self._proc_lbl)

        os_name = {"Windows": "WIN", "Darwin": "macOS", "Linux": "LINUX"}.get(_OS, _OS.upper())
        os_lbl = QLabel(f"SO  {os_name}")
        os_lbl.setFont(QFont("Courier New", 7))
        os_lbl.setStyleSheet(f"color: {C.ACC2}; background: transparent; border: none;")
        ip_lay.addWidget(os_lbl)

        lay.addWidget(info_panel)
        lay.addStretch()

        # Indicadores de estado al fondo
        for txt, col in [
            ("NÚCLEO IA\nACTIVO",      C.GREEN),
            ("SEGURIDAD\nVERIFICADA",  C.PRI),
        ]:
            lbl = QLabel(txt)
            lbl.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color: {col}; background: {C.PANEL2};"
                f" border: 1px solid {C.BORDER_A}; border-radius: 5px; padding: 5px;"
            )
            lay.addWidget(lbl)

        return w

    # --------- Panel derecho ---------
    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_RIGHT_W)
        w.setStyleSheet(f"background: {C.DARK}; border-left: 1px solid {C.BORDER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(9, 9, 9, 9)
        lay.setSpacing(7)

        def _sec(txt):
            l = QLabel(f"▸  {txt}")
            l.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
            l.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            return l

        lay.addWidget(_sec("REGISTRO DE ACTIVIDAD"))
        self._log = LogWidget()
        # Drag-and-drop: aceptar texto y archivos directamente en el log
        self._log.dropped_text.connect(self._on_log_drop_text)
        self._log.dropped_file.connect(self._on_file_selected)
        lay.addWidget(self._log, stretch=1)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        lay.addWidget(_sec("SUBIR ARCHIVO"))
        self._drop_zone = FileDropZone()
        self._drop_zone.file_selected.connect(self._on_file_selected)
        lay.addWidget(self._drop_zone)

        self._file_hint = QLabel("Sin archivos cargados. Arrastra y suelta un archivo aquí para cargarlo.")
        self._file_hint.setFont(QFont("Courier New", 7))
        self._file_hint.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._file_hint.setWordWrap(True)
        lay.addWidget(self._file_hint)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep2)

        lay.addWidget(_sec("COMANDOS"))
        lay.addLayout(self._build_input_row())

        # ── Botón INTERRUMPIR (visible solo cuando ORION habla) ──
        self._stop_btn = QPushButton("⏹  INTERRUMPIR")
        self._stop_btn.setFixedHeight(36)
        self._stop_btn.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.setToolTip("Detener la voz de ORION ahora")
        self._stop_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.RED}; color: {C.WHITE};
                border: 2px solid {C.RED}; border-radius: 5px;
                letter-spacing: 2px;
            }}
            QPushButton:hover {{
                background: #ff5577; border: 2px solid #ffffff;
            }}
            QPushButton:pressed {{
                background: #cc1133;
            }}
        """)
        self._stop_btn.clicked.connect(self._on_stop_clicked)
        self._stop_btn.hide()
        lay.addWidget(self._stop_btn)

        self._mute_btn = QPushButton("🎙  MICRÓFONO ACTIVO")
        self._mute_btn.setFixedHeight(32)
        self._mute_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.clicked.connect(self._toggle_mute)
        self._style_mute_btn()
        lay.addWidget(self._mute_btn)

        fs_btn = QPushButton("⛶  PANTALLA COMPLETA  [F11]")
        fs_btn.setFixedHeight(28)
        fs_btn.setFont(QFont("Courier New", 7))
        fs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fs_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 4px;
            }}
            QPushButton:hover {{
                color: {C.PRI}; border: 1px solid {C.BORDER_B};
                background: {C.PRI_GHO};
            }}
        """)
        fs_btn.clicked.connect(self._toggle_fullscreen)
        lay.addWidget(fs_btn)

        # Botón panel de memoria
        mem_btn = QPushButton("⚙  MEMORIA")
        mem_btn.setFixedHeight(28)
        mem_btn.setFont(QFont("Courier New", 7))
        mem_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        mem_btn.setToolTip("Ver y editar lo que ORION recuerda")
        mem_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 4px;
            }}
            QPushButton:hover {{
                color: {C.GREEN}; border: 1px solid {C.GREEN_D};
                background: {C.PRI_GHO};
            }}
        """)
        mem_btn.clicked.connect(self._show_memory_panel)
        lay.addWidget(mem_btn)

        # Botón modo compacto (PiP)
        compact_btn = QPushButton("◰  MODO COMPACTO  [F9]")
        compact_btn.setFixedHeight(28)
        compact_btn.setFont(QFont("Courier New", 7))
        compact_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        compact_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 4px;
            }}
            QPushButton:hover {{
                color: {C.PRI}; border: 1px solid {C.BORDER_B};
                background: {C.PRI_GHO};
            }}
        """)
        compact_btn.clicked.connect(self._toggle_compact_mode)
        lay.addWidget(compact_btn)

        # Selector de tema
        theme_btn = QPushButton(f"◈  TEMA: {get_theme()['name'].upper()}")
        theme_btn.setFixedHeight(28)
        theme_btn.setFont(QFont("Courier New", 7))
        theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        theme_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.ACC2};
                border: 1px solid {C.BORDER}; border-radius: 4px;
            }}
            QPushButton:hover {{
                color: {C.ACC}; border: 1px solid {C.BORDER_B};
                background: {C.PRI_GHO};
            }}
        """)
        theme_btn.clicked.connect(self._show_theme_menu)
        self._theme_btn = theme_btn
        lay.addWidget(theme_btn)

        return w

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(5)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Escribe un comando o pregunta…")
        self._input.setFont(QFont("Courier New", 9))
        self._input.setFixedHeight(32)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: #15040a; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 4px; padding: 3px 8px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input)

        send = QPushButton("▸")
        send.setFixedSize(32, 32)
        send.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 4px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
            QPushButton:pressed {{ background: {C.PRI}; color: {C.DARK}; }}
        """)
        send.clicked.connect(self._send)
        row.addWidget(send)
        return row

    # --------- Pie ---------
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

    # --------- Eventos ---------
    def _on_file_selected(self, path: str):
        self._current_file = path
        p    = Path(path)
        cat  = _file_category(p)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size = _fmt_size(p.stat().st_size)
        self._file_hint.setText(f"{icon}  {p.name}  ·  {size}  ·  Indica a ORION qué hacer con él")
        self._log.append_log(f"ARCHIVO: {p.name} ({size}) cargado")
        if self.on_text_command:
            msg = (
                f"[ARCHIVO_CARGADO] ruta={path} | nombre={p.name} | "
                f"tipo={p.suffix.lstrip('.')} | tamaño={size} | "
                f"Indica brevemente al usuario que puedes ver el archivo "
                f"'{p.name}' ({size}) y pregunta qué desea hacer con él."
            )
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def _toggle_mute(self):
        self._muted = not self._muted
        self.hud.muted = self._muted
        if self._compact_window:
            self._compact_window.set_muted(self._muted)
        self._style_mute_btn()
        if hasattr(self, "_tray_mic_action"):
            self._tray_mic_action.setText(
                "Activar Mic" if self._muted else "Silenciar Mic"
            )
        if self._muted:
            self._apply_state("SILENCIADO")
            self._log.append_log("SISTEMA: Micrófono silenciado.")
        else:
            self._apply_state("ESCUCHANDO")
            self._log.append_log("SISTEMA: Micrófono activo.")

    def _style_mute_btn(self):
        if self._muted:
            self._mute_btn.setText("🔇  MICRÓFONO SILENCIADO")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #1f040a; color: {C.MUTED_C};
                    border: 1px solid {C.MUTED_C}; border-radius: 4px;
                }}
                QPushButton:hover {{ background: #2a060f; }}
            """)
        else:
            self._mute_btn.setText("🎙  MICRÓFONO ACTIVO")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #04140a; color: {C.GREEN};
                    border: 1px solid {C.GREEN}; border-radius: 4px;
                }}
                QPushButton:hover {{ background: #061f10; }}
            """)

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
        # Mostrar/ocultar el botón de interrumpir según el estado
        if hasattr(self, "_stop_btn"):
            if state == "HABLANDO":
                self._stop_btn.show()
            else:
                self._stop_btn.hide()

    def _on_log_drop_text(self, text: str):
        """Procesa texto/URL arrastrado al log."""
        if not text:
            return
        preview = text if len(text) <= 80 else text[:77] + "..."
        self._log.append_log(f"ARCHIVO: Texto recibido → {preview}")
        # Si parece una URL, formato distinto
        if text.startswith(("http://", "https://")):
            msg = (
                f"[CONTENIDO_ARRASTRADO] tipo=URL valor={text} | "
                f"Procesa esta URL: abre, busca información o resume lo que el usuario quiera."
            )
        else:
            msg = (
                f"[CONTENIDO_ARRASTRADO] tipo=texto valor={text[:500]} | "
                f"Procesa este texto según el contexto."
            )
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def _on_stop_clicked(self):
        self._log.append_log("SISTEMA: Interrupción solicitada por el usuario.")
        if self.on_interrupt:
            try:
                threading.Thread(target=self.on_interrupt, daemon=True).start()
            except Exception as e:
                self._log.append_log(f"ERROR al interrumpir: {e}")

    def _check_config(self) -> bool:
        if not API_FILE.exists(): return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(d.get("gemini_api_key")) and bool(d.get("os_system"))
        except Exception:
            return False

    def _show_setup(self):
        ov = SetupOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow, oh = 460, 390
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.done.connect(self._on_setup_done)
        ov.show()
        self._overlay = ov

    def _on_setup_done(self, key: str, os_name: str):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        API_FILE.write_text(
            json.dumps({"gemini_api_key": key, "os_system": os_name}, indent=4),
            encoding="utf-8",
        )
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
    def mainloop(self):
        self._app.exec()
    def protocol(self, *_):
        pass
    def quit(self):
        self._win._quit_app()


class OrionUI:
    """Clase principal de la interfaz de O.R.I.O.N."""

    def __init__(self, face_path: str, size=None):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self._win = MainWindow(face_path)
        self._win.show()
        self.root = _RootShim(self._app, self._win)

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if v != self._win._muted:
            self._win._toggle_mute()

    @property
    def current_file(self) -> str | None:
        return self._win._drop_zone.current_file()

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    @property
    def on_interrupt(self):
        return self._win.on_interrupt

    @on_interrupt.setter
    def on_interrupt(self, cb):
        self._win.on_interrupt = cb

    def set_state(self, state: str):
        self._win._state_sig.emit(state)

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)

    def start_speaking(self):
        self.set_state("HABLANDO")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("ESCUCHANDO")


