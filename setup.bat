@echo off
REM ============================================================
REM  setup.bat - Prepara un repo fresco de Orion en Windows
REM ============================================================
REM  Equivalente a "primer arranque sin sorpresas":
REM    1. Crea .venv (Python 3.11/3.12)
REM    2. pip install -r requirements.txt + requirements-dev.txt
REM    3. npm install + npm run build
REM    4. Avisa de los pasos siguientes (API key, OAuth Google)
REM  No arranca Orion. Para correrlo: orion.bat (o python -m orion).
REM ============================================================

setlocal EnableDelayedExpansion
title O.R.I.O.N - Setup
cd /d "%~dp0"

echo.
echo ============================================================
echo  O.R.I.O.N - Setup de primer arranque
echo ============================================================
echo.

REM ---------- Python check ----------
where py >nul 2>nul
if errorlevel 1 (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [setup] ERROR: no encuentro Python en el PATH.
        echo         Instala Python 3.11 o 3.12 desde python.org y volve a probar.
        pause
        exit /b 1
    )
    set "PY=python"
) else (
    set "PY=py -3"
)

REM ---------- Node check ----------
where npm >nul 2>nul
if errorlevel 1 (
    echo [setup] ADVERTENCIA: npm no esta en el PATH.
    echo         Instala Node.js LTS desde nodejs.org si queres usar la UI.
    echo         Sin frontend Orion solo expone la API REST en :8765.
    echo.
    set "HAVE_NPM=0"
) else (
    set "HAVE_NPM=1"
)

REM ---------- .venv ----------
if not exist ".venv\Scripts\python.exe" (
    echo [setup] Creando .venv...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo [setup] ERROR creando .venv.
        pause
        exit /b 1
    )
)
call .venv\Scripts\activate.bat

REM ---------- pip ----------
echo [setup] Actualizando pip...
python -m pip install --quiet --upgrade --disable-pip-version-check pip

echo [setup] Instalando dependencias de runtime ^(requirements.txt^)...
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo [setup] ERROR: requirements.txt fallo.
    pause
    exit /b 1
)

if exist "requirements-dev.txt" (
    echo [setup] Instalando dependencias de desarrollo ^(requirements-dev.txt^)...
    python -m pip install --quiet --disable-pip-version-check -r requirements-dev.txt
    if errorlevel 1 (
        echo [setup] ADVERTENCIA: requirements-dev fallo, pero podes seguir.
    )
)

REM ---------- Frontend ----------
if "%HAVE_NPM%"=="1" (
    if not exist "web\node_modules" (
        echo [setup] Instalando dependencias de Node ^(npm install^)...
        pushd web
        call npm install --no-audit --no-fund
        if errorlevel 1 (
            echo [setup] ERROR: npm install fallo.
            popd
            pause
            exit /b 1
        )
        popd
    ) else (
        echo [setup] web\node_modules ya existe, lo salteo.
    )

    echo [setup] Compilando frontend ^(npm run build^)...
    pushd web
    call npm run build
    if errorlevel 1 (
        echo [setup] ERROR: npm run build fallo.
        popd
        pause
        exit /b 1
    )
    popd
)

echo.
echo ============================================================
echo  Setup completo.
echo ============================================================
echo.
echo  Siguientes pasos:
echo    1. Conseguir una API key gratis de Gemini en:
echo         https://aistudio.google.com/app/apikey
echo    2. Arrancar Orion:  orion.bat
echo    3. Pegar la API key en el modal de bienvenida.
echo.
echo  Opcional ^(Gmail / Classroom / Drive^):
echo    Ver docs\SETUP_GOOGLE_OAUTH.md para conectar tu cuenta de Google.
echo.
pause
