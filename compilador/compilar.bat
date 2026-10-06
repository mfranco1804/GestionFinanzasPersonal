@echo off
title COMPILADOR - APP GESTION PERSONAL
color 0B
echo ========================================================
echo       COMPILADOR BINARIO - APP GESTION PERSONAL
echo ========================================================
echo.
cd /d "%~dp0"
python compilar.py %1
echo.
pause
