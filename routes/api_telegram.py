"""
routes/api_telegram.py — Blueprint para la gestión y configuración
del Bot de Telegram en Finanzas Personales.
"""
from flask import Blueprint, request, jsonify
from database import get_db
from services.telegram_bot_service import telegram_bot_service

telegram_bp = Blueprint('telegram_bp', __name__)

@telegram_bp.route('/api/cuadre/telegram/estado', methods=['GET'])
def get_telegram_estado():
    """Consulta el estado del bot de Telegram."""
    try:
        data = telegram_bot_service.obtener_estado()
        return jsonify(data)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@telegram_bp.route('/api/cuadre/telegram/config', methods=['POST'])
def save_telegram_config():
    """Guarda el token del bot y el modo de guardado (DIRECTO o INBOX)."""
    try:
        data = request.get_json() or {}
        bot_token = (data.get('bot_token') or '').strip()
        modo_guardado = (data.get('modo_guardado') or 'DIRECTO').strip()
        activar = bool(data.get('activar', True))

        res = telegram_bot_service.guardar_config_y_arrancar(bot_token, modo_guardado, activar=activar)
        return jsonify(res)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@telegram_bp.route('/api/cuadre/telegram/iniciar', methods=['POST'])
def iniciar_telegram_bot():
    """Inicia el servicio en segundo plano del bot de Telegram."""
    try:
        db = get_db()
        db.execute("UPDATE finanzas_telegram_config SET activo = 1 WHERE id = 1")
        db.commit()
        ok = telegram_bot_service.iniciar()
        if ok:
            return jsonify({'success': True, 'mensaje': 'Bot de Telegram iniciado correctamente.'})
        return jsonify({'success': False, 'mensaje': 'No se pudo iniciar el bot. Verifica que el Token esté configurado.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@telegram_bp.route('/api/cuadre/telegram/detener', methods=['POST'])
def detener_telegram_bot():
    """Detiene el servicio del bot de Telegram."""
    try:
        db = get_db()
        db.execute("UPDATE finanzas_telegram_config SET activo = 0 WHERE id = 1")
        db.commit()
        telegram_bot_service.detener()
        return jsonify({'success': True, 'mensaje': 'Bot de Telegram detenido.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@telegram_bp.route('/api/cuadre/telegram/sincronizar', methods=['POST'])
def sincronizar_telegram_ahora():
    """Fuerza la sincronización inmediata de mensajes desde Telegram."""
    try:
        data = telegram_bot_service.sincronizar_ahora()
        return jsonify(data)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@telegram_bp.route('/api/cuadre/telegram/desvincular', methods=['POST'])
def desvincular_telegram():
    """Desvincula el usuario actual para permitir vincular una nueva cuenta de Telegram."""
    try:
        db = get_db()
        db.execute("UPDATE finanzas_telegram_config SET chat_id_autorizado = '' WHERE id = 1")
        db.commit()
        return jsonify({'success': True, 'mensaje': 'Cuenta de Telegram desvinculada. El próximo mensaje que envíe /start se vinculará como dueño.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

