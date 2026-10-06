"""
compilar.py — Compilador binario y publicador para App Gestión Personal.

Empaqueta toda la aplicación Flask junto con sus servicios en segundo plano,
base de datos SQLite, servidor de producción Waitress y módulo de auto-actualización
en un archivo ejecutable (.exe) binario cerrado usando PyInstaller.
"""

import os
import sys
import shutil
import subprocess
import sqlite3
import hashlib
import json
import urllib.request
import urllib.error

# ═══════════════════════════════════════════════════════════════
#  CONFIGURACIÓN DEL PROYECTO Y REPOSITORIO
# ═══════════════════════════════════════════════════════════════

GITHUB_OWNER = "mfranco1804"
GITHUB_REPO = "GestionFinanzasPersonal"
PROGRAM_NAME = "AppGestionPersonal"
EXE_NAME = f"{PROGRAM_NAME}.exe"

# ═══════════════════════════════════════════════════════════════
#  UTILIDADES
# ═══════════════════════════════════════════════════════════════

def limpiar_directorio(ruta):
    """Elimina un directorio de forma segura."""
    if os.path.exists(ruta):
        try:
            shutil.rmtree(ruta)
        except Exception as e:
            print(f"  [AVISO] No se pudo limpiar {ruta} de inmediato: {e}")

def copiar_y_preparar_bd(src_db, dest_db):
    """Prepara una base de datos limpia para distribución en nuevos equipos."""
    if not os.path.exists(src_db):
        print("  [INFO] No se encontró base de datos existente. Se inicializará al arrancar.")
        return False
        
    print("  Copiando plantilla de base de datos...")
    try:
        shutil.copy2(src_db, dest_db)
        # Asegurarse de que no queden bloqueos WAL temporales
        conn = sqlite3.connect(dest_db)
        conn.execute("PRAGMA journal_mode = DELETE;")
        conn.commit()
        conn.close()
        print("  Base de datos lista para distribución.")
        return True
    except Exception as e:
        print(f"  [ERROR] Al preparar la BD: {e}")
        return False

def calcular_sha256(filepath):
    """Calcula el hash SHA-256 de un archivo."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

def leer_version():
    """Lee APP_VERSION desde updater.py."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    updater_path = os.path.join(root_dir, "updater.py")
    
    if not os.path.exists(updater_path):
        return "1.0.0"
    
    with open(updater_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("APP_VERSION"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    return parts[1].strip().strip('"').strip("'")
    return "1.0.0"

def actualizar_version(nueva_version):
    """Actualiza la versión en updater.py."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    updater_path = os.path.join(root_dir, "updater.py")
    
    if not os.path.exists(updater_path):
        return
        
    with open(updater_path, "r", encoding="utf-8") as f:
        lineas = f.readlines()
        
    with open(updater_path, "w", encoding="utf-8") as f:
        for line in lineas:
            if line.strip().startswith("APP_VERSION"):
                f.write(f'APP_VERSION = "{nueva_version}"\n')
            else:
                f.write(line)

def leer_token_github():
    """Lee el token de GitHub desde variables de entorno, .env o Git Credential Manager."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token.strip()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    
    posibles_env = [
        os.path.join(script_dir, ".env"),
        os.path.join(root_dir, ".env")
    ]
    
    for env_path in posibles_env:
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("GITHUB_TOKEN="):
                            token = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if token:
                                return token
            except Exception:
                pass

    try:
        proc = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n",
            capture_output=True, text=True, timeout=5
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                if line.startswith("password="):
                    token = line.split("=", 1)[1].strip()
                    if token:
                        return token
    except Exception:
        pass

    return None

# ═══════════════════════════════════════════════════════════════
#  PUBLICACIÓN EN GITHUB RELEASES
# ═══════════════════════════════════════════════════════════════

def crear_release_github(version, token, checksums_text):
    """Crea un Release en GitHub o recupera uno existente y retorna la upload_url."""
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
    
    body_text = f"## App Gestión Personal v{version}\n\nDistribución y actualización oficial.\n\n### Checksums SHA-256\n```\n{checksums_text}\n```"
    
    data = json.dumps({
        "tag_name": f"v{version}",
        "name": f"App Gestión Personal v{version}",
        "body": body_text,
        "draft": False,
        "prerelease": False
    }).encode("utf-8")
    
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
        "User-Agent": "AppGestionPersonal-Publisher"
    })
    
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            res = json.loads(response.read().decode("utf-8"))
            return res.get("upload_url", "").split("{")[0], res.get("html_url")
    except urllib.error.HTTPError as e:
        if e.code == 422:
            print(f"  [INFO] El release v{version} ya existe en GitHub. Obteniendo URL de subida...")
            tag_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/tags/v{version}"
            req_tag = urllib.request.Request(tag_url, headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "AppGestionPersonal-Publisher"
            })
            try:
                with urllib.request.urlopen(req_tag, timeout=15) as resp_tag:
                    res_tag = json.loads(resp_tag.read().decode("utf-8"))
                    return res_tag.get("upload_url", "").split("{")[0], res_tag.get("html_url")
            except Exception as e2:
                print(f"  [ERROR] No se pudo obtener el release existente: {e2}")
                return None, None
        else:
            print(f"  [ERROR] Al crear release: {e}")
            return None, None
    except Exception as e:
        print(f"  [ERROR] Error de conexión: {e}")
        return None, None

