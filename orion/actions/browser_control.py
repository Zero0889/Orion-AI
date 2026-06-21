from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import platform
import shutil
import subprocess
import threading
from pathlib import Path

from playwright.async_api import (
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeout,
)

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"

# ── Configuración de Chrome directo ─────────────────────────────────────────
from orion.config import BROWSER_CONFIG_PATH as _BROWSER_CONFIG_PATH
import contextlib


def _load_browser_config() -> dict:
    """Carga la configuración del navegador desde browser.json."""
    defaults = {
        "chrome_path": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "use_direct_chrome": True,
        "profile_directory": "",
    }
    try:
        with open(_BROWSER_CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        defaults.update(data)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return defaults


def _open_url_in_chrome(url: str) -> str:
    """Abre una URL directamente en Chrome usando subprocess (sin perfiles nuevos)."""
    cfg = _load_browser_config()
    chrome_path = cfg.get("chrome_path", "")
    profile_dir = cfg.get("profile_directory", "")

    if not chrome_path or not Path(chrome_path).exists():
        chrome_path = shutil.which("chrome") or shutil.which("google-chrome")
        if not chrome_path:
            return ""

    cmd = [chrome_path]
    if profile_dir:
        cmd.append(f"--profile-directory={profile_dir}")
    cmd.append(url)

    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Abierto en Chrome: {url}"
    except (OSError, subprocess.SubprocessError) as e:
        print(f"[Navegador] Error al abrir Chrome directo: {e}")
        return ""


def _normalize_url(url: str) -> str:
    """
    Palabras simples como "instagram" → "https://instagram.com"
    Dominios como "instagram.com" → "https://instagram.com"
    URLs completas pasan sin cambios.
    """
    url = url.strip()
    if not url:
        return "about:blank"
    if "://" in url:
        return url
    # No tiene punto → asumir .com  (ej. "instagram" → "instagram.com")
    if "." not in url:
        url = url + ".com"
    return "https://" + url


def _user_agent() -> str:
    if _OS == "Windows":
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    if _OS == "Darwin":
        return (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    return (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )


def _real_profile_dir(browser: str) -> str:
    home = Path.home()
    local = os.environ.get("LOCALAPPDATA", "")
    roam = os.environ.get("APPDATA", "")

    candidates: list[Path] = []

    if _OS == "Windows":
        m = {
            "chrome": [Path(local) / "Google" / "Chrome" / "User Data"],
            "edge": [Path(local) / "Microsoft" / "Edge" / "User Data"],
            "brave": [Path(local) / "BraveSoftware" / "Brave-Browser" / "User Data"],
            "vivaldi": [Path(local) / "Vivaldi" / "User Data"],
            "opera": [
                Path(roam) / "Opera Software" / "Opera Stable",
                Path(local) / "Opera Software" / "Opera Stable",
            ],
            "operagx": [
                Path(roam) / "Opera Software" / "Opera GX Stable",
                Path(local) / "Opera Software" / "Opera GX Stable",
            ],
        }
        candidates = m.get(browser, [])

    elif _OS == "Darwin":
        lib = home / "Library" / "Application Support"
        m = {
            "chrome": [lib / "Google" / "Chrome"],
            "edge": [lib / "Microsoft Edge"],
            "brave": [lib / "BraveSoftware" / "Brave-Browser"],
            "vivaldi": [lib / "Vivaldi"],
            "opera": [lib / "com.operasoftware.Opera"],
            "operagx": [lib / "com.operasoftware.OperaGX"],
        }
        candidates = m.get(browser, [])

    elif _OS == "Linux":
        cfg = home / ".config"
        m = {
            "chrome": [cfg / "google-chrome", cfg / "chromium"],
            "edge": [cfg / "microsoft-edge"],
            "brave": [cfg / "BraveSoftware" / "Brave-Browser"],
            "vivaldi": [cfg / "vivaldi"],
            "opera": [cfg / "opera"],
            "operagx": [cfg / "opera-gx"],
        }
        candidates = m.get(browser, [])

    for p in candidates:
        if p.exists():
            print(f"[Navegador] ✅ Perfil real encontrado para {browser}: {p}")
            return str(p)

    fallback = home / ".orion_profiles" / browser
    fallback.mkdir(parents=True, exist_ok=True)
    print(f"[Navegador] ⚠️  Perfil real no encontrado para {browser}, usando: {fallback}")
    return str(fallback)


def _firefox_profile_dir() -> str | None:
    home = Path.home()

    if _OS == "Windows":
        base = Path(os.environ.get("APPDATA", "")) / "Mozilla" / "Firefox"
    elif _OS == "Darwin":
        base = home / "Library" / "Application Support" / "Firefox"
    else:
        base = home / ".mozilla" / "firefox"

    ini = base / "profiles.ini"
    if not ini.exists():
        return None

    current: dict[str, str] = {}
    default_path: str | None = None

    for line in ini.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line.startswith("["):
            p = current.get("Path", "")
            if p and current.get("Default") == "1":
                is_rel = current.get("IsRelative", "1") == "1"
                default_path = str(base / p) if is_rel else p
            current = {}
        elif "=" in line:
            k, _, v = line.partition("=")
            current[k.strip()] = v.strip()

    p = current.get("Path", "")
    if p and current.get("Default") == "1":
        is_rel = current.get("IsRelative", "1") == "1"
        default_path = str(base / p) if is_rel else p

    if default_path and Path(default_path).exists():
        print(f"[Navegador] Perfil real de Firefox: {default_path}")
        return default_path
    return None


def _find_opera_windows() -> str | None:
    local = os.environ.get("LOCALAPPDATA", "")
    prog = os.environ.get("PROGRAMFILES", "")
    prog86 = os.environ.get("PROGRAMFILES(X86)", "")

    candidates = [
        Path(local) / "Programs" / "Opera" / "opera.exe",
        Path(local) / "Programs" / "Opera GX" / "opera.exe",
        Path(prog) / "Opera" / "opera.exe",
        Path(prog86) / "Opera" / "opera.exe",
    ]
    for p in candidates:
        if p.exists():
            print(f"[Navegador] Opera encontrado en: {p}")
            return str(p)

    try:
        import winreg

        keys = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\opera.exe",
            r"SOFTWARE\Clients\StartMenuInternet\OperaStable\shell\open\command",
            r"SOFTWARE\Clients\StartMenuInternet\OperaGXStable\shell\open\command",
            r"SOFTWARE\Clients\StartMenuInternet\opera\shell\open\command",
        ]
        for key_path in keys:
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    k = winreg.OpenKey(hive, key_path)
                    val = winreg.QueryValue(k, None)
                    winreg.CloseKey(k)
                    exe = val.strip().strip('"').split('"')[0].split(" --")[0].strip()
                    if exe and Path(exe).exists():
                        print(f"[Navegador] Opera encontrado vía registro: {exe}")
                        return exe
                except Exception:
                    continue
    except Exception:
        pass

    return shutil.which("opera") or None


def _find_exe_windows(prog_name: str) -> str | None:
    try:
        import winreg

        paths_to_try = [
            rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{prog_name}.exe",
            rf"SOFTWARE\Clients\StartMenuInternet\{prog_name}\shell\open\command",
        ]
        for key_path in paths_to_try:
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    k = winreg.OpenKey(hive, key_path)
                    val = winreg.QueryValue(k, None)
                    winreg.CloseKey(k)
                    exe = val.strip().strip('"').split('"')[0].split(" --")[0].strip()
                    if exe and Path(exe).exists():
                        return exe
                except Exception:
                    continue
    except Exception:
        pass
    return None


_BROWSER_SPECS: dict[str, dict] = {
    "Windows": {
        "chrome": {"engine": "chromium", "channel": "chrome", "bins": []},
        "edge": {"engine": "chromium", "channel": "msedge", "bins": []},
        "firefox": {"engine": "firefox", "channel": None, "bins": ["firefox.exe"]},
        "opera": {
            "engine": "chromium",
            "channel": None,
            "bins": ["opera.exe"],
            "special": "opera_windows",
        },
        "operagx": {"engine": "chromium", "channel": None, "bins": [], "special": "opera_windows"},
        "brave": {"engine": "chromium", "channel": None, "bins": ["brave.exe"]},
        "vivaldi": {"engine": "chromium", "channel": None, "bins": ["vivaldi.exe"]},
        "safari": None,
    },
    "Darwin": {
        "chrome": {"engine": "chromium", "channel": "chrome", "bins": []},
        "edge": {"engine": "chromium", "channel": "msedge", "bins": ["microsoft-edge"]},
        "firefox": {"engine": "firefox", "channel": None, "bins": ["firefox"]},
        "opera": {"engine": "chromium", "channel": None, "bins": ["opera"]},
        "operagx": {"engine": "chromium", "channel": None, "bins": ["opera"]},
        "brave": {"engine": "chromium", "channel": None, "bins": ["brave browser", "brave"]},
        "vivaldi": {"engine": "chromium", "channel": None, "bins": ["vivaldi"]},
        "safari": {"engine": "webkit", "channel": None, "bins": []},
    },
    "Linux": {
        "chrome": {
            "engine": "chromium",
            "channel": None,
            "bins": ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"],
        },
        "edge": {
            "engine": "chromium",
            "channel": None,
            "bins": ["microsoft-edge", "microsoft-edge-stable"],
        },
        "firefox": {"engine": "firefox", "channel": None, "bins": ["firefox"]},
        "opera": {"engine": "chromium", "channel": None, "bins": ["opera", "opera-stable"]},
        "operagx": {"engine": "chromium", "channel": None, "bins": ["opera", "opera-stable"]},
        "brave": {"engine": "chromium", "channel": None, "bins": ["brave-browser", "brave"]},
        "vivaldi": {"engine": "chromium", "channel": None, "bins": ["vivaldi-stable", "vivaldi"]},
        "safari": None,
    },
}

_ALIASES: dict[str, str] = {
    "google chrome": "chrome",
    "google-chrome": "chrome",
    "microsoft edge": "edge",
    "ms edge": "edge",
    "msedge": "edge",
    "mozilla firefox": "firefox",
    "opera gx": "operagx",
    "opera_gx": "operagx",
}


def _resolve_browser(name: str) -> dict | None:
    name = _ALIASES.get(name.lower().strip(), name.lower().strip())
    os_map = _BROWSER_SPECS.get(_OS, {})
    spec = os_map.get(name)
    if spec is None:
        return None

    engine = spec["engine"]
    channel = spec.get("channel")
    bins = spec.get("bins", [])
    exe = None

    if spec.get("special") == "opera_windows":
        exe = _find_opera_windows()
        if not exe:
            print("[Navegador] ⚠️  No se encontró el ejecutable de Opera en Windows.")
        return {"engine": engine, "exe": exe, "channel": channel}

    for b in bins:
        found = shutil.which(b)
        if found:
            exe = found
            break

    if not exe and _OS == "Darwin":
        app_names = {
            "chrome": ["Google Chrome.app"],
            "edge": ["Microsoft Edge.app"],
            "firefox": ["Firefox.app"],
            "opera": ["Opera.app", "Opera GX.app"],
            "brave": ["Brave Browser.app"],
            "vivaldi": ["Vivaldi.app"],
        }
        for app in app_names.get(name, []):
            app_dir = Path("/Applications") / app / "Contents" / "MacOS"
            if app_dir.exists():
                found_bins = list(app_dir.iterdir())
                if found_bins:
                    exe = str(found_bins[0])
                    break

    if not exe and _OS == "Windows" and not channel:
        exe = _find_exe_windows(name)

    return {"engine": engine, "exe": exe, "channel": channel}


def _detect_default_browser() -> str:
    try:
        if _OS == "Windows":
            import winreg

            k = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Shell\Associations"
                r"\UrlAssociations\http\UserChoice",
            )
            prog_id = winreg.QueryValueEx(k, "ProgId")[0].lower()
            winreg.CloseKey(k)
            for kw in ("edge", "firefox", "opera", "brave", "vivaldi", "chrome"):
                if kw in prog_id:
                    return kw
        elif _OS == "Darwin":
            out = subprocess.run(
                [
                    "defaults",
                    "read",
                    "com.apple.LaunchServices/com.apple.launchservices.secure",
                    "LSHandlers",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.lower()
            for kw in ("firefox", "opera", "brave", "vivaldi", "safari", "chrome", "edge"):
                if kw in out:
                    return kw
        elif _OS == "Linux":
            out = subprocess.run(
                ["xdg-settings", "get", "default-web-browser"],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.lower()
            for kw in ("firefox", "opera", "brave", "vivaldi", "chrome", "edge"):
                if kw in out:
                    return kw
    except Exception:
        pass
    return "chrome"


class _BrowserSession:
    """
    Sesión completa para una instancia de navegador.
    Todos los navegadores se abren con launch_persistent_context sobre el perfil real.
    """

    def __init__(self, browser_name: str):
        self.browser_name = browser_name
        self._spec = _resolve_browser(browser_name)

        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()

        self._pw: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name=f"BrowserThread-{self.browser_name}",
        )
        self._thread.start()
        self._ready.wait(timeout=20)

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._async_init())
        self._ready.set()
        self._loop.run_forever()

    async def _async_init(self):
        self._pw = await async_playwright().start()

    def run(self, coro, timeout: int = 60) -> str:
        if not self._loop:
            raise RuntimeError(f"La sesión de '{self.browser_name}' no se inició.")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def close(self):
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._async_close(), self._loop).result(10)

    async def _async_close(self):
        if self._context:
            with contextlib.suppress(Exception):
                await self._context.close()
        if self._pw:
            with contextlib.suppress(Exception):
                await self._pw.stop()
        self._context = self._page = None

    async def _launch(self):
        """
        Inicia el navegador con el perfil real del usuario.
        Si el contexto ya está abierto, no hace nada.
        """
        if self._context is not None:
            return

        if self._spec is None:
            raise RuntimeError(
                f"'{self.browser_name}' no es compatible en esta plataforma ({_OS})."
            )

        engine_name = self._spec["engine"]
        exe = self._spec["exe"]
        channel = self._spec["channel"]
        engine_obj = getattr(self._pw, engine_name)

        if engine_name == "firefox":
            profile = _firefox_profile_dir() or str(Path.home() / ".orion_profiles" / "firefox")
            kwargs: dict = {
                "headless": False,
                "slow_mo": 0,
                "viewport": None,
                "no_viewport": True,
            }
            if exe:
                kwargs["executable_path"] = exe
            try:
                self._context = await engine_obj.launch_persistent_context(profile, **kwargs)
            except Exception as e:
                print(f"[Navegador] Falló el perfil real de Firefox ({e}), usando perfil O.R.I.O.N")
                orion = str(Path.home() / ".orion_profiles" / "firefox_orion")
                Path(orion).mkdir(parents=True, exist_ok=True)
                self._context = await engine_obj.launch_persistent_context(orion, **kwargs)

            await asyncio.sleep(0.5)
            self._page = await self._context.new_page()
            print("[Navegador] ✅ Firefox iniciado")
            return

        if engine_name == "webkit":
            safari_profile = str(Path.home() / ".orion_profiles" / "safari")
            Path(safari_profile).mkdir(parents=True, exist_ok=True)
            kwargs = {
                "headless": False,
                "slow_mo": 0,
                "viewport": None,
                "no_viewport": True,
            }
            self._context = await engine_obj.launch_persistent_context(safari_profile, **kwargs)
            await asyncio.sleep(0.5)
            self._page = await self._context.new_page()
            print("[Navegador] ✅ Safari iniciado")
            return

        profile = _real_profile_dir(self.browser_name)

        kwargs = {
            "headless": False,
            "slow_mo": 0,
            "viewport": None,
            "no_viewport": True,
            "args": [
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--disable-default-apps",
                "--no-default-browser-check",
            ],
        }

        if exe:
            kwargs["executable_path"] = exe
        elif channel:
            kwargs["channel"] = channel

        label = (
            f"{self.browser_name}"
            + (f"/{channel}" if channel else "")
            + (f" @ {exe}" if exe else "")
        )

        try:
            self._context = await engine_obj.launch_persistent_context(profile, **kwargs)
            await asyncio.sleep(0.5)
            self._page = await self._context.new_page()
            print(f"[Navegador] ✅ Iniciado [{label}] perfil={profile}")
            return
        except Exception as e:
            print(f"[Navegador] ⚠️  Falló el perfil real para {label}: {e}")

        orion_profile = str(Path.home() / ".orion_profiles" / self.browser_name)
        Path(orion_profile).mkdir(parents=True, exist_ok=True)
        print(f"[Navegador] Reintentando con perfil O.R.I.O.N: {orion_profile}")

        try:
            self._context = await engine_obj.launch_persistent_context(orion_profile, **kwargs)
            await asyncio.sleep(0.5)
            self._page = await self._context.new_page()
            print(f"[Navegador] ✅ Iniciado [{label}] con perfil O.R.I.O.N")
        except Exception as e2:
            raise RuntimeError(f"No se pudo iniciar {self.browser_name}: {e2}") from e2

    async def _get_page(self) -> Page:
        await self._launch()
        # Si por alguna razón la página se cerró, abrir una nueva
        if self._page is None or self._page.is_closed():
            self._page = await self._context.new_page()
            await asyncio.sleep(0.2)
        return self._page

    async def go_to(self, url: str) -> str:

        url = _normalize_url(url)
        page = await self._get_page()
        prev_url = page.url

        async def _do_goto(p: Page) -> str:
            """Intenta navegar y devuelve la URL resultante (puede quedar en blanco)."""
            try:
                await p.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await asyncio.sleep(0.3)
            except PlaywrightTimeout:
                pass  # la página puede haber cargado parcialmente — comprobar URL abajo
            except Exception as e:
                print(f"[Navegador] excepción en goto (no fatal): {e}")
            return p.url

        result_url = await _do_goto(page)

        if result_url in ("about:blank", "", None, prev_url) and prev_url in (
            "about:blank",
            "",
            None,
        ):
            print(f"[Navegador] Sigue en blanco tras goto — reintentando en pestaña nueva: {url}")
            try:
                new_page = await self._context.new_page()
                self._page = new_page
                result_url = await _do_goto(new_page)
            except Exception as e:
                print(f"[Navegador] Reintento en pestaña nueva falló: {e}")

        if result_url and result_url not in ("about:blank", "", None):
            return f"Abierto: {result_url}"
        return f"No se pudo abrir: {url}"

    async def search(self, query: str, engine: str = "google") -> str:
        _engines = {
            "google": "https://www.google.com/search?q=",
            "bing": "https://www.bing.com/search?q=",
            "duckduckgo": "https://duckduckgo.com/?q=",
            "yandex": "https://yandex.com/search/?text=",
        }
        base = _engines.get(engine.lower(), _engines["google"])
        return await self.go_to(base + query.replace(" ", "+"))

    async def click(self, selector: str = None, text: str = None) -> str:
        page = await self._get_page()
        try:
            if text:
                await page.get_by_text(text, exact=False).first.click(timeout=8_000)
                return f"Clic en texto: '{text}'"
            if selector:
                await page.click(selector, timeout=8_000)
                return f"Clic en selector: {selector}"
            return "No se proporcionó selector ni texto."
        except PlaywrightTimeout:
            return "Elemento no encontrado (tiempo agotado)."
        except Exception as e:
            return f"Error al hacer clic: {e}"

    async def type_text(
        self, selector: str = None, text: str = "", clear_first: bool = True
    ) -> str:
        page = await self._get_page()
        try:
            el = page.locator(selector).first if selector else page.locator(":focus")
            if clear_first:
                await el.clear()
            await el.type(text, delay=50)
            return "Texto escrito."
        except Exception as e:
            return f"Error al escribir: {e}"

    async def scroll(self, direction: str = "down", amount: int = 500) -> str:
        page = await self._get_page()
        try:
            y = amount if direction == "down" else -amount
            await page.mouse.wheel(0, y)
            return f"Desplazado: {direction}."
        except Exception as e:
            return f"Error al desplazar: {e}"

    async def press(self, key: str) -> str:
        page = await self._get_page()
        try:
            await page.keyboard.press(key)
            return f"Tecla pulsada: {key}"
        except Exception as e:
            return f"Error de tecla: {e}"

    async def get_text(self) -> str:
        page = await self._get_page()
        try:
            text = await page.inner_text("body")
            return text[:4_000]
        except Exception as e:
            return f"No se pudo obtener el texto de la página: {e}"

    async def get_url(self) -> str:
        page = await self._get_page()
        return page.url

    async def fill_form(self, fields: dict) -> str:
        page = await self._get_page()
        results = []
        for selector, value in fields.items():
            try:
                el = page.locator(selector).first
                await el.clear()
                await el.type(str(value), delay=40)
                results.append(f"✓ {selector}")
            except Exception as e:
                results.append(f"✗ {selector}: {e}")
        return "Formulario rellenado: " + ", ".join(results)

    async def smart_click(self, description: str) -> str:
        page = await self._get_page()
        for role in ("button", "link", "searchbox", "textbox", "menuitem", "tab"):
            try:
                loc = page.get_by_role(role, name=description)
                if await loc.count() > 0:
                    await loc.first.click(timeout=5_000)
                    return f"Clic ({role}): '{description}'"
            except Exception:
                pass
        for attempt in (
            lambda: page.get_by_text(description, exact=False).first.click(timeout=5_000),
            lambda: page.get_by_placeholder(description, exact=False).first.click(timeout=5_000),
            lambda: page.locator(
                f'[alt*="{description}" i],[title*="{description}" i],'
                f'[aria-label*="{description}" i]'
            ).first.click(timeout=5_000),
        ):
            try:
                await attempt()
                return f"Clic: '{description}'"
            except Exception:
                pass
        return f"No se pudo encontrar el elemento: '{description}'"

    async def smart_type(self, description: str, text: str) -> str:
        page = await self._get_page()
        candidates = [
            ("placeholder", page.get_by_placeholder(description, exact=False)),
            ("label", page.get_by_label(description, exact=False)),
            ("role", page.get_by_role("textbox", name=description)),
            ("searchbox", page.get_by_role("searchbox")),
            ("combobox", page.get_by_role("combobox", name=description)),
        ]
        for method, loc in candidates:
            try:
                el = loc.first
                if await el.count() == 0:
                    continue
                await el.clear()
                await el.type(text, delay=50)
                return f"Escrito en ({method}): '{description}'"
            except Exception:
                continue
        return f"No se pudo encontrar el campo: '{description}'"

    async def new_tab(self, url: str = "") -> str:
        page = await self._get_page()
        ctx = page.context
        new = await ctx.new_page()
        self._page = new
        if url:
            return await self.go_to(url)
        return "Pestaña nueva abierta."

    async def close_tab(self) -> str:
        page = self._page
        if page and not page.is_closed():
            ctx = page.context
            await page.close()
            pages = ctx.pages
            self._page = pages[-1] if pages else None
            return "Pestaña cerrada."
        return "No hay pestaña activa para cerrar."

    async def screenshot(self, path: str = None) -> str:
        page = await self._get_page()
        try:
            save_path = path or str(Path.home() / "Desktop" / "orion_screenshot.png")
            await page.screenshot(path=save_path, full_page=False)
            return f"Captura guardada: {save_path}"
        except Exception as e:
            return f"Error en captura: {e}"

    async def back(self) -> str:
        page = await self._get_page()
        try:
            await page.go_back(timeout=10_000)
            return f"Retrocediendo: {page.url}"
        except Exception as e:
            return f"Error al retroceder: {e}"

    async def forward(self) -> str:
        page = await self._get_page()
        try:
            await page.go_forward(timeout=10_000)
            return f"Avanzando: {page.url}"
        except Exception as e:
            return f"Error al avanzar: {e}"

    async def reload(self) -> str:
        page = await self._get_page()
        try:
            await page.reload(timeout=15_000)
            return f"Página recargada: {page.url}"
        except Exception as e:
            return f"Error al recargar: {e}"

    async def close_browser(self) -> str:
        await self._async_close()
        return f"{self.browser_name} cerrado."


