"""
core.cli_installer — Descarga binarios CLI auxiliares a tools/<name>/
====================================================================
Algunas skills (gog, himalaya, jq…) llaman binarios externos. Para que
ORION funcione sin pedirle al usuario configurar PATH, los bajamos a
``tools/<name>/`` dentro del proyecto y los exponemos al subprocess del
executor vía PATH local.

Diseño
------
* :data:`REGISTRY`        — diccionario ``{nombre → CliSpec}`` con repos
                            de release oficial. Agregar uno nuevo son
                            ~6 líneas.
* :func:`cli_path`        — devuelve la ruta absoluta del binario, o
                            None si no está instalado.
* :func:`install_cli`     — descarga + extrae para la plataforma actual.
                            Idempotente (no re-baja si ya existe salvo
                            ``force=True``).
* :func:`extra_path_dirs` — carpetas a prepender al PATH del subprocess.
* :func:`required_bins`   — dado un frontmatter de SKILL.md, lista los
                            bins requeridos (parsea el formato OpenClaw).
* :func:`registry_info`   — descripción de cada entrada del REGISTRY
                            para el frontend (status + repo).

Sin deps nuevas — sólo stdlib (urllib, zipfile, tarfile, shutil).
"""

from __future__ import annotations

import os
import platform
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orion.config import BASE_DIR
import contextlib


@dataclass(frozen=True)
class CliSpec:
    """Define cómo instalar un binario CLI desde una GitHub release.

    ``asset_template`` admite los placeholders ``{version}``, ``{os}`` y
    ``{arch}``. ``os_map`` y ``arch_map`` traducen el output de
    ``platform.system()`` y ``platform.machine()`` al vocabulario que usa
    el proyecto en sus assets (cada proyecto tiene el suyo: gog usa
    'windows/darwin/linux' + 'amd64/arm64', otros usan 'win/macos/linux'
    + 'x64/aarch64'…).
    """

    name: str
    repo: str  # "owner/repo"
    version: str  # ej: "0.22.0"
    asset_template: str  # ej: "gogcli_{version}_{os}_{arch}.zip"
    bin_name: str  # nombre del binario tras extraer
    os_map: dict[str, str] = field(
        default_factory=lambda: {"windows": "windows", "darwin": "darwin", "linux": "linux"}
    )
    arch_map: dict[str, str] = field(
        default_factory=lambda: {
            "amd64": "amd64",
            "x86_64": "amd64",
            "arm64": "arm64",
            "aarch64": "arm64",
        }
    )
    description: str = ""  # para el UI

    @property
    def display_name(self) -> str:
        return self.name


# ── Registry ────────────────────────────────────────────────────────────


REGISTRY: dict[str, CliSpec] = {
    "gog": CliSpec(
        name="gog",
        repo="openclaw/gogcli",
        version="0.22.0",
        asset_template="gogcli_{version}_{os}_{arch}.{ext}",
        bin_name="gog",
        description="Google Workspace CLI: Gmail, Calendar, Drive, Docs, Sheets, Contacts.",
    ),
    "jq": CliSpec(
        # jq lo usan MUCHAS skills para parsear JSON. Vale la pena pre-registrarlo.
        name="jq",
        repo="jqlang/jq",
        version="1.7.1",
        asset_template="jq-{os}-{arch}{ext_dot}",
        bin_name="jq",
        os_map={"windows": "windows", "darwin": "macos", "linux": "linux"},
        arch_map={"amd64": "amd64", "x86_64": "amd64", "arm64": "arm64", "aarch64": "arm64"},
        description="Procesador de JSON desde línea de comandos. Lo usan muchas skills.",
    ),
    "himalaya": CliSpec(
        name="himalaya",
        repo="pimalaya/himalaya",
        version="1.0.0",
        asset_template="himalaya.{ext}",  # himalaya usa un nombre simple por OS
        bin_name="himalaya",
        description="CLI de email (alternativa a gog si querés algo más liviano).",
    ),
}


# ── Helpers de plataforma ──────────────────────────────────────────────


def _platform_tags(spec: CliSpec) -> tuple[str, str]:
    sys_name = platform.system().lower()
    arch = platform.machine().lower()
    os_tag = spec.os_map.get(sys_name)
    arch_tag = spec.arch_map.get(arch)
    if not os_tag or not arch_tag:
        raise RuntimeError(
            f"{spec.name}: plataforma no soportada ({sys_name}/{arch}). "
            f"OS map: {spec.os_map} · Arch map: {spec.arch_map}"
        )
    return os_tag, arch_tag


def _asset_for(spec: CliSpec) -> tuple[str, str]:
    """Devuelve (asset_name, format_ext) para la plataforma actual."""
    os_tag, arch_tag = _platform_tags(spec)
    ext_dot = ".exe" if os_tag == "windows" and spec.name == "jq" else ""
    ext = "zip" if os_tag == "windows" else "tar.gz"
    asset = spec.asset_template.format(
        version=spec.version,
        os=os_tag,
        arch=arch_tag,
        ext=ext,
        ext_dot=ext_dot,
    )
    return asset, ext


# ── Filesystem ──────────────────────────────────────────────────────────


def tools_dir() -> Path:
    p = BASE_DIR / "tools"
    p.mkdir(exist_ok=True)
    return p


def extra_path_dirs() -> list[str]:
    """Carpetas con binarios manejados por ORION para prepender al PATH
    cuando lanzamos subprocesses (ver agent/executor.py).
    Filtra metadirectorios para no contaminar el PATH.
    """
    root = tools_dir()
    if not root.exists():
        return []
    out: list[str] = []
    for sub in root.iterdir():
        if not sub.is_dir():
            continue
        if sub.name.startswith(".") or sub.name == "__pycache__":
            continue
        out.append(str(sub))
    return out


