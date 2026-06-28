"""
Audit mobile de Orion — recorre cada vista con viewport Pixel 7 (412x915)
y captura screenshot + métricas para detectar bugs visuales.

Requiere que Orion esté corriendo en http://127.0.0.1:8765.

Métricas que reporta por vista:
  · screenshot full-page
  · overflow horizontal (rootScrollWidth > viewportWidth)
  · elementos con scroll-x indeseado
  · cantidad de letras truncadas (heurística: textos donde >50% líneas tienen 1-3 chars)

Salida:
  · screenshots PNG en /tmp/orion-audit/
  · reporte JSON con findings
"""

from __future__ import annotations

import contextlib
import json
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

# Forzar UTF-8 en stdout (en Windows cp1252 explota con ✓/⚠).
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

OUT = Path(tempfile.gettempdir()) / "orion-audit"
OUT.mkdir(parents=True, exist_ok=True)

BASE = "http://127.0.0.1:8765"

# (view_id, label, icon_aria, action_to_navigate)
VIEWS = [
    ("home", "Inicio"),
    ("chat", "Conversación"),
    ("notes", "Notas"),
    ("memory", "Memoria"),
    ("history", "Historial"),
    ("circuit", "Circuitos"),
    ("telemetry", "Telemetría"),
    ("agents", "Agentes"),
    ("iot", "IoT"),
    ("access", "Acceso"),
    ("mcp", "MCP"),
    ("skills", "Skills"),
    ("notifications", "Notificaciones"),
    ("diagnostics", "Diagnóstico"),
    ("settings", "Ajustes"),
]


def collect_metrics(page: Page) -> dict:
    """Mide overflow + recoge textos sospechosos vía JS en el browser."""
    js = """
    () => {
      const vw = window.innerWidth;
      const root = document.documentElement;
      const docW = Math.max(root.scrollWidth, document.body.scrollWidth);
      const overflowX = Math.max(0, docW - vw);

      // Heurística "letra-por-línea":
      // En tipografía normal a 412 px de viewport, una línea cabe ~50-60 chars.
      // Si un párrafo tiene >3 líneas y la mayoría son 1-3 chars, es ese bug.
      const suspects = [];
      const paragraphs = document.querySelectorAll('p, .orion-meta');
      paragraphs.forEach((el) => {
        const r = el.getBoundingClientRect();
        if (r.width <= 0 || r.height <= 0) return;
        const cs = getComputedStyle(el);
        const lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.4 || 16;
        const lineCount = Math.round(r.height / lh);
        const text = (el.textContent || '').trim();
        if (lineCount >= 4 && text.length > 0) {
          // chars por línea estimados:
          const cpl = text.length / lineCount;
          if (cpl < 6) {
            suspects.push({
              text: text.slice(0, 90),
              width: Math.round(r.width),
              lines: lineCount,
              cpl: Math.round(cpl * 10) / 10,
            });
          }
        }
      });

      // Elementos que sobresalen horizontalmente del viewport
      const protruders = [];
      document.querySelectorAll('*').forEach((el) => {
        const r = el.getBoundingClientRect();
        if (r.right > vw + 2 && r.width > 30 && r.width < vw - 10) {
          const tag = el.tagName.toLowerCase();
          if (['html', 'body', 'main', 'header'].includes(tag)) return;
          const text = (el.textContent || '').trim().slice(0, 60);
          protruders.push({
            tag,
            cls: (el.className || '').toString().slice(0, 60),
            right: Math.round(r.right),
            width: Math.round(r.width),
            text,
          });
        }
      });

      return {
        viewport: vw,
        docWidth: docW,
        overflowX,
        suspects: suspects.slice(0, 5),
        protruders: protruders.slice(0, 5),
      };
    }
    """
    return page.evaluate(js)


def dismiss_onboarding(page: Page) -> None:
    """Cierra el modal de Onboarding si aparece (primer arranque)."""
    try:
        skip = page.get_by_role(
            "button",
            name=lambda n: "saltar" in n.lower() or "después" in n.lower() or "cerrar" in n.lower(),
        )
        if skip.count() > 0:
            skip.first.click(timeout=1500)
            page.wait_for_timeout(400)
    except Exception:
        pass
    # Intento fallback con ESC
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
    except Exception:
        pass


def open_drawer(page: Page) -> None:
    """Abre el drawer mobile clickeando el botón panel-left del TopBar."""
    page.locator("header button").first.click(timeout=2500)
    # Espera a que el drawer termine la transición (300ms en CSS).
    page.wait_for_timeout(450)


def close_drawer_if_open(page: Page) -> None:
    """Si el backdrop sigue, lo clickeamos para cerrar y esperamos a que se vaya."""
    bd = page.locator('button[aria-label="Cerrar menú"]')
    if bd.count() > 0:
        with contextlib.suppress(Exception):
            bd.first.click(timeout=1500)
        with contextlib.suppress(Exception):
            bd.wait_for(state="detached", timeout=1500)


def navigate_to_id(page: Page, view_id: str) -> None:
    """Cambia la vista via window.__orion.setView — evita pelearnos con
    el drawer (que en mobile cubre el TopBar y se vuelve un nido de
    pointer-event conflicts en Playwright)."""
    page.evaluate(f"window.__orion && window.__orion.setView({view_id!r})")
    page.wait_for_timeout(700)


def main() -> int:
    report = {"views": [], "errors": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 412, "height": 915},
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True,
            user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        )
        page = ctx.new_page()

        # Captura errores de consola
        console_errors: list[str] = []
        page.on("pageerror", lambda e: console_errors.append(str(e)))
        page.on(
            "console",
            lambda m: console_errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None,
        )

        try:
            page.goto(BASE, wait_until="networkidle", timeout=20000)
        except Exception as e:
            report["errors"].append(f"goto failed: {e}")
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1

        page.wait_for_timeout(1200)
        dismiss_onboarding(page)
        page.wait_for_timeout(400)

        # Screenshot inicial (home con drawer cerrado)
        first_path = OUT / "00-initial.png"
        page.screenshot(path=str(first_path), full_page=True)

        # Screenshot del drawer abierto (chequeo del nav)
        try:
            open_drawer(page)
            page.screenshot(path=str(OUT / "01-drawer-open.png"), full_page=False)
            close_drawer_if_open(page)
        except Exception as e:
            report["errors"].append(f"drawer screenshot failed: {e}")

        for view_id, label in VIEWS:
            entry: dict = {"view": view_id, "label": label}
            try:
                navigate_to_id(page, view_id)
                close_drawer_if_open(page)
                m = collect_metrics(page)
                entry["metrics"] = m
                img = OUT / f"view-{view_id}.png"
                page.screenshot(path=str(img), full_page=True)
                entry["screenshot"] = str(img)
            except Exception as e:
                entry["error"] = str(e)
            report["views"].append(entry)

        report["console_errors"] = console_errors[:20]
        browser.close()

    out_json = OUT / "report.json"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport: {out_json}")
    # resumen corto
    print(f"\nViews auditadas: {len(report['views'])}")
    bugs = 0
    for v in report["views"]:
        m = v.get("metrics") or {}
        if m.get("overflowX", 0) > 0 or m.get("suspects") or m.get("protruders"):
            bugs += 1
            print(
                f"  ⚠ {v['view']:14s} overflow={m.get('overflowX', 0):3d}  "
                f"suspects={len(m.get('suspects', []))}  protruders={len(m.get('protruders', []))}"
            )
        else:
            print(f"  ✓ {v['view']:14s} ok")
    print(f"\nTotal con bugs: {bugs}/{len(report['views'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
