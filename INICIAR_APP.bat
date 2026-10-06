@echo off
title APP GESTION PERSONAL
color 0A
echo ========================================================
echo       INICIANDO APP GESTION PERSONAL
echo ========================================================
echo.

cd /d "%~dp0"
if exist "compilado\AppGestionPersonal.exe" (
    echo [INFO] Iniciando version de produccion compilada...
    start "" "compilado\AppGestionPersonal.exe"
) else (
    echo [INFO] Iniciando en modo ejecucion local...
    echo [INFO] No cierre esta ventana mientras use la aplicacion.
    echo.
    echo -------------------------------------------
    echo Acceso en esta PC: http://localhost:5000
    echo -------------------------------------------
    echo.
    python app.py
)
