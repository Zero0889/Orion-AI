# scripts/build.ps1 — Empaquetado Tauri para Windows (Fase 6).
#
# Pipeline:
#   1. Compilar frontend React  (npm run build)        → web/dist/
#   2. Compilar backend Python  (pyinstaller spec)     → dist/orion-backend/
#   3. Renombrar binario al target-triple esperado por Tauri
#   4. Compilar app Tauri       (cargo tauri build)    → src-tauri/target/release/bundle/
#
# Prerequisitos: Node 18+, Python 3.11 (.venv activado), Rust + cargo-tauri.
# Lanza desde la raíz del repo.

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path "$PSScriptRoot/..").Path
Set-Location $repo

Write-Host "==> 1/4  Frontend (npm run build)" -ForegroundColor Cyan
Push-Location "$repo/web"
npm install --no-audit --no-fund | Out-Null
npm run build
Pop-Location

Write-Host "==> 2/4  Backend (pyinstaller)" -ForegroundColor Cyan
& "$repo/.venv/Scripts/python.exe" -m pip install -r "$repo/requirements-dev.txt" --quiet
& "$repo/.venv/Scripts/python.exe" -m PyInstaller `
    "$repo/packaging/orion_backend.spec" --clean --noconfirm

Write-Host "==> 3/4  Preparando sidecar para Tauri" -ForegroundColor Cyan
$triple = (rustc -vV | Select-String "host:" -SimpleMatch | ForEach-Object {
    $_.ToString().Split(":")[1].Trim()
})
Write-Host "    target-triple: $triple"

$src = "$repo/dist/orion-backend/orion-backend.exe"
$dstDir = "$repo/src-tauri/binaries"
New-Item -ItemType Directory -Force $dstDir | Out-Null
Copy-Item $src "$dstDir/orion-backend-$triple.exe" -Force

# Tauri también necesita la carpeta de _internal con los datos. La
# copiamos como recurso para que el sidecar la encuentre al arrancar.
# (Esto se hace fuera del manifest porque la carpeta puede pesar 100+ MB
# y queremos comprimirla solo en el bundle final.)
Copy-Item "$repo/dist/orion-backend/_internal" `
    "$dstDir/_internal" -Recurse -Force

Write-Host "==> 4/4  Tauri build" -ForegroundColor Cyan
Push-Location "$repo/src-tauri"
cargo tauri build
Pop-Location

Write-Host ""
Write-Host "✓ Listo. Instalador en:" -ForegroundColor Green
Get-ChildItem -Recurse "$repo/src-tauri/target/release/bundle/" -Filter "*.msi"  -ErrorAction SilentlyContinue
Get-ChildItem -Recurse "$repo/src-tauri/target/release/bundle/" -Filter "*.exe" -ErrorAction SilentlyContinue
