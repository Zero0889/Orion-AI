"""
core.skill_scanner — Validación y scan de seguridad para skills
================================================================
Port (simplificado) de ``packages/agent-core/src/skills/security/scanner.ts``
de OpenClaw. Detecta patrones peligrosos en SKILL.md y archivos .py/.sh/.js
dentro de una carpeta de skill ANTES de cargarla.

Severidades
-----------
- ``critical``: bloquea el load. La skill se rechaza con un mensaje claro.
- ``warn``: la skill se carga igual pero se loguea + se devuelve en la
  respuesta del install endpoint para que el usuario decida.
- ``info``: solo logging informativo.

Validación adicional de frontmatter
-----------------------------------
* ``name`` requerido, alfanumérico+guiones, <80 chars.
* ``description`` requerida, no vacía, <500 chars.
* ``body`` no vacío y <500 KB (defensa contra prompt-bombs).

Uso
---
::

    from orion.core.skill_scanner import scan_skill_dir, ScanResult
    result = scan_skill_dir(Path("skills/foo"))
    if result.has_critical():
        print("Rechazada:", result.summary())
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# ── Tipos ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str  # "critical" | "warn" | "info"
    file: str  # path relativo a la skill_dir
    line: int  # 0 si no aplica
    message: str
    evidence: str  # snippet de hasta 120 chars


@dataclass
class ScanResult:
    skill_dir: Path
    findings: list[Finding] = field(default_factory=list)
    scanned_files: int = 0

    def has_critical(self) -> bool:
        return any(f.severity == "critical" for f in self.findings)

    def has_warnings(self) -> bool:
        return any(f.severity == "warn" for f in self.findings)

    def by_severity(self, sev: str) -> list[Finding]:
        return [f for f in self.findings if f.severity == sev]

    def summary(self) -> str:
        c = len(self.by_severity("critical"))
        w = len(self.by_severity("warn"))
        i = len(self.by_severity("info"))
        return f"{c} critical, {w} warnings, {i} info ({self.scanned_files} files)"

    def to_dict(self) -> dict:
        return {
            "scanned_files": self.scanned_files,
            "critical": len(self.by_severity("critical")),
            "warn": len(self.by_severity("warn")),
            "info": len(self.by_severity("info")),
            "findings": [
                {
                    "rule_id": f.rule_id,
                    "severity": f.severity,
                    "file": f.file,
                    "line": f.line,
                    "message": f.message,
                    "evidence": f.evidence,
                }
                for f in self.findings
            ],
        }


# ── Reglas ──────────────────────────────────────────────────────────────
# Patrones inspirados en OpenClaw security/scanner.ts. Adaptamos a Python:
# en vez de child_process/exec buscamos os.system/subprocess.Popen,
# en vez de eval/new Function buscamos eval/exec, etc.

# Reglas por LÍNEA (regex sobre cada línea individual).
LINE_RULES = [
    # Ejecución dinámica de código
    {
        "id": "dynamic-code-execution",
        "severity": "critical",
        "msg": "Dynamic code execution detected (eval/exec)",
        "pattern": re.compile(r"\beval\s*\(|\bexec\s*\(|__import__\s*\("),
    },
    # Crypto mining markers
    {
        "id": "crypto-mining",
        "severity": "critical",
        "msg": "Possible crypto-mining reference",
        "pattern": re.compile(r"stratum\+tcp|stratum\+ssl|coinhive|cryptonight|xmrig", re.I),
    },
    # Persistencia/backdoor patterns
    {
        "id": "persistence-task",
        "severity": "warn",
        "msg": "Possible persistence mechanism (scheduled task / autostart)",
        "pattern": re.compile(
            r"schtasks|crontab\s+-e|/etc/rc\.local|/Library/LaunchAgents|HKCU.*Run", re.I
        ),
    },
]

# Reglas sobre el SOURCE COMPLETO (en archivos de código).
SOURCE_RULES = [
    # Lectura de archivos + envío de red → exfiltración
    {
        "id": "potential-exfiltration",
        "severity": "warn",
        "msg": "File read combined with network send — possible data exfiltration",
        "primary": re.compile(r"open\s*\(|read_text|read_bytes|readFile"),
        "context": re.compile(r"requests\.|urllib|httpx|aiohttp|fetch\s*\(|socket\."),
    },
    # Variables de entorno + red → harvesting de credenciales
    {
        "id": "env-harvesting",
        "severity": "critical",
        "msg": "Environment variable access + network send — possible credential harvesting",
        "primary": re.compile(r"os\.environ|getenv|process\.env"),
        "context": re.compile(r"requests\.|urllib|httpx|aiohttp|fetch\s*\(|socket\."),
    },
    # Obfuscation
    {
        "id": "obfuscated-code",
        "severity": "warn",
        "msg": "Hex/base64 obfuscation pattern",
        "primary": re.compile(
            r"(\\x[0-9a-fA-F]{2}){8,}|(?:b64decode|atob)\s*\(\s*['\"][A-Za-z0-9+/=]{200,}"
        ),
        "context": None,
    },
]

# Reglas específicas para el TEXTO del SKILL.md (recetas, instrucciones).
# Las primeras tres detectan prompt injection — críticas porque si el modelo
# las lee, podría obedecerlas y bypassear nuestras reglas.
SKILL_CONTENT_RULES = [
    {
        "id": "prompt-injection-ignore-instructions",
        "severity": "critical",
        "msg": "Skill text tries to override prior instructions",
        "pattern": re.compile(r"ignore (all|any|previous|above|prior) instructions", re.I),
    },
    {
        "id": "prompt-injection-system",
        "severity": "critical",
        "msg": "Skill text references hidden prompt layers",
        "pattern": re.compile(r"\b(system prompt|developer message|hidden instructions)\b", re.I),
    },
    {
        "id": "prompt-injection-tool",
        "severity": "critical",
        "msg": "Skill text encourages bypassing tool approval",
        "pattern": re.compile(
            r"\b(run|execute|invoke|call)\b.{0,50}\btool\b.{0,50}\bwithout\b.{0,30}\b(permission|approval)",
            re.I,
        ),
    },
    {
        "id": "shell-pipe-to-shell",
        "severity": "critical",
        "msg": "Skill text includes curl|sh / wget|sh install pattern",
        "pattern": re.compile(
            r"\b(curl|wget|iwr|Invoke-WebRequest)\b[^|\n]{0,120}\|\s*(sh|bash|zsh|pwsh|powershell)\b",
            re.I,
        ),
    },
    {
        "id": "destructive-delete",
        "severity": "warn",
        "msg": "Skill text contains broad destructive delete",
        "pattern": re.compile(
            r"\brm\s+-rf\s+(\/|\$HOME|~|\.)|Remove-Item.*-Recurse.*-Force.*[CcDd]:\\", re.I
        ),
    },
    {
        "id": "unsafe-permissions",
        "severity": "warn",
        "msg": "Skill text contains unsafe chmod 777",
        "pattern": re.compile(r"\bchmod\s+(-R\s+)?777\b", re.I),
    },
]


# Extensiones escanables como código fuente.
_SCANNABLE_EXTS = {".py", ".sh", ".bash", ".zsh", ".ps1", ".bat", ".js", ".ts", ".mjs"}

# Límites duros.
_MAX_FILES = 100
_MAX_FILE_BYTES = 1 * 1024 * 1024  # 1 MB por archivo
_MAX_BODY_BYTES = 500 * 1024  # 500 KB para SKILL.md


# ── API ─────────────────────────────────────────────────────────────────


def scan_skill_dir(skill_dir: Path) -> ScanResult:
    """Recorre la carpeta de la skill y aplica todas las reglas. Devuelve
    un ScanResult que el caller usa para decidir aceptar/rechazar."""
    res = ScanResult(skill_dir=skill_dir)
    if not skill_dir.exists() or not skill_dir.is_dir():
        return res

    # 1) SKILL.md (reglas de contenido + size limit)
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        try:
            data = skill_md.read_bytes()
        except OSError:
            data = b""
        if len(data) > _MAX_BODY_BYTES:
            res.findings.append(
                Finding(
                    rule_id="skill-too-large",
                    severity="critical",
                    file="SKILL.md",
                    line=0,
                    message=f"SKILL.md excede {_MAX_BODY_BYTES} bytes ({len(data)})",
                    evidence="",
                )
            )
        else:
            text = data.decode("utf-8", errors="replace")
            _apply_content_rules(text, "SKILL.md", res)
        res.scanned_files += 1

    # 2) Archivos de código fuente dentro de la skill.
    count = 0
    for sub in skill_dir.rglob("*"):
        if not sub.is_file():
            continue
        if sub.suffix.lower() not in _SCANNABLE_EXTS:
            continue
        if sub.name.startswith("."):
            continue
        if count >= _MAX_FILES:
            break
        try:
            size = sub.stat().st_size
        except OSError:
            continue
        if size > _MAX_FILE_BYTES:
            res.findings.append(
                Finding(
                    rule_id="file-too-large",
                    severity="info",
                    file=str(sub.relative_to(skill_dir)),
                    line=0,
                    message=f"Archivo {size} bytes — skip de scan",
                    evidence="",
                )
            )
            count += 1
            continue
        try:
            text = sub.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(sub.relative_to(skill_dir))
        _apply_line_rules(text, rel, res)
        _apply_source_rules(text, rel, res)
        res.scanned_files += 1
        count += 1

    return res


def validate_frontmatter(fm: dict) -> list[Finding]:
    """Valida el frontmatter parseado. Devuelve findings (no muta state).
    Llamado desde core.skills._load_one tras parsear el YAML."""
    out: list[Finding] = []

    name = (fm.get("name") or "").strip()
    desc = (fm.get("description") or "").strip()

    if not name:
        out.append(
            Finding(
                rule_id="frontmatter-missing-name",
                severity="critical",
                file="SKILL.md",
                line=0,
                message="Falta el campo 'name' en el frontmatter",
                evidence="",
            )
        )
    elif len(name) > 80 or not re.fullmatch(r"[a-zA-Z0-9_\-.]+", name):
        out.append(
            Finding(
                rule_id="frontmatter-bad-name",
                severity="critical",
                file="SKILL.md",
                line=0,
                message=f"'name' inválido: '{name[:40]}' (solo alfanumérico, guiones, puntos; <80 chars)",
                evidence=name[:80],
            )
        )

    if not desc:
        out.append(
            Finding(
                rule_id="frontmatter-missing-description",
                severity="critical",
                file="SKILL.md",
                line=0,
                message="Falta el campo 'description' en el frontmatter",
                evidence="",
            )
        )
    elif len(desc) > 500:
        out.append(
            Finding(
                rule_id="frontmatter-long-description",
                severity="warn",
                file="SKILL.md",
                line=0,
                message=f"'description' demasiado larga ({len(desc)} chars) — recortala a ~140 para el catálogo",
                evidence=desc[:80],
            )
        )

    return out


# ── Internals ───────────────────────────────────────────────────────────


def _evidence(line: str, max_len: int = 120) -> str:
    s = line.strip()
    return s if len(s) <= max_len else s[:max_len] + "…"


def _apply_line_rules(text: str, rel_path: str, res: ScanResult) -> None:
    for i, line in enumerate(text.splitlines(), start=1):
        for rule in LINE_RULES:
            if rule["pattern"].search(line):
                res.findings.append(
                    Finding(
                        rule_id=rule["id"],
                        severity=rule["severity"],
                        file=rel_path,
                        line=i,
                        message=rule["msg"],
                        evidence=_evidence(line),
                    )
                )


def _apply_source_rules(text: str, rel_path: str, res: ScanResult) -> None:
    for rule in SOURCE_RULES:
        prim = rule["primary"].search(text)
        if not prim:
            continue
        if rule["context"] is not None and not rule["context"].search(text):
            continue
        # Buscamos número de línea aproximado del primary match.
        line_no = text.count("\n", 0, prim.start()) + 1
        res.findings.append(
            Finding(
                rule_id=rule["id"],
                severity=rule["severity"],
                file=rel_path,
                line=line_no,
                message=rule["msg"],
                evidence=_evidence(prim.group(0)),
            )
        )


def _apply_content_rules(text: str, rel_path: str, res: ScanResult) -> None:
    for i, line in enumerate(text.splitlines(), start=1):
        for rule in SKILL_CONTENT_RULES:
            if rule["pattern"].search(line):
                res.findings.append(
                    Finding(
                        rule_id=rule["id"],
                        severity=rule["severity"],
                        file=rel_path,
                        line=i,
                        message=rule["msg"],
                        evidence=_evidence(line),
                    )
                )
