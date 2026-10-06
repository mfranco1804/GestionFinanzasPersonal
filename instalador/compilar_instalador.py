"""
compilar_instalador.py — Compila el instalador autónomo (Self-Contained Setup) con PyInstaller.

Embebe 'app_payload.dat' (copia binaria de AppGestionPersonal.exe), base de datos e iconos
para garantizar que el instalador funcione de forma inmediata, 100% offline y sin fallos en cualquier equipo.
"""

import os
import sys
import shutil
import time
import subprocess

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    
    instalador_src = os.path.join(script_dir, "instalador.py")
    build_dir = os.path.join(script_dir, "build")
    dist_dir = os.path.join(script_dir, "dist")
    output_dir = os.path.join(root_dir, "compilado")
    
    icono_path = os.path.join(root_dir, "icono.ico")
    exe_src = os.path.join(output_dir, "AppGestionPersonal.exe")
    db_src = os.path.join(output_dir, "finanzas_personales.db")
    
    if not os.path.exists(exe_src):
        print(f"[ERROR] No se encontró {exe_src}. Debe compilar primero el ejecutable principal.")
        sys.exit(1)

    # 1. Preparar archivo binario de datos 'app_payload.dat' para evitar que PyInstaller filtre el .exe
    payload_dat = os.path.join(script_dir, "app_payload.dat")
    print("\n[1/4] Preparando payload binario embebido (app_payload.dat)...")
    shutil.copy2(exe_src, payload_dat)
    print(f"  Tamaño del payload: {os.path.getsize(payload_dat) // 1024} KB")

    # 2. Limpiar carpetas temporales
    print("\n[2/4] Limpiando carpetas temporales del instalador...")
    for d in [build_dir, dist_dir]:
        if os.path.exists(d):
            shutil.rmtree(d, ignore_errors=True)
    
    # 3. Compilar instalador autónomo
    print("\n[3/4] Compilando instalador autónomo con PyInstaller...")
    sep = ";"  # Windows path separator
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "Instalar_AppGestionPersonal",
        "--clean",
        "--uac-admin",
        "--exclude-module=numpy",
        "--exclude-module=PIL",
        "--exclude-module=Pillow",
        "--exclude-module=pandas",
        "--exclude-module=scipy",
        "--exclude-module=matplotlib",
        "--exclude-module=torch",
        "--exclude-module=torchvision",
        "--exclude-module=flask",
        "--exclude-module=werkzeug",
        "--exclude-module=jinja2",
        "--exclude-module=waitress",
        f"--add-data={payload_dat}{sep}.",
        f"--workpath={build_dir}",
        f"--distpath={dist_dir}",
        "--noconfirm"
    ]
    
    if os.path.exists(db_src):
        cmd.append(f"--add-data={db_src}{sep}.")
        
    if os.path.exists(icono_path):
        cmd.append(f"--icon={icono_path}")
        cmd.append(f"--add-data={icono_path}{sep}.")
    
    cmd.append(instalador_src)
    
    print("  " + " ".join(cmd))
    
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Falló la compilación del instalador: {e}")
        # Limpiar payload temporal
        if os.path.exists(payload_dat):
            try:
                os.remove(payload_dat)
            except OSError:
                pass
        sys.exit(1)
        
    # 4. Mover a compilado/
    print("\n[4/4] Moviendo el instalador autónomo a compilado/...")
    os.makedirs(output_dir, exist_ok=True)
    src_exe = os.path.join(dist_dir, "Instalar_AppGestionPersonal.exe")
    dest_exe = os.path.join(output_dir, "Instalar_AppGestionPersonal.exe")
    
    try:
        subprocess.run(["taskkill", "/f", "/im", "Instalar_AppGestionPersonal.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
    except Exception:
        pass

    if os.path.exists(dest_exe):
        for retry in range(5):
            try:
                os.remove(dest_exe)
                break
            except Exception:
                time.sleep(1)

    if os.path.exists(src_exe):
        for retry in range(5):
            try:
                shutil.copy2(src_exe, dest_exe)
                print(f"  Instalador autónomo listo en: {dest_exe}")
                break
            except Exception as e_mv:
                if retry == 4:
                    print(f"  [AVISO] No se pudo sobrescribir de inmediato ({e_mv}). Reintentando...")
                time.sleep(1)
    else:
        print(f"  [ERROR] No se encontró el instalador en: {src_exe}")
        sys.exit(1)
        
    # Limpieza
    if os.path.exists(payload_dat):
        try:
            os.remove(payload_dat)
        except OSError:
            pass

    for d in [build_dir, dist_dir]:
        if os.path.exists(d):
            shutil.rmtree(d, ignore_errors=True)
            
    print("\n" + "="*60)
    print("¡INSTALADOR AUTÓNOMO GENERADO CON ÉXITO!")
    print(f"Archivo: {dest_exe}")
    print(f"Tamaño final: {os.path.getsize(dest_exe) // (1024*1024)} MB")
    print("Este archivo ya contiene toda la aplicación embebida de forma garantizada.")
    print("="*60)

if __name__ == "__main__":
    main()
