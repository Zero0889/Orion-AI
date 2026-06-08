@echo off
title O.R.I.O.N
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python main.py
pause
