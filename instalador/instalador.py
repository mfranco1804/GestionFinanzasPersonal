"""
instalador.py — Instalador Gráfico Oficial y Autónomo para App Gestión Personal.

Funciona de dos maneras:
  1. AUTÓNOMO (OFFLINE TOTAL): Desempaqueta 'app_payload.dat' que viene embebido dentro del propio .exe.
  2. NUBE (ONLINE FALLBACK): Si no viniera embebido, descarga la versión oficial desde GitHub Releases.
"""

import os
import sys
import shutil
import hashlib
import subprocess
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import ssl

def _get_ssl_context():
    """Genera un contexto SSL permisivo y seguro para evitar fallos de certificados en Windows."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    except Exception:
        return None

# ═══════════════════════════════════════════════════════════════
#  CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════

GITHUB_OWNER = "mfranco1804"
GITHUB_REPO = "GestionFinanzasPersonal"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

DEFAULT_INSTALL_DIR = r"C:\AppGestionPersonal"
PROGRAM_NAME = "Gestión Financiera Personal"
EXE_NAME = "AppGestionPersonal.exe"
PAYLOAD_NAME = "app_payload.dat"
DB_NAME = "finanzas_personales.db"
ICO_NAME = "icono.ico"

# ═══════════════════════════════════════════════════════════════
#  LOCALIZADOR DE ARCHIVOS Y RECURSOS
# ═══════════════════════════════════════════════════════════════

def localizar_payload():
    """
    Busca el archivo binario del programa (embebido o local).
    Retorna la ruta absoluta si existe y tiene tamaño real.
    """
    candidatos = []
    
    # 1. Embebido dentro del .exe del instalador (PyInstaller _MEIPASS)
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        candidatos.append(os.path.join(sys._MEIPASS, PAYLOAD_NAME))
        candidatos.append(os.path.join(sys._MEIPASS, EXE_NAME))
        
    # 2. Junto al ejecutable del instalador (ej: carpeta o USB)
    exe_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
    candidatos.append(os.path.join(exe_dir, PAYLOAD_NAME))
    candidatos.append(os.path.join(exe_dir, EXE_NAME))
    candidatos.append(os.path.join(exe_dir, "compilado", EXE_NAME))
    candidatos.append(os.path.join(os.path.dirname(exe_dir), "compilado", EXE_NAME))

    for ruta in candidatos:
        if os.path.exists(ruta):
            try:
                if os.path.getsize(ruta) > 1000000: # Más de 1 MB
                    return ruta
            except OSError:
                pass
                
    return None

def localizar_archivo(nombre_archivo):
    """Busca recursos secundarios como iconos o bases de datos."""
    candidatos = []
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        candidatos.append(os.path.join(sys._MEIPASS, nombre_archivo))
    exe_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
    candidatos.append(os.path.join(exe_dir, nombre_archivo))
    candidatos.append(os.path.join(exe_dir, "compilado", nombre_archivo))
    candidatos.append(os.path.join(os.path.dirname(exe_dir), "compilado", nombre_archivo))
    candidatos.append(os.path.join(os.path.dirname(exe_dir), nombre_archivo))

    for ruta in candidatos:
        if os.path.exists(ruta):
            return ruta
    return None

def obtener_ultimo_release():
    """Consulta GitHub Releases."""
    try:
        ctx = _get_ssl_context()
        req = urllib.request.Request(
            GITHUB_API_URL,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "AppGestionPersonal-Installer/1.0"
            }
        )
        kwargs = {"timeout": 12}
        if ctx:
            kwargs["context"] = ctx
        with urllib.request.urlopen(req, **kwargs) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        print(f"[Instalador] No se pudo conectar a GitHub: {e}")
        return None

def obtener_urls_assets(release_data):
    if not release_data:
        return None, None, "1.0.0"
    exe_url = None
    checksums_url = None
    version = release_data.get("tag_name", "1.0.0")
    for asset in release_data.get("assets", []):
        name = asset.get("name", "").lower()
        if name == EXE_NAME.lower():
            exe_url = asset.get("browser_download_url")
        elif name.endswith(".exe") and not name.startswith("instalar") and not exe_url:
            exe_url = asset.get("browser_download_url")
        elif name == "checksums.sha256":
            checksums_url = asset.get("browser_download_url")
    return exe_url, checksums_url, version

def crear_acceso_directo_windows(target_exe, shortcut_path, icon_path=None):
    """Crea acceso directo en el escritorio."""
    try:
        icon_cmd = f'$s.IconLocation = "{icon_path}";' if (icon_path and os.path.exists(icon_path)) else ''
        ps_cmd = (
            f'$ws = New-Object -ComObject WScript.Shell; '
            f'$s = $ws.CreateShortcut("{shortcut_path}"); '
            f'$s.TargetPath = "{target_exe}"; '
            f'$s.WorkingDirectory = "{os.path.dirname(target_exe)}"; '
            f'{icon_cmd} '
            f'$s.Save()'
        )
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return True
    except Exception as e:
        print(f"Aviso acceso directo: {e}")
        return False

# ═══════════════════════════════════════════════════════════════
#  INTERFAZ GRÁFICA
# ═══════════════════════════════════════════════════════════════

class InstallerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Instalador — {PROGRAM_NAME}")
        self.root.geometry("540x420")
        self.root.resizable(False, False)
        self.root.configure(bg="#0f172a")

        ico = localizar_archivo(ICO_NAME)
        if ico:
            try:
                self.root.iconbitmap(ico)
            except Exception:
                pass

        self.install_dir = tk.StringVar(value=DEFAULT_INSTALL_DIR)
        self.status_text = tk.StringVar(value="Listo para instalar")
        self.progress_val = tk.DoubleVar(value=0)

        self._construir_ui()
        self._centrar_ventana()

    def _centrar_ventana(self):
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _construir_ui(self):
        header = tk.Frame(self.root, bg="#064e3b", height=85)
        header.pack(fill="x")
        header.pack_propagate(False)

        title = tk.Label(header, text="Gestión Financiera Personal", font=("Segoe UI", 15, "bold"), fg="#ffffff", bg="#064e3b")
        title.pack(anchor="w", padx=25, pady=(15, 2))

        subtitle = tk.Label(header, text="Instalador Oficial de Escritorio — Paquete Completo", font=("Segoe UI", 9), fg="#a7f3d0", bg="#064e3b")
        subtitle.pack(anchor="w", padx=25)

        body = tk.Frame(self.root, bg="#0f172a", padx=25, pady=20)
        body.pack(fill="both", expand=True)

        lbl_dir = tk.Label(body, text="Carpeta de Instalación:", font=("Segoe UI", 10, "bold"), fg="#e2e8f0", bg="#0f172a")
        lbl_dir.pack(anchor="w", pady=(0, 5))

        dir_frame = tk.Frame(body, bg="#0f172a")
        dir_frame.pack(fill="x", pady=(0, 15))

        entry_dir = tk.Entry(dir_frame, textvariable=self.install_dir, font=("Segoe UI", 9), bg="#1e293b", fg="#ffffff", insertbackground="white", bd=1, relief="solid")
        entry_dir.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 8))

        btn_browse = tk.Button(dir_frame, text="Examinar...", font=("Segoe UI", 9), bg="#334155", fg="#ffffff", activebackground="#475569", activeforeground="#ffffff", bd=0, padx=12, cursor="hand2", command=self._seleccionar_carpeta)
        btn_browse.pack(side="right")

        lbl_prog = tk.Label(body, textvariable=self.status_text, font=("Segoe UI", 9), fg="#94a3b8", bg="#0f172a")
        lbl_prog.pack(anchor="w", pady=(5, 5))

        style = ttk.Style()
        style.theme_use('default')
        style.configure("Emerald.Horizontal.TProgressbar", background="#10b981", troughcolor="#1e293b", bordercolor="#0f172a", lightcolor="#10b981", darkcolor="#059669")
        
        self.progress_bar = ttk.Progressbar(body, variable=self.progress_val, maximum=100, style="Emerald.Horizontal.TProgressbar")
        self.progress_bar.pack(fill="x", pady=(0, 20), ipady=2)

        btn_frame = tk.Frame(body, bg="#0f172a")
        btn_frame.pack(fill="x", side="bottom")

        self.btn_install = tk.Button(btn_frame, text="Instalar Ahora", font=("Segoe UI", 11, "bold"), bg="#059669", fg="#ffffff", activebackground="#047857", activeforeground="#ffffff", bd=0, padx=20, pady=8, cursor="hand2", command=self._iniciar_instalacion)
        self.btn_install.pack(side="right")

        btn_cancel = tk.Button(btn_frame, text="Cancelar", font=("Segoe UI", 10), bg="#1e293b", fg="#94a3b8", activebackground="#334155", activeforeground="#ffffff", bd=0, padx=15, pady=8, cursor="hand2", command=self.root.quit)
        btn_cancel.pack(side="right", padx=(0, 10))

    def _seleccionar_carpeta(self):
        carpeta = filedialog.askdirectory(initialdir=self.install_dir.get(), title="Seleccionar carpeta de instalación")
        if carpeta:
            self.install_dir.set(os.path.normpath(carpeta))

    def _iniciar_instalacion(self):
        self.btn_install.config(state="disabled", text="Instalando...")
        threading.Thread(target=self._proceso_instalacion, daemon=True).start()

    def _proceso_instalacion(self):
        dest_dir = self.install_dir.get().strip()
        try:
            os.makedirs(dest_dir, exist_ok=True)
        except Exception as e:
            self._mostrar_error(f"No se pudo crear la carpeta de instalación ({dest_dir}):\n{e}\n\nIntente ejecutar el instalador como Administrador o elija otra carpeta.")
            return

        dest_exe = os.path.join(dest_dir, EXE_NAME)
        dest_db = os.path.join(dest_dir, DB_NAME)
        dest_ico = os.path.join(dest_dir, ICO_NAME)

        # Cerrar procesos anteriores si estuvieran abiertos
        if os.path.exists(dest_exe):
            try:
                subprocess.run(["taskkill", "/f", "/im", EXE_NAME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                import time
                time.sleep(0.5)
            except Exception:
                pass

        exe_instalado = False

        # 1. Método A: Desempaquetar recurso embebido o local
        self.status_text.set("Desempaquetando archivos del sistema...")
        self.progress_val.set(25)
        
        payload_local = localizar_payload()
        if payload_local:
            try:
                self.status_text.set("Copiando ejecutable a la carpeta de destino...")
                self.progress_val.set(50)
                shutil.copy2(payload_local, dest_exe)
                if os.path.exists(dest_exe) and os.path.getsize(dest_exe) > 1000000:
                    exe_instalado = True
                    self.progress_val.set(75)
            except Exception as e_copy:
                print(f"Aviso al copiar payload local: {e_copy}")

        # 2. Método B: Fallback vía GitHub Releases (si no venía embebido)
        if not exe_instalado:
            self.status_text.set("Conectando con GitHub Releases...")
            self.progress_val.set(30)
            release_data = obtener_ultimo_release()
            exe_url, checksums_url, version = obtener_urls_assets(release_data)

            if exe_url:
                try:
                    self.status_text.set(f"Descargando versión {version} desde GitHub...")
                    ctx = _get_ssl_context()
                    req = urllib.request.Request(exe_url, headers={"User-Agent": "AppGestionPersonal-Installer/1.0"})
                    kwargs = {"timeout": 180}
                    if ctx:
                        kwargs["context"] = ctx

                    with urllib.request.urlopen(req, **kwargs) as resp:
                        total = int(resp.headers.get("Content-Length", 0))
                        descargado = 0
                        with open(dest_exe, "wb") as f:
                            while True:
                                chunk = resp.read(16384)
                                if not chunk:
                                    break
                                f.write(chunk)
                                descargado += len(chunk)
                                if total > 0:
                                    pct = 30 + (descargado / total) * 45
                                    self.progress_val.set(pct)
                                    self.status_text.set(f"Descargando: {descargado // (1024*1024)} MB / {total // (1024*1024)} MB")
                    exe_instalado = True
                except Exception as e_dl:
                    print(f"Error al descargar desde GitHub: {e_dl}")

        if not exe_instalado or not os.path.exists(dest_exe):
            self._mostrar_error(
                f"No se pudo instalar {EXE_NAME}.\n\n"
                f"Carpeta destino: {dest_dir}\n"
                "Verifique permisos de disco o asegúrese de que el archivo no esté bloqueado por un antivirus."
            )
            return

        # 3. Base de datos inicial (NUNCA sobreescribir si ya existe)
        self.status_text.set("Configurando base de datos...")
        self.progress_val.set(80)
        if not os.path.exists(dest_db):
            db_origen = localizar_archivo(DB_NAME)
            if db_origen and os.path.exists(db_origen):
                try:
                    shutil.copy2(db_origen, dest_db)
                except Exception:
                    pass

        # 4. Icono
        self.status_text.set("Configurando iconos...")
        self.progress_val.set(88)
        ico_origen = localizar_archivo(ICO_NAME)
        if ico_origen and os.path.exists(ico_origen):
            try:
                shutil.copy2(ico_origen, dest_ico)
            except Exception:
                pass

        # 5. Lanzador Iniciar_App.bat
        launcher_bat = os.path.join(dest_dir, "Iniciar_App.bat")
        with open(launcher_bat, "w", encoding="utf-8") as f:
            f.write("@echo off\n")
            f.write("title GESTION FINANCIERA PERSONAL\n")
            f.write(f'start "" "{EXE_NAME}"\n')

        # 6. Acceso directo en el Escritorio
        self.status_text.set("Creando acceso directo en el Escritorio...")
        self.progress_val.set(95)
        
        escritorios = [
            os.path.join(os.path.expanduser("~"), "Desktop"),
            os.path.join(os.path.expanduser("~"), "Escritorio"),
            os.path.join(os.environ.get("USERPROFILE", ""), "Desktop"),
            os.path.join(os.environ.get("PUBLIC", ""), "Desktop")
        ]
        
        for esc in escritorios:
            if os.path.exists(esc):
                shortcut_file = os.path.join(esc, f"{PROGRAM_NAME}.lnk")
                crear_acceso_directo_windows(dest_exe, shortcut_file, dest_ico if os.path.exists(dest_ico) else None)
                break

        self.progress_val.set(100)
        self.status_text.set("¡Instalación completada exitosamente!")
        self.root.after(300, self._finalizar_exito, dest_exe)

    def _finalizar_exito(self, target_exe):
        resp = messagebox.askyesno(
            "Instalación Exitosa",
            f"¡{PROGRAM_NAME} se ha instalado correctamente en:\n{self.install_dir.get()}\n\n¿Deseas abrir la aplicación ahora?"
        )
        if resp:
            try:
                subprocess.Popen(f'"{target_exe}"', shell=True, cwd=os.path.dirname(target_exe))
            except Exception as e:
                print(f"Error al iniciar app: {e}")
        self.root.quit()

    def _mostrar_error(self, mensaje):
        messagebox.showerror("Error de Instalación", mensaje)
        self.btn_install.config(state="normal", text="Reintentar")
        self.status_text.set("Error durante la instalación.")
        self.progress_val.set(0)

if __name__ == "__main__":
    root = tk.Tk()
    app = InstallerApp(root)
    root.mainloop()