def eliminar_asset_si_existe(upload_url, filename, token):
    """Si un archivo ya existe en el release, lo elimina para reemplazarlo limpiamente."""
    try:
        parts = upload_url.split("/releases/")
        if len(parts) >= 2:
            rel_id = parts[1].split("/")[0]
            assets_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/{rel_id}/assets"
            req = urllib.request.Request(assets_url, headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "AppGestionPersonal-Publisher"
            })
            with urllib.request.urlopen(req, timeout=15) as r:
                assets = json.loads(r.read().decode("utf-8"))
                for a in assets:
                    if a.get("name") == filename:
                        del_req = urllib.request.Request(a.get("url"), headers={
                            "Authorization": f"token {token}",
                            "Accept": "application/vnd.github.v3+json",
                            "User-Agent": "AppGestionPersonal-Publisher"
                        }, method="DELETE")
                        urllib.request.urlopen(del_req, timeout=15)
                        print(f"  [INFO] Asset previo '{filename}' eliminado para actualizarlo.")
                        break
    except Exception:
        pass

def subir_asset_github(upload_url, filepath, token):
    """Sube un archivo como asset de un Release de GitHub."""
    filename = os.path.basename(filepath)
    file_size = os.path.getsize(filepath)
    
    eliminar_asset_si_existe(upload_url, filename, token)
    
    content_type = "application/octet-stream" if filename.endswith(".exe") else "text/plain"
    url = f"{upload_url}?name={filename}"
    
    print(f"  Subiendo {filename} ({file_size // 1024} KB)...")
    with open(filepath, "rb") as f:
        file_bytes = f.read()

    req = urllib.request.Request(url, data=file_bytes, method="POST")
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("Content-Type", content_type)
    req.add_header("Content-Length", str(file_size))
    req.add_header("User-Agent", "AppGestionPersonal-Publisher")
    
    try:
        with urllib.request.urlopen(req, timeout=1800) as response:
            print(f"  [OK] {filename} subido exitosamente!")
            return True
    except Exception as e:
        print(f"  [ERROR] Falló la subida de {filename}: {e}")
        return False

def publicar_en_github(output_dir, version):
    """Orquesta la publicación en GitHub Releases si hay credenciales disponibles."""
    print("\n[6/6] Verificando publicación en GitHub Releases...")
    token = leer_token_github()
    if not token:
        print("  [AVISO] No se detectó GITHUB_TOKEN configurado.")
        print("  La aplicación se compiló exitosamente a nivel local para exportar en USB o red.")
        print("  Para auto-publicar en GitHub Releases en el futuro, configure GITHUB_TOKEN en .env.")
        return

    exe_path = os.path.join(output_dir, EXE_NAME)
    checksums_path = os.path.join(output_dir, "checksums.sha256")
    inst_exe = os.path.join(output_dir, f"Instalar_{PROGRAM_NAME}.exe")
    
    if not os.path.exists(exe_path) or not os.path.exists(checksums_path):
        print("  [ERROR] Archivos no encontrados para publicar.")
        return

    with open(checksums_path, "r", encoding="utf-8") as f:
        checksums_text = f.read().strip()

    print(f"  Creando Release v{version} en GitHub ({GITHUB_OWNER}/{GITHUB_REPO})...")
    upload_url, html_url = crear_release_github(version, token, checksums_text)
    if not upload_url:
        return

    subir_asset_github(upload_url, exe_path, token)
    subir_asset_github(upload_url, checksums_path, token)
    if os.path.exists(inst_exe):
        subir_asset_github(upload_url, inst_exe, token)
        
    print(f"  [OK] Release publicado en: {html_url}")

# ═══════════════════════════════════════════════════════════════
#  FLUJO PRINCIPAL DE COMPILACIÓN
# ═══════════════════════════════════════════════════════════════

