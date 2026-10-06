"""
routes/api_proyeccion.py — Módulo de Proyección Financiera (Gastos Fijos vs Entradas Fijas).
Proporciona un simulador y pronóstico financiero recurrente totalmente desacoplado
del cuadre transaccional mensual.
"""
from datetime import datetime
from flask import Blueprint, request, jsonify
from database import get_db

proyeccion_bp = Blueprint('proyeccion_bp', __name__)

# Factores de conversión matemática estricta a periodicidad MENSUAL
# Basados en estándares financieros de FP&A (365 días / 12 meses y 52 semanas / 12 meses)
FACTORES_MENSUAL = {
    'DIARIO': 365.0 / 12.0,      # 30.4167 días por mes
    'SEMANAL': 52.0 / 12.0,     # 4.3333 semanas por mes
    'QUINCENAL': 2.0,           # 2 quincenas por mes exactas
    'MENSUAL': 1.0,             # 1 vez al mes
    'BIMESTRAL': 1.0 / 2.0,     # Cada 2 meses
    'TRIMESTRAL': 1.0 / 3.0,    # Cada 3 meses
    'SEMESTRAL': 1.0 / 6.0,     # Cada 6 meses
    'ANUAL': 1.0 / 12.0         # 1 vez al año
}

def normalizar_monto_proyeccion(monto_orig: float, frecuencia: str, moneda: str, tasa: float, tasa_bcv: float = 1.0):
    """
    Convierte cualquier monto en cualquier moneda y frecuencia
    a su valor exacto mensual y anual en USD.
    """
    monto_orig = float(monto_orig or 0.0)
    frec = (frecuencia or 'MENSUAL').upper()
    factor = FACTORES_MENSUAL.get(frec, 1.0)
    moneda_norm = (moneda or 'USD').upper()
    tasa_val = float(tasa or 1.0)

    if moneda_norm in ('BS', 'BOLIVARES'):
        if tasa_val <= 1.0 and tasa_bcv > 1.0:
            tasa_val = tasa_bcv
        monto_usd_base = (monto_orig / tasa_val) if tasa_val > 0 else 0.0
    else:
        monto_usd_base = monto_orig
        tasa_val = 1.0

    monto_mensual_usd = round(monto_usd_base * factor, 2)
    monto_anual_usd = round(monto_mensual_usd * 12.0, 2)

    return {
        'monto_original': round(monto_orig, 2),
        'frecuencia': frec,
        'moneda': moneda_norm,
        'tasa': round(tasa_val, 4),
        'monto_mensual_usd': monto_mensual_usd,
        'monto_anual_usd': monto_anual_usd
    }

def obtener_tasa_bcv_activa(db):
    """Obtiene la tasa BCV configurada actualmente en el sistema."""
    cfg = db.execute("SELECT tasa_bcv FROM app_config WHERE id = 1").fetchone()
    if cfg and cfg['tasa_bcv'] and float(cfg['tasa_bcv']) > 1.0:
        return float(cfg['tasa_bcv'])
    return 1.0

