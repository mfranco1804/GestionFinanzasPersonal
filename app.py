"""
app.py — Punto de entrada para la aplicación de Gestión Financiera Personal.
Misma pila tecnológica que APH: Flask + SQLite + HTML5/Bootstrap 5/Vanilla JS.
"""
import os
import sys
import secrets
import webbrowser
import threading
from flask import Flask, session, jsonify, request
from dotenv import load_dotenv

# Cargar variables de entorno si existen
load_dotenv()

# Database setup
from database import BASE_DIR, close_connection, get_cached_config, init_db, DB_PATH

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True

def get_or_create_secret_key():
    """Genera o recupera la clave de sesión en .secret_key ubicada en el directorio base persistente."""
    key_file = os.path.join(BASE_DIR, '.secret_key')
    if os.path.exists(key_file):
        try:
            with open(key_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception:
            pass
    key = secrets.token_hex(32)
    try:
        with open(key_file, 'w', encoding='utf-8') as f:
            f.write(key)
    except Exception:
        pass
    return key

app.secret_key = os.environ.get('SECRET_KEY') or get_or_create_secret_key()

app.teardown_appcontext(close_connection)

# Context processor
@app.context_processor
def inject_globals():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return dict(config=get_cached_config(), csrf_token=session['_csrf_token'])

# Register Blueprints
from routes.views import views_bp
from routes.api_cuadre_personal import cuadre_personal_bp
from routes.api_whatsapp import whatsapp_bp
from routes.api_telegram import telegram_bp
from routes.api_proyeccion import proyeccion_bp

app.register_blueprint(views_bp)
app.register_blueprint(cuadre_personal_bp)
app.register_blueprint(whatsapp_bp)
app.register_blueprint(telegram_bp)
app.register_blueprint(proyeccion_bp)

# ================= RUTAS DE ACTUALIZACIÓN (AUTO-UPDATER) =================
@app.route('/api/version', methods=['GET'])
def api_get_version():
    """Retorna la versión actual del sistema."""
    try:
        import updater
        return jsonify({"version": updater.APP_VERSION, "name": updater.PROGRAM_NAME})
    except Exception as e:
        return jsonify({"version": "1.0.0", "error": str(e)})

@app.route('/api/check-update', methods=['GET'])
def api_check_update():
    """Verifica si hay una actualización disponible en GitHub Releases."""
    try:
        import updater
        update_info = updater.check_for_updates()
        if update_info:
            return jsonify({
                "available": True,
                "current_version": updater.APP_VERSION,
                "new_version": update_info["version"],
                "release_notes": update_info.get("release_notes", "")
            })
        return jsonify({"available": False, "current_version": updater.APP_VERSION})
    except Exception as e:
        return jsonify({"available": False, "error": str(e), "current_version": "1.0.0"})

@app.route('/api/apply-update', methods=['POST'])
def api_apply_update():
    """Descarga e instala la actualización disponible y reinicia el sistema."""
    try:
        import updater
        update_info = updater.check_for_updates()
        if not update_info:
            return jsonify({"success": False, "error": "No hay actualizaciones disponibles."})
        
        new_exe = updater.download_update(
            update_info["download_url"],
            checksums_url=update_info.get("checksums_url")
        )
        
        if not new_exe:
            return jsonify({"success": False, "error": "Error al descargar la actualización o fallo en la verificación criptográfica SHA-256."})
        
        if updater.apply_update(new_exe):
            def shutdown_server():
                import time
                time.sleep(1.5)
                os._exit(0)
            threading.Thread(target=shutdown_server, daemon=True).start()
            return jsonify({"success": True, "message": "Actualización descargada exitosamente. La aplicación se reiniciará en unos segundos."})
        else:
            return jsonify({"success": False, "error": "No se pudo aplicar la actualización (¿está en modo desarrollo?)."})
    except Exception as e:
        return jsonify({"success": False, "error": f"Error durante la actualización: {str(e)}"})

# Servicios de arranque (Tasas y Telegram Bot)
from services.rates_service import sincronizar_tasas_arrancada
from services.telegram_bot_service import telegram_bot_service

if __name__ == '__main__':
    init_db()
    sincronizar_tasas_arrancada()
    
    # Iniciar bot de Telegram si está configurado como activo
    try:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        tg_cfg = conn.execute("SELECT activo, bot_token FROM finanzas_telegram_config WHERE id = 1").fetchone()
        if tg_cfg and tg_cfg['activo'] and tg_cfg['bot_token']:
            telegram_bot_service.iniciar()
        conn.close()
    except Exception as e_tg:
        print("Aviso al iniciar bot de Telegram:", e_tg)

    port = int(os.environ.get('PORT', 5000))

    # Comprobación de actualizaciones al iniciar si es ejecutable
    if getattr(sys, 'frozen', False):
        try:
            import updater
            print(f"[Updater] App Gestión Personal v{updater.APP_VERSION}")
            print("[Updater] Comprobando actualizaciones...")
            up_info = updater.check_for_updates()
            if up_info:
                print(f"[Updater] ¡Nueva versión disponible: v{up_info['version']}!")
            else:
                print("[Updater] El sistema está actualizado a la última versión.")
        except Exception as e_upd:
            print(f"[Updater] No se pudo verificar actualizaciones: {e_upd}")

    # Abrir navegador automáticamente tras iniciar el servidor
    def abrir_navegador():
        try:
            webbrowser.open(f"http://127.0.0.1:{port}")
        except Exception:
            pass
    threading.Timer(1.5, abrir_navegador).start()

    try:
        from waitress import serve
        threads = 50
        print(f"\n{'='*55}")
        print(f"  APP GESTION PERSONAL - SERVIDOR PROFESIONAL")
        print(f"  Servidor: Waitress ({threads} hilos concurrentes)")
        print(f"  Dirección: http://127.0.0.1:{port}")
        print(f"{'='*55}\n")
        serve(app, host='0.0.0.0', port=port, threads=threads)
    except ImportError:
        print(f"=== Servidor iniciado en http://127.0.0.1:{port} ===")
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
