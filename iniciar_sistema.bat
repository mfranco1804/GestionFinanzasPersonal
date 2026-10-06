@echo off
title APP GESTION PERSONAL - SERVIDOR
color 0A
echo ==========================================
echo      INICIANDO GESTION PERSONAL
echo ==========================================
echo.
echo [INFO] Iniciando el servidor...
echo [INFO] No cierre esta ventana mientras use la aplicacion.
echo.
echo -------------------------------------------
echo Acceso en esta PC: http://localhost:5000
echo -------------------------------------------
echo.
echo Intentando abrir el navegador automaticamente...
start http://localhost:5000
echo.
echo Presione CTRL+C para detener el servidor.
echo.
python app.py
pause
