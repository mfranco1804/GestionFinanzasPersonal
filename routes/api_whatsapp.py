"""
routes/api_whatsapp.py — Blueprint para la automatización e integración
de WhatsApp en Finanzas Personales.

Soporta:
- Método A: Importación directa de chat exportado (.txt).
- Método B: Sincronización en vivo con WhatsApp Web (Playwright).
- Bandeja de Entrada unificada para Gastos, Ingresos y Cambios Internos.
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
from database import get_db
from utils.whatsapp_parser import (
    parsear_chat_exportado_whatsapp, 
    parsear_mensaje_whatsapp, 
    calcular_hash_mensaje
)
from services.whatsapp_browser_service import whatsapp_browser_service

whatsapp_bp = Blueprint('whatsapp_bp', __name__)

@whatsapp_bp.route('/api/cuadre/whatsapp/estado', methods=['GET'])
def get_whatsapp_estado():
    """Consulta el estado del servicio de WhatsApp, configuración y conteo de pendientes."""
    try:
        db = get_db()
        cfg = db.execute("SELECT * FROM finanzas_whatsapp_config WHERE id = 1").fetchone()
        
        # Conteo de pendientes en la bandeja
        pendientes = db.execute("SELECT COUNT(*) as c FROM finanzas_whatsapp_inbox WHERE estado = 'PENDIENTE'").fetchone()
        pendientes_count = pendientes['c'] if pendientes else 0

        vinculado = whatsapp_browser_service.esta_vinculado()
        estado_browser = "CONECTADO" if vinculado else (cfg['estado'] if cfg else "DESCONECTADO")

        return jsonify({
            'success': True,
            'vinculado': vinculado,
            'estado': estado_browser,
            'grupo_nombre': cfg['grupo_nombre'] if cfg else 'Finanzas Personales',
            'enlace_grupo': cfg['enlace_grupo'] if cfg else '',
            'ultima_sincronizacion': cfg['ultima_sincronizacion'] if cfg else '',
            'pendientes_count': pendientes_count
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@whatsapp_bp.route('/api/cuadre/whatsapp/config', methods=['POST'])
def save_whatsapp_config():
    """Guarda nombre del grupo y enlace de invitación."""
    try:
        data = request.get_json() or {}
        grupo_nombre = (data.get('grupo_nombre') or '').strip() or 'Finanzas Personales'
        enlace_grupo = (data.get('enlace_grupo') or '').strip()

        db = get_db()
        db.execute("""
            UPDATE finanzas_whatsapp_config 
            SET grupo_nombre = ?, enlace_grupo = ? 
            WHERE id = 1
        """, (grupo_nombre, enlace_grupo))
        db.commit()

        return jsonify({'success': True, 'mensaje': 'Configuración guardada correctamente'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@whatsapp_bp.route('/api/cuadre/whatsapp/vincular-navegador', methods=['POST'])
@whatsapp_bp.route('/api/cuadre/whatsapp/abrir-qr', methods=['POST'])
def whatsapp_vincular_navegador():
    """Abre la ventana visible de Chromium para vincular WhatsApp Web escaneando el QR una sola vez (igual que en APH)."""
    try:
        from services.whatsapp_browser_service import whatsapp_browser_service
        res = whatsapp_browser_service.abrir_ventana_vinculacion_qr()
        return jsonify(res)
    except Exception as e:
        return jsonify({'success': False, 'mensaje': f"Error al iniciar vinculación: {str(e)}", 'error': str(e)}), 500


@whatsapp_bp.route('/api/cuadre/whatsapp/desvincular', methods=['POST'])
def desvincular_whatsapp_api():
    """Desvincula la sesión actual de WhatsApp Web."""
    try:
        res = whatsapp_browser_service.desvincular()
        return jsonify(res)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@whatsapp_bp.route('/api/cuadre/whatsapp/sincronizar-live', methods=['POST'])
def sincronizar_live():
    """Ejecuta la extracción automática de mensajes del grupo mediante Playwright (Método B)."""
    try:
        db = get_db()
        cfg = db.execute("SELECT grupo_nombre, enlace_grupo FROM finanzas_whatsapp_config WHERE id = 1").fetchone()
        nombre = cfg['grupo_nombre'] if cfg else 'Finanzas Personales'
        enlace = cfg['enlace_grupo'] if cfg else ''

        res = whatsapp_browser_service.extraer_mensajes_grupo(nombre, enlace)
        return jsonify(res)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@whatsapp_bp.route('/api/cuadre/whatsapp/importar-archivo', methods=['POST'])
def importar_archivo_chat():
    """
    Método A: Recibe el archivo de texto (.txt) exportado de WhatsApp,
    lo analiza con el parser universal de 3 vías y almacena los movimientos en el inbox.
    """
    try:
        if 'archivo' not in request.files:
            return jsonify({'success': False, 'error': 'No se adjuntó ningún archivo .txt'}), 400

        file = request.files['archivo']
        if not file.filename:
            return jsonify({'success': False, 'error': 'Archivo no válido'}), 400

        contenido_bytes = file.read()
        try:
            contenido_txt = contenido_bytes.decode('utf-8')
        except UnicodeDecodeError:
            contenido_txt = contenido_bytes.decode('latin-1', errors='ignore')

        db = get_db()
        # Obtener tasa referencial actual
        tasa_ref = 1.0
        cfg = db.execute("SELECT tasa_bcv FROM app_config WHERE id = 1").fetchone()
        if cfg and cfg['tasa_bcv']:
            tasa_ref = float(cfg['tasa_bcv'])

        movimientos = parsear_chat_exportado_whatsapp(contenido_txt, tasa_referencial=tasa_ref)

        insertados = 0
        duplicados = 0
        conteo_tipos = {'GASTO': 0, 'INGRESO': 0, 'CAMBIO': 0}

        for m in movimientos:
            existe = db.execute("SELECT id FROM finanzas_whatsapp_inbox WHERE mensaje_hash = ?", (m['hash'],)).fetchone()
            if existe:
                duplicados += 1
                continue

            tipo = m.get('tipo_movimiento', 'GASTO')
            conteo_tipos[tipo] = conteo_tipos.get(tipo, 0) + 1

            db.execute("""
                INSERT INTO finanzas_whatsapp_inbox
                (mensaje_hash, fecha_mensaje, fecha, mes, semana,
                 remitente, texto_original, tipo_movimiento,
                 pote, monto_original, tasa, monto_usd, concepto, categoria_fuente,
                 pote_origen, monto_origen, pote_destino, monto_destino,
                 dudoso, estado)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDIENTE')
            """, (
                m['hash'],
                m.get('fecha_mensaje', ''),
                m.get('fecha', ''),
                m.get('mes', ''),
                m.get('semana', 1),
                m.get('remitente', 'Yo'),
                m.get('texto_original', ''),
                tipo,
                m.get('moneda', 'EFECTIVO'),
                m.get('monto_original', 0.0),
                m.get('tasa', tasa_ref),
                m.get('monto_usd', 0.0),
                m.get('concepto', ''),
                m.get('categoria_fuente', ''),
                m.get('pote_origen', ''),
                m.get('monto_origen', 0.0),
                m.get('pote_destino', ''),
                m.get('monto_destino', 0.0),
                m.get('dudoso', 0)
            ))
            insertados += 1

        db.commit()

        return jsonify({
            'success': True,
            'total_detectados': len(movimientos),
            'insertados': insertados,
            'duplicados': duplicados,
            'conteo_tipos': conteo_tipos,
            'mensaje': f"Procesado con éxito: {insertados} nuevos movimientos agregados ({duplicados} ya existían)."
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@whatsapp_bp.route('/api/cuadre/whatsapp/inbox/<mes>', methods=['GET'])
def get_inbox_items(mes):
    """Retorna los movimientos de WhatsApp en la bandeja de entrada para revisión."""
    try:
        db = get_db()
        if mes == 'TODOS':
            rows = db.execute("SELECT * FROM finanzas_whatsapp_inbox WHERE estado = 'PENDIENTE' ORDER BY fecha_mensaje DESC").fetchall()
        else:
            rows = db.execute("SELECT * FROM finanzas_whatsapp_inbox WHERE estado = 'PENDIENTE' AND mes = ? ORDER BY fecha_mensaje DESC", (mes,)).fetchall()

        items = [dict(r) for r in rows]
        return jsonify({'success': True, 'items': items})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@whatsapp_bp.route('/api/cuadre/whatsapp/inbox/<int:item_id>', methods=['PUT'])
def update_inbox_item(item_id):
    """Permite ajustar detalles de un movimiento detectado antes de migrarlo."""
    try:
        data = request.get_json() or {}
        db = get_db()

        tipo = data.get('tipo_movimiento')
        monto_orig = float(data.get('monto_original', 0))
        tasa = float(data.get('tasa', 1.0))
        moneda = data.get('pote') or data.get('moneda', 'EFECTIVO')

        if moneda in ('BOLIVARES', 'BS'):
            if tasa <= 1.0:
                cfg = db.execute("SELECT tasa_bcv FROM app_config WHERE id = 1").fetchone()
                if cfg and cfg['tasa_bcv'] and float(cfg['tasa_bcv']) > 1.0:
                    tasa = float(cfg['tasa_bcv'])
            monto_usd = round(monto_orig / tasa, 2) if tasa > 0 else 0.0
        elif moneda in ('EFECTIVO', 'BINANCE'):
            monto_usd = monto_orig
            tasa = 1.0
        else:
            monto_usd = 0.0

        dudoso = 1 if moneda == 'SIN_DEFINIR' else 0

        db.execute("""
            UPDATE finanzas_whatsapp_inbox
            SET tipo_movimiento = ?,
                pote = ?,
                monto_original = ?,
                tasa = ?,
                monto_usd = ?,
                concepto = ?,
                categoria_fuente = ?,
                pote_origen = ?,
                monto_origen = ?,
                pote_destino = ?,
                monto_destino = ?,
                dudoso = ?
            WHERE id = ?
        """, (
            tipo,
            moneda,
            monto_orig,
            tasa,
            monto_usd,
            data.get('concepto', ''),
            data.get('categoria_fuente', ''),
            data.get('pote_origen', ''),
            float(data.get('monto_origen', 0)),
            data.get('pote_destino', ''),
            float(data.get('monto_destino', 0)),
            dudoso,
            item_id
        ))
        db.commit()

        return jsonify({'success': True, 'mensaje': 'Movimiento actualizado', 'tasa': tasa, 'monto_usd': monto_usd})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@whatsapp_bp.route('/api/cuadre/whatsapp/migrar', methods=['POST'])
def migrar_inbox():
    """
    Migra los movimientos seleccionados (o todos los pendientes) desde el inbox
    hacia las tablas contables oficiales: finanzas_gastos, finanzas_ingresos y finanzas_cambios_internos.
    Bloquea la migración si hay movimientos sin pote definido.
    """
    try:
        data = request.get_json() or {}
        ids = data.get('ids', [])

        db = get_db()
        if ids:
            placeholders = ','.join(['?'] * len(ids))
            rows = db.execute(f"SELECT * FROM finanzas_whatsapp_inbox WHERE id IN ({placeholders}) AND estado = 'PENDIENTE'", ids).fetchall()
        else:
            rows = db.execute("SELECT * FROM finanzas_whatsapp_inbox WHERE estado = 'PENDIENTE'").fetchall()

        # Validación estricta: No migrar si hay movimientos sin pote o sin definir
        sin_pote = [r for r in rows if r['tipo_movimiento'] in ('GASTO', 'INGRESO') and (not r['pote'] or r['pote'] == 'SIN_DEFINIR')]
        if sin_pote:
            primer = sin_pote[0]
            return jsonify({
                'success': False,
                'requiere_validacion': True,
                'item_invalido': dict(primer),
                'error': f"El movimiento '{primer['texto_original']}' ({primer['concepto'] or 'Sin concepto'}) no tiene moneda/pote especificado. Por favor define si fue en Efectivo ($), Binance (USDT) o Bolívares (Bs) antes de migrar."
            }), 400

        # Obtener tasa BCV actual para fallback
        cfg = db.execute("SELECT tasa_bcv FROM app_config WHERE id = 1").fetchone()
        tasa_bcv_actual = float(cfg['tasa_bcv']) if cfg and cfg['tasa_bcv'] else 1.0

        migrados = 0
        for r in rows:
            tipo = r['tipo_movimiento']
            reg_id = None
            pote_norm = 'BS' if r['pote'] in ('BOLIVARES', 'BS') else ('BINANCE' if r['pote'] in ('BINANCE', 'USDT') else 'EFECTIVO')

            tasa_val = float(r['tasa'] or 1.0)
            if pote_norm == 'BS' and tasa_val <= 1.0:
                tasa_val = tasa_bcv_actual

            monto_usd_calc = round(float(r['monto_original']) / tasa_val, 2) if (pote_norm == 'BS' and tasa_val > 0) else float(r['monto_original'])

            if tipo == 'GASTO':
                cur = db.cursor()
                cur.execute("""
                    INSERT INTO finanzas_gastos
                    (mes, semana, fecha, descripcion, categoria, moneda, monto_original, tasa, monto_usd, referencia)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    r['mes'],
                    r['semana'],
                    r['fecha'],
                    r['concepto'],
                    r['categoria_fuente'] or 'Otros Gastos',
                    pote_norm,
                    r['monto_original'],
                    tasa_val,
                    monto_usd_calc,
                    f"WhatsApp ({r['remitente']})"
                ))
                reg_id = cur.lastrowid

            elif tipo == 'INGRESO':
                cur = db.cursor()
                cur.execute("""
                    INSERT INTO finanzas_ingresos
                    (mes, semana, fecha, concepto, fuente, moneda, monto_original, tasa, monto_usd, referencia, nota)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    r['mes'],
                    r['semana'],
                    r['fecha'],
                    r['concepto'],
                    r['categoria_fuente'] or 'Entrada Extraordinaria',
                    pote_norm,
                    r['monto_original'],
                    tasa_val,
                    monto_usd_calc,
                    f"WhatsApp ({r['remitente']})",
                    r['texto_original']
                ))
                reg_id = cur.lastrowid

            elif tipo == 'CAMBIO':
                cur = db.cursor()
                p_orig = 'BS' if r['pote_origen'] in ('BOLIVARES', 'BS') else ('BINANCE' if r['pote_origen'] in ('BINANCE', 'USDT') else 'EFECTIVO')
                p_dest = 'BS' if r['pote_destino'] in ('BOLIVARES', 'BS') else ('BINANCE' if r['pote_destino'] in ('BINANCE', 'USDT') else 'EFECTIVO')
                cur.execute("""
                    INSERT INTO finanzas_cambios_internos
                    (mes, fecha, pote_origen, monto_origen, pote_destino, monto_destino, tasa, nota)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    r['mes'],
                    r['fecha'],
                    p_orig,
                    r['monto_origen'],
                    p_dest,
                    r['monto_destino'],
                    r['tasa'],
                    f"WhatsApp: {r['texto_original']}"
                ))
                reg_id = cur.lastrowid

            db.execute("UPDATE finanzas_whatsapp_inbox SET estado = 'MIGRADO', registro_id = ? WHERE id = ?", (reg_id, r['id']))
            migrados += 1

        db.commit()

        return jsonify({
            'success': True,
            'migrados': migrados,
            'mensaje': f"Se migraron exitosamente {migrados} movimientos al cuadre mensual."
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@whatsapp_bp.route('/api/cuadre/whatsapp/descartar', methods=['POST'])
def descartar_inbox():
    """Descarta uno o varios movimientos del inbox."""
    try:
        data = request.get_json() or {}
        ids = data.get('ids', [])

        db = get_db()
        if ids:
            placeholders = ','.join(['?'] * len(ids))
            db.execute(f"UPDATE finanzas_whatsapp_inbox SET estado = 'DESCARTADO' WHERE id IN ({placeholders})", ids)
        else:
            db.execute("UPDATE finanzas_whatsapp_inbox SET estado = 'DESCARTADO' WHERE estado = 'PENDIENTE'")
        db.commit()

        return jsonify({'success': True, 'mensaje': 'Movimientos descartados'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
