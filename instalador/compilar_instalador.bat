@echo off
title COMPILADOR INSTALADOR - APP GESTION PERSONAL
color 0B
echo ========================================================
echo   COMPILANDO INSTALADOR - APP GESTION PERSONAL
echo ========================================================
echo.
cd /d "%~dp0"
python compilar_instalador.py
echo.
pause
