@echo off
REM ============================================================
REM  O.R.I.O.N - Launcher para Windows
REM ============================================================
REM  Detecta y resuelve automaticamente prerequisitos comunes:
REM    - .venv de Python (lo crea si falta)
REM    - Deps de Python (pip install)
REM    - Build del frontend (npm install + npm run build si no hay
REM      web\dist\)
REM  Solo arranca Orion cuando todo esta listo.
REM ============================================================

setlocal EnableDelayedExpansion
title O.R.I.O.N
cd /d "%~dp0"

REM ---------- 1. .venv ----------
if not exist ".venv\Scripts\python.exe" (
    echo [orion.bat] No encuentro .venv - lo creo ahora con Python del sistema...
    where py >nul 2>nul
    if errorlevel 1 (
        where python >nul 2>nul
        if errorlevel 1 (
            echo.
            echo [orion.bat] ERROR: no encuentro Python en el PATH.
            echo            Instala Python 3.11 o 3.12 desde python.org y volve a probar.
            pause
            exit /b 1
        )
        python -m venv .venv
    ) else (
        py -3 -m venv .venv
    )
    if errorlevel 1 (
        echo [orion.bat] ERROR: no pude crear el venv.
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat

REM ---------- 2. Python deps ----------
echo [orion.bat] Sincronizando dependencias de Python...
python -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo.
    echo [orion.bat] ERROR: pip install fallo. Revisa requirements.txt o tu conexion.
    pause
    exit /b 1
)

REM ---------- 3. Frontend (solo si falta) ----------
if not exist "web\dist\index.html" (
    echo [orion.bat] web\dist no esta - construyo el frontend ahora.
    where npm >nul 2>nul
    if errorlevel 1 (
        echo.
        echo [orion.bat] ERROR: no encuentro npm en el PATH.
        echo            Instala Node.js LTS desde nodejs.org y volve a probar.
        echo            Sin frontend Orion solo expone la API REST en :8765.
        pause
        exit /b 1
    )
    if not exist "web\node_modules" (
        echo [orion.bat] Instalando dependencias de Node ^(npm install^)...
        pushd web
        call npm install --no-audit --no-fund
        if errorlevel 1 (
            echo [orion.bat] ERROR: npm install fallo.
            popd
            pause
            exit /b 1
        )
        popd
    )
    echo [orion.bat] Compilando frontend ^(npm run build^)...
    pushd web
    call npm run build
    if errorlevel 1 (
        echo [orion.bat] ERROR: npm run build fallo.
        popd
        pause
        exit /b 1
    )
    popd
)

REM ---------- 4. Arrancar Orion ----------
echo [orion.bat] Listo. Arrancando Orion...
echo.
python -m orion
pause
