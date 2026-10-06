"""
services/telegram_bot_service.py — Servicio de integración oficial con Telegram Bot API
para Gestión Financiera Personal.

Permite:
1. Recibir gastos, ingresos y cambios internos directamente desde Telegram vía HTTP Long Polling.
2. Procesar con el parser inteligente de 3 vías con soporte para tasas BCV y Binance USDT.
3. Guardar directamente en las tablas contables o en la Bandeja de Entrada (configurable).
4. Responder al usuario en tiempo real con comprobantes detallados, tasas y balances.
"""
import os
import re
import time
import json
import logging
import threading
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Optional, Dict, Any, List

from database import get_db, DB_PATH, BASE_DIR
from utils.whatsapp_parser import parsear_mensaje_whatsapp, calcular_hash_mensaje

logger = logging.getLogger("TelegramBotService")
logger.setLevel(logging.INFO)

LOG_PATH = os.path.join(BASE_DIR, "telegram_service.log")

if not logger.handlers:
    fh = logging.FileHandler(LOG_PATH, encoding='utf-8')
    fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(fh)

def get_service_db():
    try:
        from flask import has_app_context
        if has_app_context():
            return get_db()
    except Exception:
        pass
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

import ssl
import urllib.error

try:
    import certifi
    CERTIFI_PATH = certifi.where()
except Exception:
    CERTIFI_PATH = None

def sanitizar_bot_token(raw_token: str) -> str:
    """Limpia y valida el formato del token de Telegram."""
    if not raw_token:
        return ""
    token = raw_token.strip().strip('"').strip("'")
    # Remover prefijos de URLs si el usuario pegó la URL entera
    if "api.telegram.org/bot" in token:
        token = token.split("api.telegram.org/bot")[-1].split("/")[0]
    # Si pegó con el prefijo bot (ej: bot123456:ABC...)
    if token.lower().startswith("bot") and ":" in token:
        token = token[3:]
    return token.strip()