def gestionar_version_interactiva():
    """
    Pregunta al usuario qué versión desea compilar, ofreciendo:
    1. Próximo parche semántico (ej: 1.0.0 -> 1.0.1) - Recomendado para actualizaciones.
    2. Próxima versión menor (ej: 1.0.0 -> 1.1.0) - Para nuevas características.
    3. Escribir versión personalizada manual.
    4. Mantener versión actual sin cambios.
    """
    version_actual = leer_version()
    
    # Si se pasó explícitamente por línea de comandos (ej: python compilar.py 1.0.1)
    if len(sys.argv) > 1:
        arg_v = sys.argv[1].strip().lstrip("vV")
        if arg_v:
            actualizar_version(arg_v)
            print(f"[INFO] Versión configurada desde argumentos de consola: v{arg_v}")
            return arg_v

    # Calcular versiones semánticas recomendadas
    partes = version_actual.split(".")
    try:
        mayor = int(partes[0])
        menor = int(partes[1]) if len(partes) > 1 else 0
        parche = int(partes[2]) if len(partes) > 2 else 0
        v_patch = f"{mayor}.{menor}.{parche + 1}"
        v_minor = f"{mayor}.{menor + 1}.0"
    except Exception:
        v_patch = "1.0.1"
        v_minor = "1.1.0"

    print("=" * 60)
    print(f"  VERSIÓN ACTUAL DEL SISTEMA: v{version_actual}")
    print("=" * 60)
    print("  Para que las otras computadoras detecten una ACTUALIZACIÓN automática,")
    print("  la versión debe ser numéricamente superior a la que tienen instalada (ej: 1.0.1 > 1.0.0).\n")
    print(f"  [1] v{v_patch} (Recomendado - Nueva actualización/parche)")
    print(f"  [2] v{v_minor} (Mejoras y nuevas funciones)")
    print(f"  [3] Mantener versión actual (v{version_actual})")
    print(f"  [4] Ingresar versión personalizada manualmente")
    print("=" * 60)

    version_elegida = v_patch
    try:
        eleccion = input(f"\nSelecciona una opción [Presiona ENTER para v{v_patch}]: ").strip()
        if eleccion == "" or eleccion == "1":
            version_elegida = v_patch
        elif eleccion == "2":
            version_elegida = v_minor
        elif eleccion == "3":
            version_elegida = version_actual
        elif eleccion == "4":
            custom = input("Escribe la versión deseada (ej: 1.0.2): ").strip().lstrip("vV")
            version_elegida = custom if custom else v_patch
        else:
            if "." in eleccion:
                version_elegida = eleccion.lstrip("vV")
            else:
                version_elegida = v_patch
    except (KeyboardInterrupt, EOFError):
        print("\n[INFO] Usando versión por defecto:", v_patch)
        version_elegida = v_patch

    actualizar_version(version_elegida)
    print(f"\n>> Versión establecida para esta compilación: v{version_elegida} <<\n")
    return version_elegida