@proyeccion_bp.route('/api/proyeccion/resumen', methods=['GET'])
def get_resumen_proyeccion():
    """
    Calcula y devuelve todos los KPIs, totales mensuales/anuales,
    distribuciones por categoría y ratios de salud financiera.
    """
    try:
        db = get_db()
        tasa_bcv = obtener_tasa_bcv_activa(db)
        rows = db.execute("SELECT * FROM finanzas_proyeccion_items ORDER BY tipo DESC, categoria ASC, monto_mensual_usd DESC").fetchall()

        entradas = []
        gastos = []

        tot_ent_men = 0.0
        tot_ent_anu = 0.0
        tot_gas_men = 0.0
        tot_gas_anu = 0.0

        cat_gastos = {}
        cat_entradas = {}

        for r in rows:
            item = dict(r)
            es_activo = bool(item['activo'])
            
            if item['tipo'] == 'ENTRADA':
                entradas.append(item)
                if es_activo:
                    tot_ent_men += item['monto_mensual_usd']
                    tot_ent_anu += item['monto_anual_usd']
                    c = item['categoria'] or 'Otras Entradas'
                    cat_entradas[c] = round(cat_entradas.get(c, 0.0) + item['monto_mensual_usd'], 2)
            else:
                gastos.append(item)
                if es_activo:
                    tot_gas_men += item['monto_mensual_usd']
                    tot_gas_anu += item['monto_anual_usd']
                    c = item['categoria'] or 'Otros Gastos'
                    cat_gastos[c] = round(cat_gastos.get(c, 0.0) + item['monto_mensual_usd'], 2)

        tot_ent_men = round(tot_ent_men, 2)
        tot_ent_anu = round(tot_ent_anu, 2)
        tot_gas_men = round(tot_gas_men, 2)
        tot_gas_anu = round(tot_gas_anu, 2)

        margen_libre_men = round(tot_ent_men - tot_gas_men, 2)
        margen_libre_anu = round(tot_ent_anu - tot_gas_anu, 2)

        # Ratios de Salud Financiera
        ratio_cobertura = round((tot_ent_men / tot_gas_men), 2) if tot_gas_men > 0 else 0.0
        tasa_ahorro_pct = round((margen_libre_men / tot_ent_men * 100.0), 1) if tot_ent_men > 0 else 0.0
        gasto_diario_est = round(tot_gas_men / (365.0 / 12.0), 2) if tot_gas_men > 0 else 0.0
        ingreso_diario_est = round(tot_ent_men / (365.0 / 12.0), 2) if tot_ent_men > 0 else 0.0

        return jsonify({
            'success': True,
            'tasa_bcv': tasa_bcv,
            'kpis': {
                'entradas_mensual': tot_ent_men,
                'entradas_anual': tot_ent_anu,
                'gastos_mensual': tot_gas_men,
                'gastos_anual': tot_gas_anu,
                'margen_libre_mensual': margen_libre_men,
                'margen_libre_anual': margen_libre_anu,
                'ratio_cobertura': ratio_cobertura,
                'tasa_ahorro_pct': tasa_ahorro_pct,
                'gasto_diario_est': gasto_diario_est,
                'ingreso_diario_est': ingreso_diario_est,
                'total_items': len(rows),
                'total_entradas_count': len(entradas),
                'total_gastos_count': len(gastos)
            },
            'distribucion_gastos': cat_gastos,
            'distribucion_entradas': cat_entradas,
            'entradas': entradas,
            'gastos': gastos
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@proyeccion_bp.route('/api/proyeccion/item', methods=['POST'])
def crear_item_proyeccion():
    """Crea una nueva entrada fija o gasto fijo en el planificador."""
    try:
        data = request.get_json() or {}
        tipo = (data.get('tipo') or 'GASTO').strip().upper()
        if tipo not in ('ENTRADA', 'GASTO'):
            return jsonify({'success': False, 'error': 'Tipo debe ser ENTRADA o GASTO'}), 400

        concepto = (data.get('concepto') or '').strip()
        if not concepto:
            return jsonify({'success': False, 'error': 'El concepto o descripción es obligatorio'}), 400

        categoria = (data.get('categoria') or ('Sueldo / Salario Fijo' if tipo == 'ENTRADA' else 'Servicios Básicos')).strip()
        frecuencia = (data.get('frecuencia') or 'MENSUAL').strip().upper()
        moneda = (data.get('moneda') or 'USD').strip().upper()
        monto_orig = float(data.get('monto_original') or 0.0)
        tasa_custom = float(data.get('tasa') or 1.0)
        dia_pago = int(data.get('dia_pago')) if data.get('dia_pago') else None
        notas = (data.get('notas') or '').strip()
        activo = 1 if data.get('activo', True) else 0

        db = get_db()
        tasa_bcv = obtener_tasa_bcv_activa(db)

        calc = normalizar_monto_proyeccion(monto_orig, frecuencia, moneda, tasa_custom, tasa_bcv)

        cur = db.cursor()
        cur.execute("""
            INSERT INTO finanzas_proyeccion_items
            (tipo, concepto, categoria, frecuencia, moneda, monto_original, tasa,
             monto_mensual_usd, monto_anual_usd, activo, dia_pago, notas)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tipo,
            concepto,
            categoria,
            calc['frecuencia'],
            calc['moneda'],
            calc['monto_original'],
            calc['tasa'],
            calc['monto_mensual_usd'],
            calc['monto_anual_usd'],
            activo,
            dia_pago,
            notas
        ))
        db.commit()
        item_id = cur.lastrowid

        return jsonify({
            'success': True,
            'mensaje': f"{'Entrada fija' if tipo == 'ENTRADA' else 'Gasto fijo'} registrado exitosamente.",
            'item_id': item_id,
            'calculos': calc
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@proyeccion_bp.route('/api/proyeccion/item/<int:item_id>', methods=['PUT'])
def actualizar_item_proyeccion(item_id):
    """Actualiza los datos y recalcula montos normalizados de un ítem existente."""
    try:
        data = request.get_json() or {}
        db = get_db()
        existente = db.execute("SELECT * FROM finanzas_proyeccion_items WHERE id = ?", (item_id,)).fetchone()
        if not existente:
            return jsonify({'success': False, 'error': 'Ítem no encontrado'}), 404

        tipo = (data.get('tipo') or existente['tipo']).strip().upper()
        concepto = (data.get('concepto') or existente['concepto']).strip()
        categoria = (data.get('categoria') or existente['categoria']).strip()
        frecuencia = (data.get('frecuencia') or existente['frecuencia']).strip().upper()
        moneda = (data.get('moneda') or existente['moneda']).strip().upper()
        monto_orig = float(data.get('monto_original', existente['monto_original']))
        tasa_custom = float(data.get('tasa', existente['tasa']))
        dia_pago = int(data.get('dia_pago')) if data.get('dia_pago') else None
        notas = data.get('notas', existente['notas'] or '').strip()
        activo = int(data.get('activo', existente['activo']))

        tasa_bcv = obtener_tasa_bcv_activa(db)
        calc = normalizar_monto_proyeccion(monto_orig, frecuencia, moneda, tasa_custom, tasa_bcv)
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        db.execute("""
            UPDATE finanzas_proyeccion_items
            SET tipo = ?,
                concepto = ?,
                categoria = ?,
                frecuencia = ?,
                moneda = ?,
                monto_original = ?,
                tasa = ?,
                monto_mensual_usd = ?,
                monto_anual_usd = ?,
                activo = ?,
                dia_pago = ?,
                notas = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            tipo,
            concepto,
            categoria,
            calc['frecuencia'],
            calc['moneda'],
            calc['monto_original'],
            calc['tasa'],
            calc['monto_mensual_usd'],
            calc['monto_anual_usd'],
            activo,
            dia_pago,
            notas,
            ahora,
            item_id
        ))
        db.commit()

        return jsonify({
            'success': True,
            'mensaje': 'Movimiento recurrente actualizado correctamente.',
            'calculos': calc
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@proyeccion_bp.route('/api/proyeccion/item/<int:item_id>/toggle', methods=['PATCH'])
def toggle_activo_item(item_id):
    """Activa o desactiva un ítem para simular escenarios en tiempo real."""
    try:
        db = get_db()
        existente = db.execute("SELECT activo, concepto FROM finanzas_proyeccion_items WHERE id = ?", (item_id,)).fetchone()
        if not existente:
            return jsonify({'success': False, 'error': 'Ítem no encontrado'}), 404

        nuevo_estado = 0 if existente['activo'] else 1
        db.execute("UPDATE finanzas_proyeccion_items SET activo = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (nuevo_estado, item_id))
        db.commit()

        return jsonify({
            'success': True,
            'activo': bool(nuevo_estado),
            'mensaje': f"'{existente['concepto']}' {'activado' if nuevo_estado else 'desactivado en simulación'}."
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@proyeccion_bp.route('/api/proyeccion/item/<int:item_id>', methods=['DELETE'])
def eliminar_item_proyeccion(item_id):
    """Elimina permanentemente un ítem del planificador de proyección."""
    try:
        db = get_db()
        db.execute("DELETE FROM finanzas_proyeccion_items WHERE id = ?", (item_id,))
        db.commit()
        return jsonify({'success': True, 'mensaje': 'Elemento eliminado de la proyección.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@proyeccion_bp.route('/api/proyeccion/recalcular-tasas', methods=['POST'])
def recalcular_con_tasa_bcv_actual():
    """Recalcula todos los ítems denominados en Bolívares usando la tasa BCV más reciente."""
    try:
        db = get_db()
        tasa_bcv = obtener_tasa_bcv_activa(db)
        items_bs = db.execute("SELECT * FROM finanzas_proyeccion_items WHERE moneda IN ('BS', 'BOLIVARES')").fetchall()

        actualizados = 0
        for r in items_bs:
            calc = normalizar_monto_proyeccion(r['monto_original'], r['frecuencia'], r['moneda'], tasa_bcv, tasa_bcv)
            db.execute("""
                UPDATE finanzas_proyeccion_items
                SET tasa = ?, monto_mensual_usd = ?, monto_anual_usd = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (calc['tasa'], calc['monto_mensual_usd'], calc['monto_anual_usd'], r['id']))
            actualizados += 1

        db.commit()
        return jsonify({
            'success': True,
            'actualizados': actualizados,
            'tasa_bcv': tasa_bcv,
            'mensaje': f"Se recalcularon {actualizados} ítems en Bolívares con la tasa BCV actual ({tasa_bcv:.2f} Bs/$)."
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
