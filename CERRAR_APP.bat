@echo off
title CERRAR PROCESOS - APP GESTION PERSONAL
echo ========================================================
echo       CERRANDO PROCESOS DE APP GESTION PERSONAL
echo ========================================================
echo.
taskkill /F /IM AppGestionPersonal.exe /T 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq APP GESTION PERSONAL*" 2>nul

:: Liberar puerto 5000 si estuviera ocupado
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5000') do (
    taskkill /F /PID %%a 2>nul
)

echo.
echo [OK] Procesos detenidos y puertos liberados exitosamente.
echo.
pause