class _SessionRegistry:
    """Administra todas las sesiones de navegador activas."""

    def __init__(self):
        self._sessions: dict[str, _BrowserSession] = {}
        self._active_browser: str = ""
        self._lock = threading.Lock()

    def _get_or_create(self, browser_name: str) -> _BrowserSession:
        with self._lock:
            if browser_name not in self._sessions:
                sess = _BrowserSession(browser_name)
                sess.start()
                self._sessions[browser_name] = sess
                print(f"[Registro] Nueva sesión: {browser_name}")
            return self._sessions[browser_name]

    def get(self, browser_name: str | None = None) -> _BrowserSession:
        if not browser_name:
            browser_name = self._active_browser or _detect_default_browser()
        browser_name = _ALIASES.get(browser_name.lower().strip(), browser_name.lower().strip())
        sess = self._get_or_create(browser_name)
        self._active_browser = browser_name
        return sess

    def switch(self, browser_name: str) -> str:
        browser_name = _ALIASES.get(browser_name.lower().strip(), browser_name.lower().strip())
        self._get_or_create(browser_name)
        self._active_browser = browser_name
        return f"Navegador activo → {browser_name}"

    def close_one(self, browser_name: str) -> str:
        with self._lock:
            sess = self._sessions.pop(browser_name, None)
        if sess:
            sess.close()
            if self._active_browser == browser_name:
                self._active_browser = ""
            return f"{browser_name} cerrado."
        return f"No hay sesión activa para: {browser_name}"

    def close_all(self) -> str:
        with self._lock:
            names = list(self._sessions.keys())
            sessions = list(self._sessions.values())
            self._sessions.clear()
            self._active_browser = ""
        for s in sessions:
            with contextlib.suppress(Exception):
                s.close()
        return "Todos los navegadores cerrados: " + (", ".join(names) if names else "ninguno")

    def list_sessions(self) -> str:
        with self._lock:
            if not self._sessions:
                return "No hay sesiones de navegador activas."
            lines = []
            for name in self._sessions:
                marker = " ◀ activo" if name == self._active_browser else ""
                lines.append(f"  • {name}{marker}")
            return "Navegadores abiertos:\n" + "\n".join(lines)


