"""
upload_to_github.py — Script para subir releases y assets directamente a GitHub.
Repositorio: mfranco1804/GestionFinanzasPersonal
"""

import os
import sys
import json
import ssl
import subprocess
import urllib.request
import urllib.parse

REPO = "mfranco1804/GestionFinanzasPersonal"

def obtener_version_actual():
    """Lee la versión desde argumentos de línea de comandos o desde updater.py."""
    if len(sys.argv) > 1 and sys.argv[1].strip():
        v = sys.argv[1].strip()
        return v if v.startswith("v") else f"v{v}"
    root_dir = os.path.dirname(os.path.abspath(__file__))
    updater_file = os.path.join(root_dir, "updater.py")
    if os.path.exists(updater_file):
        with open(updater_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("APP_VERSION"):
                    v = line.split("=", 1)[1].strip().strip('"').strip("'")
                    return v if v.startswith("v") else f"v{v}"
    return "v1.0.0"

VERSION = obtener_version_actual()

def obtener_token():
    # 1. Variables de entorno
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token.strip()
    
    # 2. Archivo .env
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("GITHUB_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
                    
    # 3. Git Credential Manager
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

def main():
    token = obtener_token()
    if not token:
        print("[ERROR] No se encontró GITHUB_TOKEN en variables de entorno, .env ni en Git Credential Manager.")
        print("Para publicar automáticamente en GitHub Releases:")
        print("1. Crea un Personal Access Token (classic) en GitHub con scope 'repo'.")
        print("2. Crea un archivo .env en la raíz con: GITHUB_TOKEN=ghp_tu_token")
        sys.exit(1)

    root_dir = os.path.dirname(os.path.abspath(__file__))
    compilado_dir = os.path.join(root_dir, "compilado")
    
    files_to_upload = [
        os.path.join(compilado_dir, "AppGestionPersonal.exe"),
        os.path.join(compilado_dir, "Instalar_AppGestionPersonal.exe"),
        os.path.join(compilado_dir, "checksums.sha256")
    ]

    print(f"Conectando con https://github.com/{REPO} para publicar release {VERSION}...")
    
    # Obtener o crear el release
    release_url = f"https://api.github.com/repos/{REPO}/releases"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "GestionFinanzasPersonal-Publisher"
    }

    req = urllib.request.Request(f"{release_url}/tags/{VERSION}", headers=headers)
    upload_url = None
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            upload_url = data.get("upload_url", "").split("{")[0]
            print(f"[OK] Release {VERSION} ya existe en GitHub.")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"[INFO] Creando nuevo Release {VERSION} en GitHub...")
            checksums_path = os.path.join(compilado_dir, "checksums.sha256")
            chk_text = open(checksums_path, "r", encoding="utf-8").read() if os.path.exists(checksums_path) else ""
            body_payload = json.dumps({
                "tag_name": VERSION,
                "name": f"Gestión Financiera Personal {VERSION}",
                "body": f"## Versión Oficial {VERSION}\n\nDistribución oficial para Windows.\n\n### Checksums SHA-256\n```\n{chk_text}\n```",
                "draft": False,
                "prerelease": False
            }).encode("utf-8")
            create_req = urllib.request.Request(release_url, data=body_payload, headers={**headers, "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(create_req, timeout=15) as resp_c:
                    data = json.loads(resp_c.read().decode("utf-8"))
                    upload_url = data.get("upload_url", "").split("{")[0]
                    print(f"[OK] Release creado exitosamente: {data.get('html_url')}")
            except Exception as e_cr:
                print(f"[ERROR] No se pudo crear el release: {e_cr}")
                sys.exit(1)
        else:
            print(f"[ERROR] Error al consultar release: {e}")
            sys.exit(1)

    if not upload_url:
        print("[ERROR] No se obtuvo la upload_url del release.")
        sys.exit(1)

    # Obtener lista actual de assets para eliminar duplicados anteriores
    existing_assets = {a.get("name"): a.get("id") for a in data.get("assets", [])}

    # Subir cada archivo
    for filepath in files_to_upload:
        if not os.path.exists(filepath):
            print(f"[AVISO] Archivo no encontrado: {filepath}")
            continue

        filename = os.path.basename(filepath)
        size = os.path.getsize(filepath)
        content_type = "application/octet-stream" if filename.endswith(".exe") else "text/plain"

        # Si el asset ya existe en GitHub, eliminarlo primero para evitar error 422
        if filename in existing_assets:
            asset_id = existing_assets[filename]
            print(f"[INFO] Eliminando versión anterior de {filename} (ID: {asset_id})...")
            del_url = f"https://api.github.com/repos/{REPO}/releases/assets/{asset_id}"
            del_req = urllib.request.Request(del_url, method="DELETE", headers=headers)
            try:
                with urllib.request.urlopen(del_req, timeout=30) as del_resp:
                    print(f" -> [OK] Asset anterior {filename} eliminado.")
            except Exception as e_del:
                print(f" -> [AVISO] No se pudo eliminar asset anterior {filename}: {e_del}")
        
        target_url = f"{upload_url}?name={urllib.parse.quote(filename)}"
        print(f"Subiendo {filename} ({size // 1024} KB)...")
        
        with open(filepath, "rb") as f:
            file_bytes = f.read()

        up_req = urllib.request.Request(target_url, data=file_bytes, headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": content_type,
            "Content-Length": str(size),
            "User-Agent": "GestionFinanzasPersonal-Publisher"
        })
        
        try:
            with urllib.request.urlopen(up_req, timeout=1800) as resp_up:
                print(f" -> [OK] {filename} subido exitosamente!")
        except Exception as e_up:
            print(f" -> [ERROR] Falló subida de {filename}: {e_up}")

    print("\n¡Publicación finalizada con éxito!")

if __name__ == "__main__":
    main()
