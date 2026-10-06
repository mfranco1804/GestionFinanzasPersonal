"""
updater.py — Sistema de Auto-Actualización vía GitHub Releases para App Gestión Personal.

Este módulo se encarga de:
  1. Definir la versión actual del programa (APP_VERSION).
  2. Consultar GitHub Releases para detectar versiones nuevas.
  3. Descargar el nuevo .exe con verificación criptográfica SHA-256.
  4. Aplicar la actualización mediante un script .bat independiente de auto-reemplazo.
"""

import os
import sys
import json
import ssl
import hashlib
import urllib.request
import urllib.error
import certifi

def _get_ssl_context():
    """Genera un contexto SSL seguro usando los certificados actualizados de certifi."""
    try:
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        try:
            return ssl.create_default_context()
        except Exception:
            return None

# ═══════════════════════════════════════════════════════════════
#  CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════

# Versión actual del programa (fuente de verdad).
APP_VERSION = "1.0.0"

# Repositorio público de GitHub donde se publican los Releases.
GITHUB_OWNER = "mfranco1804"
GITHUB_REPO = "GestionFinanzasPersonal"
PROGRAM_NAME = "AppGestionPersonal"
EXE_NAME = f"{PROGRAM_NAME}.exe"

# URL de la API de GitHub para obtener el último Release.
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

# Timeout en segundos para las peticiones HTTP.
HTTP_TIMEOUT = 15


# ═══════════════════════════════════════════════════════════════
#  VERIFICAR ACTUALIZACIONES
# ═══════════════════════════════════════════════════════════════