class TelegramBotService:
    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

    def _get_ssl_context(self) -> ssl.SSLContext:
        """Crea un contexto SSL seguro y resiliente con soporte para certifi y Windows."""
        try:
            if CERTIFI_PATH and os.path.exists(CERTIFI_PATH):
                return ssl.create_default_context(cafile=CERTIFI_PATH)
            return ssl.create_default_context()
        except Exception:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx

    def _api_request(self, token: str, method: str, params: Optional[Dict[str, Any]] = None, timeout: int = 30) -> Dict[str, Any]:
        """Realiza una petición HTTP a la API oficial de Telegram con manejo de SSL y errores."""
        token = sanitizar_bot_token(token)
        url = f"https://api.telegram.org/bot{token}/{method}"
        headers = {"User-Agent": "AppGestionPersonal/1.0", "Content-Type": "application/json"}
        data_bytes = json.dumps(params or {}).encode('utf-8') if params else None
        
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST" if params else "GET")
        ctx = self._get_ssl_context()

        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as response:
                res_body = response.read().decode('utf-8')
                return json.loads(res_body)
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode('utf-8')
                data = json.loads(err_body)
                return data
            except Exception:
                return {"ok": False, "error_code": e.code, "description": f"Error HTTP {e.code}: {e.reason}"}
        except urllib.error.URLError as e:
            # Fallback reintento con SSL permisivo en caso de interceptor local
            try:
                fallback_ctx = ssl.create_default_context()
                fallback_ctx.check_hostname = False
                fallback_ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(req, context=fallback_ctx, timeout=timeout) as response:
                    res_body = response.read().decode('utf-8')
                    return json.loads(res_body)
            except Exception:
                return {"ok": False, "description": f"Error de conexión con Telegram: {str(e.reason)}"}
        except Exception as e:
            return {"ok": False, "description": f"Error inesperado: {str(e)}"}

    def verificar_token(self, token: str) -> Dict[str, Any]:
        """Comprueba si el Token de BotFather es válido obteniendo la información del bot."""
        token = sanitizar_bot_token(token)
        if not token:
            return {"success": False, "error": "El token no puede estar vacío."}
        try:
            res = self._api_request(token, "getMe", timeout=12)
            if res.get("ok"):
                user = res.get("result", {})
                return {
                    "success": True,
                    "bot_id": user.get("id"),
                    "bot_username": user.get("username"),
                    "bot_first_name": user.get("first_name")
                }
            desc = res.get("description", "Token inválido o no reconocido por Telegram.")
            if "unauthorized" in desc.lower():
                desc = "Token no autorizado (401). Verifica que lo hayas copiado exactamente de @BotFather."
            elif "not found" in desc.lower():
                desc = "Bot no encontrado (404). Verifica que el formato del Token sea correcto (ej: 7123456789:AAHk...)."
            return {"success": False, "error": desc}
        except Exception as e:
            return {"success": False, "error": f"Error conectando con Telegram API: {str(e)}"}

    def enviar_mensaje(self, token: str, chat_id: str, texto: str, parse_mode: str = "Markdown") -> bool:
        """Envía un mensaje de respuesta a un chat de Telegram."""
        try:
            res = self._api_request(token, "sendMessage", {
                "chat_id": chat_id,
                "text": texto,
                "parse_mode": parse_mode
            }, timeout=10)
            return bool(res.get("ok"))
        except Exception as e:
            logger.error(f"Error enviando mensaje a chat {chat_id}: {e}")
            return False

    def obtener_estado(self) -> Dict[str, Any]:
        """Retorna el estado actual de configuración y ejecución del bot."""
        db = get_service_db()
        row = db.execute("SELECT * FROM finanzas_telegram_config WHERE id = 1").fetchone()
        
        activo_db = bool(row["activo"]) if row else False
        is_thread_alive = self._thread is not None and self._thread.is_alive()
        
        # Conteo de pendientes en bandeja
        pendientes = db.execute("SELECT COUNT(*) as c FROM finanzas_whatsapp_inbox WHERE estado = 'PENDIENTE'").fetchone()
        pendientes_count = pendientes['c'] if pendientes else 0

        return {
            "success": True,
            "activo": is_thread_alive and self._running,
            "activo_en_config": activo_db,
            "bot_username": row["bot_username"] if row else "",
            "bot_token_configurado": bool(row and row["bot_token"]),
            "chat_id_autorizado": row["chat_id_autorizado"] if row else "",
            "modo_guardado": row["modo_guardado"] if row else "DIRECTO",
            "ultima_actividad": row["ultima_actividad"] if row else "",
            "pendientes_count": pendientes_count
        }

    def guardar_config_y_arrancar(self, bot_token: str, modo_guardado: str = "DIRECTO", activar: bool = True) -> Dict[str, Any]:
        """Guarda la configuración y arranca/detiene el servicio."""
        bot_token = (bot_token or "").strip()
        modo_guardado = (modo_guardado or "DIRECTO").strip().upper()
        if modo_guardado not in ['DIRECTO', 'INBOX']:
            modo_guardado = 'DIRECTO'

        db = get_service_db()
        existing = db.execute("SELECT bot_token, bot_username FROM finanzas_telegram_config WHERE id = 1").fetchone()

        username = ""
        if bot_token:
            check = self.verificar_token(bot_token)
            if not check.get("success"):
                return {"success": False, "error": check.get("error")}
            username = check.get("bot_username", "")
        else:
            if existing and existing["bot_token"]:
                bot_token = existing["bot_token"]
                username = existing["bot_username"] or ""
            else:
                return {"success": False, "error": "Por favor introduce el Token de BotFather para continuar."}

        db.execute("""
            UPDATE finanzas_telegram_config
            SET bot_token = ?,
                bot_username = ?,
                modo_guardado = ?,
                activo = ?
            WHERE id = 1
        """, (bot_token, username, modo_guardado, 1 if activar and bot_token else 0))
        db.commit()

        if activar and bot_token:
            self.iniciar()
        else:
            self.detener()

        return {
            "success": True,
            "mensaje": f"Bot @{username} configurado y listo en modo {modo_guardado}.",
            "bot_username": username,
            "activo": self._running
        }

    def sincronizar_ahora(self) -> Dict[str, Any]:
        """Fuerza la consulta inmediata o refresca el estado si el daemon en vivo ya está escuchando."""
        db = get_service_db()
        cfg = db.execute("SELECT bot_token, chat_id_autorizado, modo_guardado, ultimo_update_id FROM finanzas_telegram_config WHERE id = 1").fetchone()
        if not cfg or not cfg["bot_token"]:
            return {"success": False, "error": "No hay un Bot de Telegram configurado con Token."}

        # Si el hilo ya está corriendo en tiempo real, no abrimos otro getUpdates simultáneo
        # para evitar el error 409 Conflict de Telegram.
        if self._running and self._thread and self._thread.is_alive():
            pendientes = db.execute("SELECT COUNT(*) as c FROM finanzas_whatsapp_inbox WHERE estado = 'PENDIENTE'").fetchone()
            count = pendientes['c'] if pendientes else 0
            return {
                "success": True,
                "nuevos_mensajes": 0,
                "procesados": 0,
                "mensaje": "El bot está conectado en tiempo real. Todos los mensajes se procesan al instante.",
                "pendientes_count": count
            }

        token = cfg["bot_token"]
        chat_id_auth = (cfg["chat_id_autorizado"] or "").strip()
        modo_guardado = cfg["modo_guardado"] or "DIRECTO"
        offset = int(cfg["ultimo_update_id"] or 0) + 1 if cfg["ultimo_update_id"] else 0

        try:
            params = {"offset": offset, "timeout": 0, "allowed_updates": ["message"]}
            res = self._api_request(token, "getUpdates", params, timeout=12)
            if not res.get("ok"):
                desc = res.get("description", "Error consultando actualizaciones")
                if "conflict" in desc.lower():
                    return {"success": True, "mensaje": "El bot ya está recibiendo mensajes en tiempo real en segundo plano.", "procesados": 0}
                return {"success": False, "error": desc}

            updates = res.get("result", [])
            procesados = 0
            for upd in updates:
                upd_id = upd.get("update_id", 0)
                offset = max(offset, upd_id + 1)
                try:
                    db.execute("UPDATE finanzas_telegram_config SET ultimo_update_id = ? WHERE id = 1", (upd_id,))
                    db.commit()
                except Exception:
                    pass

                msg = upd.get("message")
                if not msg or "text" not in msg:
                    continue
                self._procesar_mensaje_recibido(token, msg, chat_id_auth, modo_guardado)
                procesados += 1

            return {
                "success": True,
                "nuevos_mensajes": len(updates),
                "procesados": procesados,
                "mensaje": f"¡Se sincronizaron {procesados} movimiento(s) de Telegram!" if procesados > 0 else "No hay mensajes nuevos en Telegram. Todo está al día."
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def iniciar(self) -> bool:
        """Inicia el hilo en segundo plano para escuchar mensajes de Telegram."""
        with self._lock:
            if self._running and self._thread and self._thread.is_alive():
                return True
            
            db = get_service_db()
            row = db.execute("SELECT bot_token FROM finanzas_telegram_config WHERE id = 1").fetchone()
            if not row or not row["bot_token"]:
                logger.warning("No hay bot_token configurado para iniciar Telegram Bot.")
                return False

            self._running = True
            self._thread = threading.Thread(target=self._polling_worker, daemon=True, name="TelegramBotWorker")
            self._thread.start()
            logger.info("Hilo de Telegram Bot iniciado exitosamente.")
            return True

    def detener(self):
        """Detiene el servicio de escucha de Telegram."""
        with self._lock:
            self._running = False
            logger.info("Solicitud de detención de Telegram Bot enviada.")

    def _polling_worker(self):
        """Bucle principal de Long Polling de Telegram."""
        offset = 0
        logger.info("Telegram Bot Worker en ejecución...")
        
        # Recuperar último offset
        try:
            db = get_service_db()
            cfg = db.execute("SELECT bot_token, ultimo_update_id FROM finanzas_telegram_config WHERE id = 1").fetchone()
            if cfg and cfg["ultimo_update_id"]:
                offset = int(cfg["ultimo_update_id"]) + 1
        except Exception:
            pass

        while self._running:
            try:
                db = get_service_db()
                cfg = db.execute("SELECT bot_token, chat_id_autorizado, modo_guardado FROM finanzas_telegram_config WHERE id = 1").fetchone()
                if not cfg or not cfg["bot_token"]:
                    time.sleep(3)
                    continue

                token = cfg["bot_token"]
                chat_id_auth = (cfg["chat_id_autorizado"] or "").strip()
                modo_guardado = cfg["modo_guardado"] or "DIRECTO"

                # Long Polling con timeout de 20s
                params = {"offset": offset, "timeout": 20, "allowed_updates": ["message"]}
                res = self._api_request(token, "getUpdates", params, timeout=28)

                if not res.get("ok"):
                    desc = str(res.get("description", ""))
                    if "conflict" in desc.lower():
                        logger.warning("Telegram Bot: detectado 409 Conflict (otra instancia activa consultando getUpdates). Pausando 8s...")
                        time.sleep(8)
                    else:
                        time.sleep(3)
                    continue

                updates = res.get("result", [])
                for upd in updates:
                    upd_id = upd.get("update_id", 0)
                    offset = max(offset, upd_id + 1)
                    
                    # Actualizar offset en DB
                    try:
                        db.execute("UPDATE finanzas_telegram_config SET ultimo_update_id = ? WHERE id = 1", (upd_id,))
                        db.commit()
                    except Exception:
                        pass

                    msg = upd.get("message")
                    if not msg or "text" not in msg:
                        continue

                    self._procesar_mensaje_recibido(token, msg, chat_id_auth, modo_guardado)

            except Exception as e:
                logger.error(f"Error en bucle de polling de Telegram: {e}")
                time.sleep(3)

        logger.info("Telegram Bot Worker detenido.")

    def _procesar_mensaje_recibido(self, token: str, msg: Dict[str, Any], chat_id_auth: str, modo_guardado: str):
        """Procesa un mensaje de texto recibido en Telegram."""
        chat_id = str(msg.get("chat", {}).get("id", ""))
        sender_name = msg.get("from", {}).get("first_name", "Yo")
        username = msg.get("from", {}).get("username", "")
        texto = msg.get("text", "").strip()

        if not texto or not chat_id:
            return

        db = get_service_db()
        ahora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. Comandos de control y vinculación (/start, /ayuda, /tasas, /balance)
        if texto.startswith("/"):
            cmd = texto.split()[0].lower()
            
            if cmd in ["/start", "/vincular"]:
                # Si no había chat autorizado, vincular automáticamente a este usuario
                db.execute("UPDATE finanzas_telegram_config SET chat_id_autorizado = ?, ultima_actividad = ? WHERE id = 1", (chat_id, ahora_str))
                db.commit()
                
                resp = (
                    f"👋 *¡Hola {sender_name}!* 🎯\n\n"
                    f"Tu cuenta de Telegram ha sido *vinculada exitosamente* a tu sistema de *Gestión Financiera Personal*.\n\n"
                    f"💡 *¿Cómo registrar movimientos?*\n"
                    f"Simplemente envíame un mensaje normal:\n"
                    f"• `Almuerzo 12 $` *(Gasto en Efectivo)*\n"
                    f"• `Gasolina 500 bs` *(Gasto en Bolívares)*\n"
                    f"• `Cobro freelance 250 $` *(Ingreso)*\n"
                    f"• `Cambio 50 usdt a bs tasa 950` *(Cambio de pote)*\n\n"
                    f"⚙️ *Comandos útiles:*\n"
                    f"• `/tasas` — Ver tasas activas (BCV, Binance USDT, Euro)\n"
                    f"• `/balance` — Resumen financiero del mes\n"
                    f"• `/modo directo` — Guardar directo en cuentas\n"
                    f"• `/modo inbox` — Enviar a Bandeja de Entrada\n"
                )
                self.enviar_mensaje(token, chat_id, resp)
                return

            # Verificar autorización para el resto de comandos
            if chat_id_auth and chat_id != chat_id_auth:
                self.enviar_mensaje(token, chat_id, "⛔ *Acceso no autorizado.* Este bot es privado para un solo usuario.")
                return

            if cmd in ["/tasas", "/tasa"]:
                cfg_row = db.execute("SELECT tasa_bcv, tasa_usdt, tasa_bcv_euro, tasas_updated_at FROM app_config WHERE id = 1").fetchone()
                bcv = cfg_row["tasa_bcv"] if cfg_row else 1.0
                usdt = cfg_row["tasa_usdt"] if cfg_row else 1.0
                euro = cfg_row["tasa_bcv_euro"] if cfg_row else 1.0
                upd = cfg_row["tasas_updated_at"] if cfg_row else ""
                
                resp = (
                    f"📊 *Tasas de Cambio Actuales:*\n\n"
                    f"🏦 *BCV USD:* `{bcv:.2f} Bs`\n"
                    f"🟡 *Binance P2P (USDT):* `{usdt:.2f} Bs`\n"
                    f"💶 *BCV Euro:* `{euro:.2f} Bs`\n"
                    f"🕒 *Actualizado:* _{upd or 'Hoy'}_\n"
                )
                self.enviar_mensaje(token, chat_id, resp)
                return

            if cmd in ["/balance", "/resumen"]:
                mes_actual = datetime.now().strftime("%Y-%m")
                ing = db.execute("SELECT COALESCE(SUM(monto_usd), 0) as s FROM finanzas_ingresos WHERE mes = ?", (mes_actual,)).fetchone()['s']
                gas = db.execute("SELECT COALESCE(SUM(monto_usd), 0) as s FROM finanzas_gastos WHERE mes = ?", (mes_actual,)).fetchone()['s']
                neto = ing - gas
                
                emoji_neto = "🟢" if neto >= 0 else "🔴"
                resp = (
                    f"📈 *Resumen Financiero ({mes_actual})*\n\n"
                    f"💰 *Ingresos:* `${ing:,.2f} USD`\n"
                    f"💸 *Gastos:* `${gas:,.2f} USD`\n"
                    f"{emoji_neto} *Balance Neto:* `${neto:,.2f} USD`\n"
                )
                self.enviar_mensaje(token, chat_id, resp)
                return

            if cmd == "/modo":
                partes = texto.split()
                if len(partes) > 1 and partes[1].upper() in ["DIRECTO", "INBOX"]:
                    nuevo_modo = partes[1].upper()
                    db.execute("UPDATE finanzas_telegram_config SET modo_guardado = ? WHERE id = 1", (nuevo_modo,))
                    db.commit()
                    self.enviar_mensaje(token, chat_id, f"✅ Modo de guardado actualizado a: *{nuevo_modo}*")
                else:
                    self.enviar_mensaje(token, chat_id, f"ℹ️ Modo actual: *{modo_guardado}*\nPuedes cambiarlo con `/modo directo` o `/modo inbox`.")
                return

            if cmd in ["/ayuda", "/help"]:
                resp = (
                    f"📖 *Guía Rápida de Mensajes Financieros:*\n\n"
                    f"• *Gastos:* `Almuerzo 15 $` o `Supermercado 1200 bs`\n"
                    f"• *Ingresos:* `Cobro de cliente 350 $` o `Honorarios 5000 bs`\n"
                    f"• *Cambios:* `Cambio 100 usdt a bs tasa 950`\n"
                    f"• *Potes disponibles:* Efectivo ($), Binance (USDT), Bolívares (Bs)\n"
                )
                self.enviar_mensaje(token, chat_id, resp)
                return

        # 2. Control de Acceso: solo el chat_id autorizado puede enviar movimientos
        if chat_id_auth and chat_id != chat_id_auth:
            self.enviar_mensaje(token, chat_id, "⛔ *Acceso no autorizado.* Este bot pertenece a otra cuenta de Finanzas Personales.")
            return

        # Si aún no había chat_id registrado, asociarlo automáticamente
        if not chat_id_auth:
            db.execute("UPDATE finanzas_telegram_config SET chat_id_autorizado = ? WHERE id = 1", (chat_id,))
            db.commit()

        # 3. Obtener tasa referencial activa
        tasa_ref = 1.0
        try:
            cfg_row = db.execute("SELECT tasa_bcv, tasa_usdt FROM app_config WHERE id = 1").fetchone()
            if cfg_row and cfg_row["tasa_bcv"] and float(cfg_row["tasa_bcv"]) > 0:
                tasa_ref = float(cfg_row["tasa_bcv"])
        except Exception:
            pass

        # 4. Parsear mensaje mediante el parser universal
        parsed = parsear_mensaje_whatsapp(texto, remitente=sender_name, tasa_referencial=tasa_ref)

        if not parsed.get("es_valido") or parsed.get("tipo_movimiento") == 'IGNORAR':
            resp = (
                f"🤔 No identifiqué un monto o movimiento en tu mensaje:\n"
                f"_{texto}_\n\n"
                f"💡 *Prueba escribiendo por ejemplo:*\n"
                f"• `Almuerzo 12 $`\n"
                f"• `Gasolina 450 bs`\n"
                f"• `Cobré 200 $`\n"
                f"• `Cambio 50 usdt a bs tasa 950`"
            )
            self.enviar_mensaje(token, chat_id, resp)
            return

        # 5. Registro según el modo de guardado
        fecha_dt = datetime.now()
        fecha_hora_str = fecha_dt.strftime("%Y-%m-%d %H:%M:%S")
        fecha_str = fecha_dt.strftime("%Y-%m-%d")
        mes = fecha_str[:7]
        semana = min(((fecha_dt.day - 1) // 7) + 1, 5)
        tipo = parsed["tipo_movimiento"]

        # Actualizar última actividad
        db.execute("UPDATE finanzas_telegram_config SET ultima_actividad = ? WHERE id = 1", (ahora_str,))
        db.commit()

        if modo_guardado == 'DIRECTO':
            # Guardado directo en las tablas contables
            if tipo == 'GASTO':
                db.execute("""
                    INSERT INTO finanzas_gastos
                    (mes, semana, fecha, descripcion, categoria, moneda, monto_original, tasa, monto_usd, referencia)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Telegram')
                """, (
                    mes,
                    semana,
                    fecha_str,
                    parsed["concepto"],
                    parsed["categoria_fuente"],
                    parsed["moneda"],
                    parsed["monto_original"],
                    parsed["tasa"],
                    parsed["monto_usd"]
                ))
                db.commit()
                
                resp = (
                    f"✅ *Gasto Registrado Exitosamente* 💸\n\n"
                    f"📝 *Concepto:* {parsed['concepto']}\n"
                    f"📂 *Categoría:* {parsed['categoria_fuente']}\n"
                    f"💵 *Monto:* `{parsed['monto_original']:,.2f} {parsed['moneda']}`\n"
                    f"🇺🇸 *Equivalente:* `${parsed['monto_usd']:,.2f} USD`\n"
                    f"📅 *Fecha:* {fecha_str} (Semana {semana})\n"
                )
                self.enviar_mensaje(token, chat_id, resp)
                return

            elif tipo == 'INGRESO':
                db.execute("""
                    INSERT INTO finanzas_ingresos
                    (mes, semana, fecha, concepto, fuente, moneda, monto_original, tasa, monto_usd, referencia)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Telegram')
                """, (
                    mes,
                    semana,
                    fecha_str,
                    parsed["concepto"],
                    parsed["categoria_fuente"],
                    parsed["moneda"],
                    parsed["monto_original"],
                    parsed["tasa"],
                    parsed["monto_usd"]
                ))
                db.commit()
                
                resp = (
                    f"💰 *Ingreso Registrado Exitosamente* 🎉\n\n"
                    f"📝 *Concepto:* {parsed['concepto']}\n"
                    f"📂 *Fuente:* {parsed['categoria_fuente']}\n"
                    f"💵 *Monto:* `{parsed['monto_original']:,.2f} {parsed['moneda']}`\n"
                    f"🇺🇸 *Equivalente:* `${parsed['monto_usd']:,.2f} USD`\n"
                    f"📅 *Fecha:* {fecha_str} (Semana {semana})\n"
                )
                self.enviar_mensaje(token, chat_id, resp)
                return

            elif tipo == 'CAMBIO':
                db.execute("""
                    INSERT INTO finanzas_cambios_internos
                    (mes, fecha, pote_origen, monto_origen, pote_destino, monto_destino, tasa, nota)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    mes,
                    fecha_str,
                    parsed.get("pote_origen", "BINANCE"),
                    parsed.get("monto_origen", 0.0),
                    parsed.get("pote_destino", "BOLIVARES"),
                    parsed.get("monto_destino", 0.0),
                    parsed.get("tasa", 1.0),
                    f"Vía Telegram: {parsed['texto_original']}"
                ))
                db.commit()
                
                resp = (
                    f"🔄 *Cambio entre Potes Registrado* 🔁\n\n"
                    f"📤 *Sale de:* {parsed.get('pote_origen')} (`{parsed.get('monto_origen', 0):,.2f}`)\n"
                    f"📥 *Entra a:* {parsed.get('pote_destino')} (`{parsed.get('monto_destino', 0):,.2f}`)\n"
                    f"📊 *Tasa aplicada:* `{parsed.get('tasa', 1.0):,.2f}`\n"
                    f"📅 *Fecha:* {fecha_str}\n"
                )
                self.enviar_mensaje(token, chat_id, resp)
                return

        else:
            # Guardado en Bandeja de Entrada (Inbox) para aprobación en la Web
            msg_hash = calcular_hash_mensaje(fecha_hora_str, sender_name, texto)
            
            db.execute("""
                INSERT OR IGNORE INTO finanzas_whatsapp_inbox
                (mensaje_hash, fecha_mensaje, fecha, mes, semana,
                 remitente, texto_original, tipo_movimiento,
                 pote, monto_original, tasa, monto_usd, concepto, categoria_fuente,
                 pote_origen, monto_origen, pote_destino, monto_destino,
                 dudoso, estado)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDIENTE')
            """, (
                msg_hash,
                fecha_hora_str,
                fecha_str,
                mes,
                semana,
                f"Telegram ({sender_name})",
                texto,
                tipo,
                parsed["moneda"],
                parsed["monto_original"],
                parsed["tasa"],
                parsed["monto_usd"],
                parsed["concepto"],
                parsed["categoria_fuente"],
                parsed.get("pote_origen", ""),
                parsed.get("monto_origen", 0.0),
                parsed.get("pote_destino", ""),
                parsed.get("monto_destino", 0.0),
                parsed.get("dudoso", 0)
            ))
            db.commit()

            resp = (
                f"📥 *Movimiento enviado a tu Bandeja de Entrada*\n\n"
                f"🏷️ *Tipo:* {tipo}\n"
                f"💵 *Monto:* `{parsed['monto_original']:,.2f} {parsed['moneda']}` (${parsed['monto_usd']:,.2f} USD)\n"
                f"📝 *Concepto:* {parsed['concepto']}\n\n"
                f"👉 Entra a tu web para revisar y migrar con 1 clic."
            )
            self.enviar_mensaje(token, chat_id, resp)

telegram_bot_service = TelegramBotService()
