"""
services/whatsapp_browser_service.py — Servicio de sincronización de WhatsApp Web
con Playwright para Finanzas Personales.

Permite:
1. Abrir ventana interactiva para vincular WhatsApp Web una sola vez mediante QR.
2. Extraer en segundo plano (headless) los mensajes nuevos del grupo de WhatsApp.
3. Procesar y clasificar mensajes automáticamente en GASTOS, INGRESOS y CAMBIOS.
"""
import os
import re
import time
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from database import get_db, DB_PATH, BASE_DIR
from utils.whatsapp_parser import parsear_mensaje_whatsapp, calcular_hash_mensaje

logger = logging.getLogger("WhatsAppBrowserService")
logger.setLevel(logging.INFO)

PROFILE_DIR = os.path.join(BASE_DIR, "whatsapp_browser_profile")
LOG_PATH = os.path.join(BASE_DIR, "whatsapp_service.log")

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

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

class WhatsAppBrowserService:
    def __init__(self):
        self.profile_dir = PROFILE_DIR
        self.flag_file = os.path.join(self.profile_dir, "session_ready.flag")
        os.makedirs(self.profile_dir, exist_ok=True)

    def limpiar_bloqueos_perfil(self):
        """Elimina posibles procesos residuales y bloqueos de Chromium en el directorio de perfil."""
        try:
            import subprocess
            cmd = 'powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \\"Name like \'%chrome%\'\\" | Where-Object { $_.ExecutablePath -like \'*ms-playwright*\' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"'
            subprocess.run(cmd, shell=True, capture_output=True, timeout=5)
        except Exception:
            pass

        time.sleep(0.5)

        for lock_name in ["SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"]:
            lock_path = os.path.join(self.profile_dir, lock_name)
            if os.path.exists(lock_path):
                try:
                    os.remove(lock_path)
                except Exception:
                    pass

    def esta_vinculado(self) -> bool:
        """Comprueba si existe sesión guardada y confirmada en la carpeta de perfil de Chromium."""
        return os.path.exists(self.flag_file)

    def desvincular(self) -> dict:
        """Elimina la vinculación actual para permitir vincular un nuevo teléfono o número."""
        try:
            if os.path.exists(self.flag_file):
                try:
                    os.remove(self.flag_file)
                except Exception:
                    pass
            self.limpiar_bloqueos_perfil()
            import shutil
            idb_path = os.path.join(self.profile_dir, "Default", "IndexedDB")
            if os.path.exists(idb_path):
                try:
                    shutil.rmtree(idb_path, ignore_errors=True)
                except Exception:
                    pass
            db = get_service_db()
            db.execute("UPDATE finanzas_whatsapp_config SET estado = 'DESCONECTADO' WHERE id = 1")
            db.commit()
            return {"success": True, "mensaje": "WhatsApp Web desvinculado correctamente."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def abrir_ventana_vinculacion_qr(self) -> dict:
        """
        Abre Chromium en modo visible (headless=False) para que el usuario
        escanee el código QR de WhatsApp Web una sola vez.
        Se cierra automáticamente en cuanto detecta el inicio de sesión.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return {
                "success": False,
                "mensaje": "Playwright no está instalado en este servidor. Por favor ejecuta 'pip install playwright'."
            }

        try:
            import ctypes
            user32 = ctypes.windll.user32
            hDesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
            if hDesk:
                user32.SetThreadDesktop(hDesk)
        except Exception:
            pass

        self.limpiar_bloqueos_perfil()
        logger.info("Abriendo ventana visible para vinculación QR de WhatsApp Web...")
        try:
            with sync_playwright() as p:
                try:
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=self.profile_dir,
                        headless=False,
                        user_agent=USER_AGENT,
                        args=[
                            "--no-sandbox",
                            "--disable-setuid-sandbox",
                            "--disable-dev-shm-usage",
                            "--disable-blink-features=AutomationControlled",
                            "--window-position=120,60",
                            "--window-size=1080,820"
                        ],
                        viewport={"width": 1024, "height": 768}
                    )
                except Exception as e_launch:
                    logger.error(f"Error al abrir Chromium: {e_launch}")
                    return {
                        "success": False,
                        "mensaje": f"No se pudo iniciar Chromium. Detalle: {str(e_launch)}"
                    }

                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    try:
                        page.bring_to_front()
                    except Exception:
                        pass
                    page.goto("https://web.whatsapp.com", wait_until="domcontentloaded")
                    time.sleep(1)
                    try:
                        page.bring_to_front()
                    except Exception:
                        pass

                    # Esperar a que el usuario escanee el QR (máximo 120 segundos)
                    try:
                        page.wait_for_selector("#pane-side, [data-testid='chat-list'], header[data-testid='chatlist-header']", timeout=120000)
                        time.sleep(5)
                        try:
                            with open(self.flag_file, "w") as f:
                                f.write("OK")
                        except Exception:
                            pass
                        
                        db = get_service_db()
                        db.execute("UPDATE finanzas_whatsapp_config SET estado = 'CONECTADO' WHERE id = 1")
                        db.commit()

                        logger.info("✅ Sesión de WhatsApp Web vinculada exitosamente.")
                        return {"success": True, "mensaje": "¡WhatsApp Web vinculado exitosamente!"}
                    except Exception as e:
                        logger.warning(f"Tiempo agotado esperando escaneo de QR: {e}")
                        return {"success": False, "mensaje": "Tiempo agotado para escanear el código QR. Inténtalo de nuevo."}
                finally:
                    try:
                        context.close()
                    except Exception:
                        pass
        except Exception as e_all:
            logger.error(f"Error inesperado en vinculación QR: {e_all}")
            return {
                "success": False,
                "mensaje": f"Error inesperado en Playwright: {str(e_all)}"
            }

    def _verificar_chat_activo(self, page, nombre_grupo: str) -> bool:
        """Verifica con certeza que el panel principal #main tiene abierto el chat indicado."""
        try:
            main_header = page.locator("#main header").first
            if main_header.is_visible(timeout=1500):
                header_text = main_header.inner_text().strip().lower()
                clean_target = nombre_grupo.strip().lower()
                # Coincidencia si el nombre está contenido o viceversa
                if clean_target in header_text or any(part in header_text for part in clean_target.split() if len(part) > 3):
                    logger.info(f"Confirmado: Chat '{nombre_grupo}' está activo en #main header ('{header_text[:40]}...').")
                    return True
        except Exception:
            pass
        return False

    def _localizar_y_abrir_chat(self, page, nombre_grupo: str, enlace_grupo: str = "") -> bool:
        """
        Localiza y abre ESTRICTAMENTE el chat o grupo especificado en WhatsApp Web.
        Asegura que #main esté abierto con el chat correcto antes de retornar True.
        """
        nombre_clean = nombre_grupo.strip()

        # 1. ¿Ya está abierto el chat correcto en #main?
        if self._verificar_chat_activo(page, nombre_clean):
            return True

        # 2. Buscar en la lista de chats visibles en #pane-side
        match_selectors = [
            f"#pane-side span[title='{nombre_clean}']",
            f"#pane-side span[title*='{nombre_clean}' i]",
            f"#pane-side div[role='listitem'] span[title*='{nombre_clean}' i]"
        ]

        for sel in match_selectors:
            try:
                elem = page.locator(sel).first
                if elem.is_visible(timeout=1500):
                    logger.info(f"Haciendo clic en chat visible '{nombre_clean}' en el listado.")
                    elem.click()
                    time.sleep(2)
                    if self._verificar_chat_activo(page, nombre_clean):
                        return True
            except Exception:
                pass

        # 3. Scroll suave en #pane-side para buscarlo en chats recientes
        try:
            pane = page.locator("#pane-side").first
            if pane.is_visible(timeout=2000):
                for _ in range(5):
                    for sel in match_selectors:
                        elem = page.locator(sel).first
                        if elem.is_visible(timeout=500):
                            logger.info(f"Chat '{nombre_clean}' encontrado tras scroll.")
                            elem.click()
                            time.sleep(2)
                            if self._verificar_chat_activo(page, nombre_clean):
                                return True
                    pane.evaluate("el => el.scrollBy(0, 350)")
                    time.sleep(0.4)
                pane.evaluate("el => el.scrollTo(0, 0)")
                time.sleep(0.3)
        except Exception:
            pass

        # 4. Usar la barra de búsqueda de WhatsApp Web (SOLO haciendo clic en resultados que coincidan)
        search_box_selectors = [
            "div[data-testid='chat-list-search'] [contenteditable='true']",
            "#side [contenteditable='true'][role='textbox']",
            "#side div[contenteditable='true']",
            "div[aria-label*='Buscar' i][contenteditable='true']",
            "div[aria-label*='Search' i][contenteditable='true']",
            "div[data-testid='chat-list-search']",
            "button[data-testid='chat-list-search']",
            "#side [role='textbox']"
        ]

        search_input = None
        for s_sel in search_box_selectors:
            try:
                s_elem = page.locator(s_sel).first
                if s_elem.is_visible(timeout=1000):
                    search_input = s_elem
                    break
            except Exception:
                continue

        if search_input:
            try:
                logger.info(f"Buscando '{nombre_clean}' mediante el buscador de WhatsApp...")
                search_input.click()
                time.sleep(0.3)
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                time.sleep(0.2)
                page.keyboard.type(nombre_clean, delay=40)
                time.sleep(2)

                # SOLO hacer clic en elementos que tengan el título del grupo buscado
                strict_result_selectors = [
                    f"div[data-testid='search-results'] span[title*='{nombre_clean}' i]",
                    f"#side span[title*='{nombre_clean}' i]",
                    f"#pane-side span[title*='{nombre_clean}' i]"
                ]
                for r_sel in strict_result_selectors:
                    try:
                        res_elem = page.locator(r_sel).first
                        if res_elem.is_visible(timeout=2000):
                            logger.info(f"Haciendo clic en resultado de búsqueda específico para '{nombre_clean}'.")
                            res_elem.click()
                            time.sleep(2)
                            if self._verificar_chat_activo(page, nombre_clean):
                                return True
                    except Exception:
                        continue

                # Intentar Enter si el primer resultado es el foco
                page.keyboard.press("Enter")
                time.sleep(2)
                if self._verificar_chat_activo(page, nombre_clean):
                    return True
            except Exception as e_search:
                logger.warning(f"Error en búsqueda: {e_search}")

        # 5. Enlace de invitación (Fallback)
        if enlace_grupo:
            m_code = re.search(r'chat\.whatsapp\.com/([a-zA-Z0-9_-]+)', enlace_grupo)
            if m_code:
                invite_code = m_code.group(1)
                try:
                    logger.info(f"Intentando abrir grupo mediante enlace de invitación ({invite_code})...")
                    page.goto(f"https://web.whatsapp.com/accept?code={invite_code}", wait_until="domcontentloaded")
                    time.sleep(2.5)
                    for btn_text in ['Unirme', 'Unirse', 'Continuar', 'Join']:
                        try:
                            btn = page.locator(f"button:has-text('{btn_text}'), div[role='button']:has-text('{btn_text}')").first
                            if btn.is_visible(timeout=1500):
                                btn.click()
                                time.sleep(2.5)
                                break
                        except Exception:
                            pass
                    if self._verificar_chat_activo(page, nombre_clean):
                        return True
                except Exception as e_link:
                    logger.warning(f"Error al navegar por enlace de invitación: {e_link}")

        # Retornar si finalmente quedó abierto y confirmado
        return self._verificar_chat_activo(page, nombre_clean)

    def extraer_mensajes_grupo(self, nombre_grupo: str = "", enlace_grupo: str = "", max_scrolls: int = 6) -> dict:
        """
        Abre Chromium en segundo plano (headless=True), entra ESTRICTAMENTE al grupo financiero,
        hace scroll hacia arriba dentro del panel de conversación activo (#main), y extrae los 
        mensajes legítimos hacia finanzas_whatsapp_inbox.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return {"success": False, "mensaje": "Playwright no está instalado en el servidor."}

        db = get_service_db()
        if not nombre_grupo or not enlace_grupo:
            try:
                row = db.execute("SELECT grupo_nombre, enlace_grupo FROM finanzas_whatsapp_config WHERE id = 1").fetchone()
                if row:
                    if not nombre_grupo and row["grupo_nombre"]:
                        nombre_grupo = row["grupo_nombre"].strip()
                    if not enlace_grupo and row["enlace_grupo"]:
                        enlace_grupo = row["enlace_grupo"].strip()
            except Exception:
                pass

        if not nombre_grupo:
            nombre_grupo = "Finanzas Personales"

        if not self.esta_vinculado():
            return {
                "success": False,
                "requiere_qr": True,
                "mensaje": "Aún no has vinculado tu WhatsApp. Haz clic en 'Vincular WhatsApp' para escanear el código QR."
            }

        logger.info(f"Iniciando extracción de mensajes del grupo '{nombre_grupo}'...")

        insertados = 0
        duplicados = 0
        total_encontrados = 0
        items_detectados = []

        self.limpiar_bloqueos_perfil()

        with sync_playwright() as p:
            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=self.profile_dir,
                    headless=True,
                    user_agent=USER_AGENT,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled"
                    ],
                    viewport={"width": 1280, "height": 900}
                )
            except Exception as e_launch:
                logger.error(f"Error al iniciar Chromium para extracción: {e_launch}")
                return {
                    "success": False,
                    "mensaje": f"No se pudo iniciar el navegador en segundo plano: {str(e_launch)}"
                }

            page = context.pages[0] if context.pages else context.new_page()

            try:
                page.goto("https://web.whatsapp.com", wait_until="domcontentloaded")

                try:
                    page.wait_for_selector("#pane-side, [data-testid='chat-list'], header[data-testid='chatlist-header']", timeout=45000)
                    logger.info("Sesión de WhatsApp Web cargada con éxito.")
                except Exception:
                    qr_count = page.locator("[data-testid='qrcode'], canvas[aria-label*='Scan'], canvas[aria-label*='escanea']").count()
                    if qr_count > 0:
                        if os.path.exists(self.flag_file):
                            try: os.remove(self.flag_file)
                            except Exception: pass
                        return {
                            "success": False,
                            "requiere_qr": True,
                            "mensaje": "La sesión de WhatsApp caducó o requiere escanear el código QR nuevamente."
                        }
                    return {
                        "success": False,
                        "requiere_qr": False,
                        "mensaje": "Tiempo de espera agotado al conectar con WhatsApp Web. Intenta nuevamente."
                    }

                time.sleep(2)

                # 1. Localizar y abrir el chat del grupo
                abierto = self._localizar_y_abrir_chat(page, nombre_grupo, enlace_grupo)
                if not abierto:
                    logger.warning(f"No se pudo abrir y verificar el chat '{nombre_grupo}'.")
                    return {
                        "success": False,
                        "mensaje": f"No se pudo abrir el grupo '{nombre_grupo}' en WhatsApp. Verifica que el nombre configurado coincida exactamente con el nombre de tu grupo en WhatsApp o coloca el enlace de invitación."
                    }

                time.sleep(2)

                # 2. Scroll hacia arriba DENTRO DE #main para cargar mensajes previos
                try:
                    panel = page.locator("#main div[data-testid='conversation-panel-messages'], #main div.copyable-area div[tabindex='-1'], #main").first
                    if panel.is_visible(timeout=3000):
                        for _ in range(max_scrolls):
                            panel.evaluate("el => el.scrollBy(0, -600)")
                            time.sleep(0.5)
                except Exception as e_sc:
                    logger.warning(f"Aviso al hacer scroll en el panel de mensajes: {e_sc}")

                # 3. Extraer elementos de mensaje EXCLUSIVAMENTE dentro de #main (NUNCA del listado lateral)
                mensajes_elems = page.locator("#main div.message-in, #main div.message-out, #main div[data-testid='msg-container']").all()

                if not mensajes_elems:
                    logger.info("No se encontraron burbujas de mensaje dentro de la conversación actual.")
                    return {
                        "success": True,
                        "total_detectados": 0,
                        "insertados": 0,
                        "duplicados": 0,
                        "mensaje": "No se encontraron mensajes en el chat para procesar."
                    }

                # Tasa referencial actual
                tasa_ref = 1.0
                try:
                    cfg_row = db.execute("SELECT tasa_bcv, tasa_usdt FROM app_config WHERE id = 1").fetchone()
                    if cfg_row and cfg_row["tasa_bcv"] and float(cfg_row["tasa_bcv"]) > 0:
                        tasa_ref = float(cfg_row["tasa_bcv"])
                except Exception:
                    pass

                for elem in mensajes_elems:
                    try:
                        # Extraer pre_text (remitente y fecha oficial de WhatsApp)
                        pre_text = elem.get_attribute("data-pre-plain-text") or ""
                        if not pre_text:
                            child_c = elem.locator("div.copyable-text").first
                            if child_c.count() > 0:
                                pre_text = child_c.get_attribute("data-pre-plain-text") or ""

                        # Extraer texto del mensaje
                        text_sub = elem.locator("span.selectable-text, div.copyable-text").first
                        if text_sub.count() > 0:
                            texto = text_sub.inner_text().strip()
                        else:
                            texto = elem.inner_text().strip()

                        if not texto:
                            continue

                        remitente = "Yo"
                        fecha_dt = datetime.now()

                        if pre_text:
                            m_rem = re.search(r'\]\s*([^:]+):', pre_text)
                            if m_rem:
                                remitente = m_rem.group(1).strip()
                            m_fecha = re.search(r'\[?(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', pre_text)
                            if m_fecha:
                                d, m, y = int(m_fecha.group(1)), int(m_fecha.group(2)), int(m_fecha.group(3))
                                if y < 100: y += 2000
                                try:
                                    fecha_dt = datetime(y, m, d)
                                except Exception:
                                    pass

                        # Pasar por el parser de 3 vías
                        parsed = parsear_mensaje_whatsapp(texto, remitente, tasa_referencial=tasa_ref)
                        if not parsed.get("es_valido") or parsed.get("tipo_movimiento") == 'IGNORAR':
                            continue

                        total_encontrados += 1
                        fecha_hora_str = fecha_dt.strftime("%Y-%m-%d %H:%M:%S")
                        fecha_str = fecha_dt.strftime("%Y-%m-%d")
                        mes = fecha_str[:7]
                        semana = min(((fecha_dt.day - 1) // 7) + 1, 5)

                        msg_hash = calcular_hash_mensaje(fecha_hora_str, parsed["remitente"], texto)

                        existe = db.execute("SELECT id FROM finanzas_whatsapp_inbox WHERE mensaje_hash = ?", (msg_hash,)).fetchone()
                        if existe:
                            duplicados += 1
                            continue

                        cursor = db.cursor()
                        cursor.execute("""
                            INSERT INTO finanzas_whatsapp_inbox
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
                            parsed["remitente"],
                            parsed["texto_original"],
                            parsed["tipo_movimiento"],
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
                        insertados += 1
                        parsed["id"] = cursor.lastrowid
                        items_detectados.append(parsed)
                    except Exception as err_item:
                        logger.error(f"Error procesando burbuja de mensaje: {err_item}")

                # Actualizar última sincronización
                ahora_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                db.execute("UPDATE finanzas_whatsapp_config SET ultima_sincronizacion = ?, estado = 'CONECTADO' WHERE id = 1", (ahora_str,))
                db.commit()

                logger.info(f"Extracción finalizada: {total_encontrados} detectados, {insertados} nuevos, {duplicados} duplicados.")
                return {
                    "success": True,
                    "total_detectados": total_encontrados,
                    "insertados": insertados,
                    "duplicados": duplicados,
                    "mensaje": f"Sincronización completa: {insertados} movimientos nuevos importados ({duplicados} ya existían)."
                }

            except Exception as e:
                logger.error(f"Error durante la extracción con Playwright: {e}", exc_info=True)
                return {
                    "success": False,
                    "error": str(e),
                    "mensaje": f"Ocurrió un error al leer el grupo de WhatsApp: {e}"
                }
            finally:
                try:
                    context.close()
                except Exception:
                    pass

whatsapp_browser_service = WhatsAppBrowserService()
