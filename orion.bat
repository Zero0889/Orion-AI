@echo off
title O.R.I.O.N
cd /d "%~dp0"
call .venv\Scripts\activate.bat

REM Sincroniza deps por si requirements.txt cambió desde el último arranque.
REM No-op cuando ya está todo al día (~1s); cuando hay deps nuevas, las baja
REM antes de arrancar y evita ModuleNotFoundError sorpresa.
echo [orion.bat] Sincronizando dependencias...
python -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo.
    echo [orion.bat] ERROR: pip install fallo. Revisa requirements.txt o tu conexion.
    pause
    exit /b 1
)

python -m orion
pause