def main(version=None):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    output_dir = os.path.join(root_dir, "compilado")
    build_dir = os.path.join(script_dir, "build")
    dist_dir = os.path.join(script_dir, "dist")
    spec_file = os.path.join(script_dir, f"{PROGRAM_NAME}.spec")

    if not version:
        version = leer_version()
    print(f"Versión de compilación activa: v{version}")

    # 1. Limpieza
    print("\n[1/6] Limpiando carpetas de compilación anteriores...")
    limpiar_directorio(build_dir)
    limpiar_directorio(dist_dir)
    if os.path.exists(spec_file):
        try:
            os.remove(spec_file)
        except OSError:
            pass

    # 2. Argumentos de PyInstaller
    main_app = os.path.join(root_dir, "app.py")
    templates_src = os.path.join(root_dir, "templates")
    routes_src = os.path.join(root_dir, "routes")
    services_src = os.path.join(root_dir, "services")
    utils_src = os.path.join(root_dir, "utils")
    static_src = os.path.join(root_dir, "static")
    icono_path = os.path.join(root_dir, "icono.ico")

    sep = ";"  # Windows path separator para PyInstaller

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", PROGRAM_NAME,
        f"--add-data={templates_src}{sep}templates",
        f"--add-data={routes_src}{sep}routes",
        f"--add-data={services_src}{sep}services",
        f"--add-data={utils_src}{sep}utils",
        "--hidden-import=waitress",
        "--hidden-import=sqlite3",
        "--hidden-import=certifi",
        "--hidden-import=updater",
        "--hidden-import=bs4",
        "--hidden-import=dotenv",
        "--uac-admin",
        "--clean",
        f"--workpath={build_dir}",
        f"--distpath={dist_dir}",
        "--noconfirm"
    ]

    if os.path.exists(static_src):
        cmd.append(f"--add-data={static_src}{sep}static")
    if os.path.exists(icono_path):
        cmd.append(f"--icon={icono_path}")

    cmd.append(main_app)

    print("\n[2/6] Ejecutando PyInstaller...")
    print("  " + " ".join(cmd))
    
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Falló PyInstaller: {e}")
        sys.exit(1)

    # 3. Mover a compilado/
    print("\n[3/6] Moviendo ejecutable a carpeta compilado/...")
    os.makedirs(output_dir, exist_ok=True)
    src_exe = os.path.join(dist_dir, EXE_NAME)
    dest_exe = os.path.join(output_dir, EXE_NAME)

    if os.path.exists(dest_exe):
        try:
            subprocess.run(["taskkill", "/f", "/im", EXE_NAME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            import time
            time.sleep(1)
            os.remove(dest_exe)
        except Exception:
            pass

    shutil.move(src_exe, dest_exe)
    print(f"  Ejecutable generado en: {dest_exe}")

    # 4. Privacidad y Seguridad: NO distribuir base de datos personal
    # La aplicación genera automáticamente una base de datos limpia con init_db() en el primer arranque.
    print("\n[4/6] Configurando seguridad de distribución (sin base de datos personal)...")
    dest_db = os.path.join(output_dir, "finanzas_personales.db")
    if os.path.exists(dest_db):
        try:
            os.remove(dest_db)
        except Exception:
            pass

    if os.path.exists(icono_path):
        try:
            shutil.copy2(icono_path, os.path.join(output_dir, "icono.ico"))
        except Exception:
            pass

    # Generar checksum SHA-256
    exe_hash = calcular_sha256(dest_exe)
    checksums_text = f"{exe_hash}  {EXE_NAME}"
    checksums_path = os.path.join(output_dir, "checksums.sha256")
    with open(checksums_path, "w", encoding="utf-8") as f:
        f.write(checksums_text + "\n")
    print(f"  SHA-256 ({EXE_NAME}): {exe_hash}")

    # Crear lanzador de acceso rápido Iniciar_App.bat
    launcher_bat = os.path.join(output_dir, "Iniciar_App.bat")
    with open(launcher_bat, "w", encoding="utf-8") as f:
        f.write("@echo off\n")
        f.write("title APP GESTION PERSONAL\n")
        f.write(f"start \"\" \"{EXE_NAME}\"\n")

    # 5. Limpieza de temporales
    print("\n[5/6] Limpiando temporales de compilación...")
    limpiar_directorio(build_dir)
    limpiar_directorio(dist_dir)
    if os.path.exists(spec_file):
        try:
            os.remove(spec_file)
        except OSError:
            pass

    # 5.5 Compilar instalador autónomo sincronizado
    print("\n[5.5] Compilando instalador autónomo sincronizado (Instalar_AppGestionPersonal.exe)...")
    compilar_inst_py = os.path.join(root_dir, "instalador", "compilar_instalador.py")
    if os.path.exists(compilar_inst_py):
        try:
            subprocess.run([sys.executable, compilar_inst_py], check=True)
            # Actualizar checksums con el nuevo instalador
            inst_path = os.path.join(output_dir, f"Instalar_{PROGRAM_NAME}.exe")
            if os.path.exists(inst_path):
                inst_hash = calcular_sha256(inst_path)
                with open(checksums_path, "a", encoding="utf-8") as f:
                    f.write(f"{inst_hash}  Instalar_{PROGRAM_NAME}.exe\n")
        except Exception as e_inst:
            print(f"  [AVISO] No se pudo compilar el instalador automáticamente: {e_inst}")

    # 6. Publicación en GitHub Releases
    publicar_en_github(output_dir, version)

    print("\n" + "="*60)
    print("¡COMPILACIÓN Y ACTUALIZACIÓN COMPLETADAS!")
    print(f"Versión publicada: v{version}")
    print(f"Carpeta lista para exportar a otros equipos:")
    print(f"  -> {output_dir}")
    print("="*60)

if __name__ == "__main__":
    print("\n" + "="*60)
    print("   COMPILADOR OFICIAL — APP GESTIÓN PERSONAL")
    print("="*60 + "\n")

    version_seleccionada = gestionar_version_interactiva()
    main(version_seleccionada)
