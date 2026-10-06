@echo off
echo ========================================================
echo      SISTEMA DE ACTUALIZACION - APP GESTION PERSONAL
echo ========================================================
echo.

cd /d "%~dp0"

REM 1. Crear carpeta de respaldos si no existe
if not exist "respaldos" mkdir "respaldos"

REM 2. Generar nombre de archivo con fecha y hora segura
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value 2^>nul') do set datetime=%%I
if defined datetime (
    set "FECHA_HORA=%datetime:~0,8%_%datetime:~8,6%"
) else (
    set "FECHA_HORA=%date:~-4%%date:~3,2%%date:~0,2%_%time:~0,2%%time:~3,2%%time:~6,2%"
    set "FECHA_HORA=%FECHA_HORA: =0%"
)
set "BACKUP_NAME=respaldos\finanzas_backup_%FECHA_HORA%.db"

REM 3. Hacer copia de seguridad de la base de datos finanzas_personales.db
if exist "finanzas_personales.db" (
    echo [INFO] Creando respaldo de seguridad de finanzas_personales.db...
    copy "finanzas_personales.db" "%BACKUP_NAME%" >nul
    echo [OK] Base de datos respaldada con exito en: %BACKUP_NAME%
) else (
    echo [ALERTA] No se encontro finanzas_personales.db previa, continuando...
)

REM 4. Limpiar respaldos antiguos (mas de 30 dias)
echo [INFO] Limpiando respaldos con mas de 30 dias de antiguedad...
forfiles /p "respaldos" /m *.db /d -30 /c "cmd /c del @path" 2>nul

REM 5. Actualizar codigo desde GitHub si es repositorio Git
if exist ".git" (
    echo.
    echo [INFO] Descargando ultimas mejoras de GitHub...
    git fetch origin master 2>nul || git fetch origin main 2>nul
    git reset --hard origin/master 2>nul || git reset --hard origin/main 2>nul
    if %errorlevel% neq 0 (
        echo [AVISO] No se pudo sincronizar git automaticamente (puede estar desconectado o sin repo remoto).
    )
)

REM 6. Verificar dependencias de Python
echo.
echo [INFO] Verificando e instalando dependencias de Python...
python -m pip install --upgrade -r requirements.txt >nul 2>&1

echo.
echo ========================================================
echo      ACTUALIZACION FINALIZADA CON EXITO
echo ========================================================
echo.
pause
