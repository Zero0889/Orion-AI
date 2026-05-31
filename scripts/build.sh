#!/usr/bin/env bash
# scripts/build.sh — Empaquetado Tauri para macOS / Linux (Fase 6).
#
# Pipeline idéntico al de Windows:
#   1. npm run build         → web/dist/
#   2. pyinstaller spec      → dist/orion-backend/
#   3. Renombrado por target-triple → src-tauri/binaries/
#   4. cargo tauri build     → src-tauri/target/release/bundle/
#
# Prerequisitos: Node 18+, Python 3.11 (.venv activado), Rust + cargo-tauri.
# Lanza desde la raíz del repo.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

PY="${PYTHON:-$REPO/.venv/bin/python}"
if [[ ! -x "$PY" ]]; then
    PY="$(command -v python3)"
fi

echo "==> 1/4  Frontend (npm run build)"
( cd "$REPO/web" && npm install --no-audit --no-fund && npm run build )

echo "==> 2/4  Backend (pyinstaller)"
"$PY" -m pip install -r "$REPO/requirements-dev.txt" --quiet
"$PY" -m PyInstaller "$REPO/packaging/orion_backend.spec" --clean --noconfirm

echo "==> 3/4  Preparando sidecar para Tauri"
TRIPLE="$(rustc -vV | grep '^host:' | awk '{print $2}')"
echo "    target-triple: $TRIPLE"

SRC="$REPO/dist/orion-backend/orion-backend"
DST_DIR="$REPO/src-tauri/binaries"
mkdir -p "$DST_DIR"
cp "$SRC" "$DST_DIR/orion-backend-$TRIPLE"
chmod +x "$DST_DIR/orion-backend-$TRIPLE"

# Carpeta de runtime de PyInstaller
cp -R "$REPO/dist/orion-backend/_internal" "$DST_DIR/_internal"

echo "==> 4/4  Tauri build"
( cd "$REPO/src-tauri" && cargo tauri build )

echo ""
echo "✓ Listo. Instalador en:"
find "$REPO/src-tauri/target/release/bundle/" -maxdepth 3 -type f \
    \( -name "*.dmg" -o -name "*.deb" -o -name "*.AppImage" -o -name "*.app.tar.gz" \) \
    2>/dev/null || true