def _parse_version(version_str):
    """Convierte un string de versión como '1.2.3' o 'v1.0.0' en una tupla (1, 2, 3) para comparación numérica."""
    try:
        clean = version_str.strip().lstrip("vV")
        return tuple(int(x) for x in clean.split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def check_for_updates():
    """
    Consulta GitHub Releases para verificar si hay una versión más nueva disponible.
    
    Retorna:
      - None si no hay actualización disponible o si hubo un error.
      - Un diccionario con la información de la actualización:
        {
            "version": "1.0.1",
            "download_url": "https://github.com/.../AppGestionPersonal.exe",
            "checksums_url": "https://github.com/.../checksums.sha256",
            "release_notes": "Notas del release..."
        }
    """
    try:
        ctx = _get_ssl_context()
        req = urllib.request.Request(
            GITHUB_API_URL,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": f"AppGestionPersonal-Updater/{APP_VERSION}"
            }
        )
        kwargs = {"timeout": HTTP_TIMEOUT}
        if ctx:
            kwargs["context"] = ctx

        with urllib.request.urlopen(req, **kwargs) as response:
            data = json.loads(response.read().decode("utf-8"))
        
        remote_version = data.get("tag_name", "0.0.0")
        
        # Comparar versiones
        if _parse_version(remote_version) <= _parse_version(APP_VERSION):
            return None  # Ya estamos en la última versión
        
        # Buscar el .exe y el archivo de checksums en los assets
        download_url = None
        checksums_url = None
        
        for asset in data.get("assets", []):
            name = asset.get("name", "").lower()
            if name.endswith(".exe") and not name.startswith("instalar"):
                download_url = asset.get("browser_download_url")
            elif name == "checksums.sha256":
                checksums_url = asset.get("browser_download_url")
        
        if not download_url:
            print("[Updater] Release encontrado pero no contiene un archivo ejecutable .exe.")
            return None
        
        return {
            "version": remote_version.lstrip("vV"),
            "download_url": download_url,
            "checksums_url": checksums_url,
            "release_notes": data.get("body", "Sin notas de actualización.")
        }
        
    except urllib.error.URLError as e:
        print(f"[Updater] No se pudo conectar a GitHub: {e}")
        return None
    except Exception as e:
        print(f"[Updater] Error al verificar actualizaciones: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
#  DESCARGAR ACTUALIZACIÓN
# ═══════════════════════════════════════════════════════════════

def _calculate_sha256(filepath):
    """Calcula el hash SHA-256 de un archivo local."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _get_expected_sha256(checksums_url, exe_filename):
    """Descarga el archivo checksums.sha256 y extrae el hash esperado para el .exe."""
    if not checksums_url:
        return None
    
    try:
        ctx = _get_ssl_context()
        req = urllib.request.Request(
            checksums_url,
            headers={"User-Agent": f"AppGestionPersonal-Updater/{APP_VERSION}"}
        )
        kwargs = {"timeout": HTTP_TIMEOUT}
        if ctx:
            kwargs["context"] = ctx

        with urllib.request.urlopen(req, **kwargs) as response:
            content = response.read().decode("utf-8")
        
        for line in content.strip().splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1].lower() == exe_filename.lower():
                return parts[0]
        
        return None
    except Exception as e:
        print(f"[Updater] No se pudo obtener checksums: {e}")
        return None


def download_update(download_url, checksums_url=None, progress_callback=None):
    """
    Descarga el nuevo .exe a un archivo temporal y verifica su integridad SHA-256.
    
    Args:
        download_url: URL directa del .exe en GitHub Releases.
        checksums_url: URL del archivo checksums.sha256 (opcional).
        progress_callback: Función callback(bytes_descargados, bytes_totales).
    
    Retorna:
        - Ruta al archivo temporal descargado si la descarga e integridad fueron exitosas.
        - None si ocurrió un error o la verificación falló.
    """
    temp_path = None
    try:
        exe_filename = download_url.split("/")[-1]
        expected_sha256 = _get_expected_sha256(checksums_url, exe_filename)
        
        ctx = _get_ssl_context()
        req = urllib.request.Request(
            download_url,
            headers={"User-Agent": f"AppGestionPersonal-Updater/{APP_VERSION}"}
        )
        
        # Guardar en la misma carpeta del ejecutable actual para asegurar movimiento atómico
        app_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
        temp_path = os.path.join(app_dir, f"_update_{os.getpid()}.exe.tmp")
        
        kwargs = {"timeout": 120}
        if ctx:
            kwargs["context"] = ctx

        with urllib.request.urlopen(req, **kwargs) as response:
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            
            with open(temp_path, "wb") as f:
                while True:
                    chunk = response.read(16384)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    if progress_callback and total_size > 0:
                        progress_callback(downloaded, total_size)
        
        # Verificación criptográfica SHA-256
        if expected_sha256:
            actual_sha256 = _calculate_sha256(temp_path)
            if actual_sha256.lower() != expected_sha256.lower():
                print(f"[Updater] ¡ERROR DE INTEGRIDAD! SHA-256 no coincide.")
                print(f"  Esperado: {expected_sha256}")
                print(f"  Obtenido: {actual_sha256}")
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return None
            print("[Updater] Verificación criptográfica SHA-256 exitosa.")
        else:
            print("[Updater] Advertencia: No se pudo verificar checksums.sha256 (archivo no provisto).")
        
        return temp_path
        
    except Exception as e:
        print(f"[Updater] Error al descargar actualización: {e}")
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        return None


# ═══════════════════════════════════════════════════════════════
#  APLICAR ACTUALIZACIÓN (REEMPLAZO INDEPENDIENTE CON .BAT)
# ═══════════════════════════════════════════════════════════════

def apply_update(new_exe_path):
    """
    Aplica la actualización reemplazando el ejecutable actual de forma limpia y segura.
    
    Genera un script .bat independiente que:
      1. Espera 3 segundos (para que el proceso actual termine de cerrar sockets y archivos).
      2. Elimina el .exe anterior.
      3. Renombra el nuevo .exe al nombre oficial del programa.
      4. Conserva intacta la base de datos finanzas_personales.db (NUNCA la toca).
      5. Inicia el programa actualizado.
      6. Se autodestruye.
    """
    import subprocess
    import secrets
    
    if getattr(sys, 'frozen', False):
        current_exe = sys.executable
    else:
        print("[Updater] No se puede aplicar actualización en modo desarrollo (código fuente).")
        return False
    
    current_dir = os.path.dirname(current_exe)
    current_name = os.path.basename(current_exe)
    new_name = os.path.basename(new_exe_path)
    
    bat_name = f"_upd_{secrets.token_hex(4)}.bat"
    bat_path = os.path.join(current_dir, bat_name)
    
    bat_content = f"""@echo off
setlocal enabledelayedexpansion
chcp 65001 >NUL
echo.
echo =======================================================
echo   ACTUALIZANDO GESTION FINANCIERA PERSONAL
echo   Por favor no cierre esta ventana...
echo =======================================================
echo.

:: Esperar a que el proceso anterior se cierre por completo
timeout /t 3 /nobreak > NUL

:: Bucle de reintento para borrar el ejecutable viejo
set "retry=0"
:retry_del
del /f /q "{current_name}" >nul 2>&1
if exist "{current_name}" (
    set /a "retry+=1"
    if !retry! lss 10 (
        timeout /t 2 /nobreak > NUL
        goto retry_del
    )
    echo [ERROR] No se pudo borrar el programa anterior.
    echo Cierre manualmente las instancias abiertas e intente de nuevo.
    pause
    goto :cleanup
)

:: Renombrar el nuevo ejecutable
ren "{new_name}" "{current_name}"
if not exist "{current_name}" (
    echo [ERROR] No se pudo renombrar el archivo de actualizacion.
    pause
    goto :cleanup
)

echo.
echo Actualizacion completada exitosamente!
echo Iniciando nueva version...
echo.

:: Iniciar el programa actualizado
start "" "{current_name}"

:cleanup
:: Autodestruir este script temporal
del /f /q "%~f0"
"""
    
    try:
        with open(bat_path, "w", encoding="ascii", errors="replace") as f:
            f.write(bat_content)
        
        # Iniciar en proceso desacoplado para sobrevivir al cierre de Python
        CREATE_BREAKAWAY_FROM_JOB = 0x01000000
        subprocess.Popen(
            f'cmd /c "{bat_path}"',
            shell=True,
            cwd=current_dir,
            creationflags=subprocess.CREATE_NEW_CONSOLE | CREATE_BREAKAWAY_FROM_JOB
        )
        
        print("[Updater] Script de auto-reemplazo lanzado exitosamente.")
        return True
        
    except Exception as e:
        print(f"[Updater] Error al lanzar el script de reemplazo: {e}")
        if os.path.exists(bat_path):
            try:
                os.remove(bat_path)
            except OSError:
                pass
        return False
