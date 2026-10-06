"""
compilar_instalador.py — Compila el instalador autónomo (Self-Contained Setup) con PyInstaller.

Genera Instalar_AppGestionPersonal.exe autocontenido con la aplicación, base de datos e iconos embebidos
para que funcione de forma inmediata y 100% offline en cualquier equipo sin depender de internet ni de GitHub.
"""

import os
import sys
import shutil
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

    # 1. Limpiar carpetas temporales
    print("\n[1/3] Limpiando carpetas temporales del instalador...")
    for d in [build_dir, dist_dir]:
        if os.path.exists(d):
            shutil.rmtree(d, ignore_errors=True)
    
    # 2. Compilar instalador autónomo
    print("\n[2/3] Compilando instalador autónomo con PyInstaller...")
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
        f"--add-data={exe_src}{sep}.",
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
        sys.exit(1)
        
    # 3. Mover a compilado/
    print("\n[3/3] Moviendo el instalador autónomo a compilado/...")
    os.makedirs(output_dir, exist_ok=True)
    src_exe = os.path.join(dist_dir, "Instalar_AppGestionPersonal.exe")
    dest_exe = os.path.join(output_dir, "Instalar_AppGestionPersonal.exe")
    
    import time
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
    for d in [build_dir, dist_dir]:
        if os.path.exists(d):
            shutil.rmtree(d, ignore_errors=True)
            
    print("\n" + "="*60)
    print("¡INSTALADOR AUTÓNOMO GENERADO CON ÉXITO!")
    print(f"Archivo: {dest_exe}")
    print("Este archivo ya contiene AppGestionPersonal.exe embebido.")
    print("Funciona 100% OFFLINE en cualquier computadora sin errores 404.")
    print("="*60)

if __name__ == "__main__":
    main()