_registry = _SessionRegistry()


from orion.core.tool_registry import tool


@tool(
    name="browser_control",
    description=(
        "Controls any web browser. Use for: opening websites, searching the web, "
        "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
        "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
        "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all",
            },
            "browser": {
                "type": "STRING",
                "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser.",
            },
            "url": {"type": "STRING", "description": "URL for go_to / new_tab action"},
            "query": {"type": "STRING", "description": "Search query for search action"},
            "engine": {
                "type": "STRING",
                "description": "Search engine: google | bing | duckduckgo | yandex (default: google)",
            },
            "selector": {"type": "STRING", "description": "CSS selector for click/type"},
            "text": {"type": "STRING", "description": "Text to click or type"},
            "description": {
                "type": "STRING",
                "description": "Element description for smart_click/smart_type",
            },
            "direction": {"type": "STRING", "description": "up | down for scroll"},
            "amount": {
                "type": "INTEGER",
                "description": "Scroll amount in pixels (default: 500)",
            },
            "key": {
                "type": "STRING",
                "description": "Key name for press action (e.g. Enter, Escape, F5)",
            },
            "path": {"type": "STRING", "description": "Save path for screenshot"},
            "incognito": {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
            "clear_first": {
                "type": "BOOLEAN",
                "description": "Clear field before typing (default: true)",
            },
        },
        "required": ["action"],
    },
)
def browser_control(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    action = params.get("action", "").lower().strip()
    browser = params.get("browser", "").lower().strip() or None
    result = "Acción desconocida."

    # ── Verificar si usar Chrome directo (sin Playwright/perfiles) ──
    cfg = _load_browser_config()
    use_direct = cfg.get("use_direct_chrome", True)

    # Acciones simples de navegación → Chrome directo
    if use_direct and action in ("go_to", "search", "new_tab"):
        if action == "go_to":
            url = _normalize_url(params.get("url", ""))
            result = _open_url_in_chrome(url)
            if result:
                _log(player, result)
                return result

        elif action == "search":
            query = params.get("query", "")
            engine = params.get("engine", "google").lower()
            _engines = {
                "google": "https://www.google.com/search?q=",
                "bing": "https://www.bing.com/search?q=",
                "duckduckgo": "https://duckduckgo.com/?q=",
                "yandex": "https://yandex.com/search/?text=",
            }
            base = _engines.get(engine, _engines["google"])
            url = base + query.replace(" ", "+")
            result = _open_url_in_chrome(url)
            if result:
                _log(player, result)
                return result

        elif action == "new_tab":
            url = params.get("url", "")
            if url:
                url = _normalize_url(url)
                result = _open_url_in_chrome(url)
                if result:
                    _log(player, result)
                    return result

    # ── Acciones que no requieren Chrome directo o fallback a Playwright ──
    if action == "switch":
        target = browser or params.get("target", "").lower().strip()
        result = _registry.switch(target) if target else "Por favor, indique un navegador."
        _log(player, result)
        return result

    if action == "list_browsers":
        result = _registry.list_sessions()
        _log(player, result)
        return result

    if action == "close_all":
        result = _registry.close_all()
        _log(player, result)
        return result

    try:
        sess = _registry.get(browser)
    except Exception as e:
        result = f"No se pudo iniciar la sesión del navegador: {e}"
        _log(player, result)
        return result

    try:
        if action == "go_to":
            result = sess.run(sess.go_to(params.get("url", "")))
        elif action == "search":
            result = sess.run(sess.search(params.get("query", ""), params.get("engine", "google")))
        elif action == "click":
            result = sess.run(sess.click(params.get("selector"), params.get("text")))
        elif action == "type":
            result = sess.run(
                sess.type_text(
                    params.get("selector"), params.get("text", ""), params.get("clear_first", True)
                )
            )
        elif action == "scroll":
            result = sess.run(
                sess.scroll(params.get("direction", "down"), int(params.get("amount", 500)))
            )
        elif action == "fill_form":
            result = sess.run(sess.fill_form(params.get("fields", {})))
        elif action == "smart_click":
            result = sess.run(sess.smart_click(params.get("description", "")))
        elif action == "smart_type":
            result = sess.run(
                sess.smart_type(params.get("description", ""), params.get("text", ""))
            )
        elif action == "get_text":
            result = sess.run(sess.get_text())
        elif action == "get_url":
            result = sess.run(sess.get_url())
        elif action == "press":
            result = sess.run(sess.press(params.get("key", "Enter")))
        elif action == "new_tab":
            result = sess.run(sess.new_tab(params.get("url", "")))
        elif action == "close_tab":
            result = sess.run(sess.close_tab())
        elif action == "screenshot":
            result = sess.run(sess.screenshot(params.get("path")))
        elif action == "back":
            result = sess.run(sess.back())
        elif action == "forward":
            result = sess.run(sess.forward())
        elif action == "reload":
            result = sess.run(sess.reload())
        elif action == "close":
            target = browser or _registry._active_browser
            result = _registry.close_one(target) if target else "No se especificó navegador."
        else:
            result = f"Acción de navegador desconocida: '{action}'"

    except concurrent.futures.TimeoutError:
        result = f"Acción de navegador '{action}' agotó el tiempo (60s)."
    except Exception as e:
        result = f"Error de navegador ({action}): {e}"

    _log(player, result)
    return result


def _log(player, text: str):
    short = str(text)[:80]
    print(f"[Navegador] {short}")
    if player:
        player.write_log(f"[navegador] {short[:60]}")