def cli_path(name: str) -> str | None:
    """Ruta absoluta al binario si está disponible (tools/ o PATH del sistema)."""
    spec = REGISTRY.get(name)
    bin_name = spec.bin_name if spec else name
    exe = f"{bin_name}.exe" if os.name == "nt" else bin_name

    managed = tools_dir() / name / exe
    if managed.exists():
        return str(managed)
    return shutil.which(bin_name)


# Backwards-compat: el código viejo importaba gog_path() directo.
def gog_path() -> str | None:
    return cli_path("gog")


# ── Instalación ─────────────────────────────────────────────────────────


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "ORION-CLI-Installer/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as out:
        shutil.copyfileobj(r, out)


def _extract(archive: Path, dest_dir: Path) -> None:
    if archive.suffix == ".exe":
        # jq y similares vienen como binario directo, sin archive — copy directo
        # Esto en realidad no se invoca porque las descargas single-file van por
        # otra rama, pero lo dejo defensivo.
        shutil.copy(archive, dest_dir / archive.name)
        return
    name = archive.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest_dir)
        return
    if name.endswith(".tar.gz") or name.endswith(".tgz"):
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(dest_dir)
        return
    raise RuntimeError(f"Formato no soportado: {archive.name}")


def install_cli(name: str, *, force: bool = False) -> str:
    """Descarga + extrae el CLI ``name`` a ``tools/<name>/``. Devuelve la
    ruta absoluta del binario. Idempotente."""
    spec = REGISTRY.get(name)
    if spec is None:
        raise KeyError(f"CLI '{name}' no está en el registry. Conocidos: {', '.join(REGISTRY)}")

    if not force:
        existing = cli_path(name)
        if existing:
            return existing

    asset, _ext = _asset_for(spec)
    dest_dir = tools_dir() / name
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Caso especial: si el asset termina en .exe (un binario directo)
    # bajamos al destino final con el nombre del bin.
    if asset.endswith(".exe"):
        target = dest_dir / f"{spec.bin_name}.exe"
        url = f"https://github.com/{spec.repo}/releases/download/v{spec.version}/{asset}"
        print(f"[CLI Installer] ⬇ Bajando {url}")
        _download(url, target)
        if os.name != "nt":
            with contextlib.suppress(OSError):
                os.chmod(target, 0o755)
        print(f"[CLI Installer] ✓ {name} instalado en {target}")
        return str(target)

    # Caso normal: zip / tar.gz a un temp + extraer.
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(asset).suffix) as tmp:
        tmp_path = Path(tmp.name)

    try:
        url = f"https://github.com/{spec.repo}/releases/download/v{spec.version}/{asset}"
        print(f"[CLI Installer] ⬇ Bajando {url}")
        _download(url, tmp_path)

        print(f"[CLI Installer] 📦 Extrayendo a {dest_dir}")
        _extract(tmp_path, dest_dir)
    finally:
        with contextlib.suppress(OSError):
            tmp_path.unlink()

    # Buscar el binario tras extraer. Algunos archives lo dejan en root,
    # otros en subcarpeta. Lo movemos a la raíz de tools/<name>/.
    bin_name_exe = f"{spec.bin_name}.exe" if os.name == "nt" else spec.bin_name
    found: Path | None = None
    for candidate in dest_dir.rglob(spec.bin_name + "*"):
        if candidate.is_file() and candidate.name in (spec.bin_name, bin_name_exe):
            found = candidate
            break

    if found is None:
        raise RuntimeError(
            f"Extraí el archive pero no encontré '{spec.bin_name}' en {dest_dir}. "
            f"Revisá el contenido a mano."
        )

    target = dest_dir / found.name
    if found.resolve() != target.resolve():
        shutil.move(str(found), str(target))

    if os.name != "nt":
        with contextlib.suppress(OSError):
            os.chmod(target, 0o755)

    print(f"[CLI Installer] ✓ {name} instalado en {target}")
    return str(target)


# Backwards-compat: el endpoint viejo y el test importaban install_gog().
def install_gog(force: bool = False) -> str:
    return install_cli("gog", force=force)


# ── Introspección para el frontend / planner ───────────────────────────


def registry_info() -> list[dict]:
    """Listado de todas las CLIs registradas con su status actual.
    Útil para que el frontend muestre el panel completo en un sólo GET."""
    out: list[dict] = []
    for name, spec in REGISTRY.items():
        out.append(
            {
                "name": name,
                "repo": spec.repo,
                "version": spec.version,
                "description": spec.description,
                "installed": cli_path(name) is not None,
                "path": cli_path(name),
            }
        )
    return out


def required_bins(frontmatter: dict[str, Any]) -> list[str]:
    """Extrae la lista de binarios requeridos de un frontmatter SKILL.md.
    Formato OpenClaw::

        metadata:
          openclaw:
            requires:
              bins: ["gog"]

    Tolera variantes (metadata como string JSON, openclaw ausente, etc.)
    y devuelve siempre una lista (posiblemente vacía).
    """
    meta = frontmatter.get("metadata")
    if isinstance(meta, str):
        # A veces viene como bloque YAML/JSON serializado por el parser ingenuo.
        try:
            import json

            meta = json.loads(meta)
        except Exception:
            return []
    if not isinstance(meta, dict):
        return []
    oc = meta.get("openclaw") or meta.get("orion") or {}
    if not isinstance(oc, dict):
        return []
    requires = oc.get("requires") or {}
    if not isinstance(requires, dict):
        return []
    bins = requires.get("bins") or []
    if isinstance(bins, str):
        return [b.strip() for b in bins.replace(",", " ").split() if b.strip()]
    if isinstance(bins, list):
        return [str(b).strip() for b in bins if str(b).strip()]
    return []
