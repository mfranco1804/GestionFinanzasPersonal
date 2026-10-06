"""
routes/api_cuadre_personal.py — Módulo de Cuadre Financiero Personal
Cálculos contables a 2 decimales. Control de 3 Potes de Liquidez:
Efectivo ($ USD), Binance (USDT) y Bolívares (Bs con conversión a tasa).
Sin compras comerciales; ingresos por sueldo y diversas fuentes.
"""
import os
import json
import re
import calendar
from datetime import datetime, date
from flask import Blueprint, request, jsonify
from database import get_db

cuadre_personal_bp = Blueprint('cuadre_personal_api', __name__)

DIAS_SEMANA = [
    (1, "LUNES"),
    (2, "MARTES"),
    (3, "MIÉRCOLES"),
    (4, "JUEVES"),
    (5, "VIERNES"),
    (6, "SÁBADO"),
    (7, "DOMINGO")
]

def r2(val) -> float:
    """Redondea de forma segura a 2 decimales."""
    try:
        if val is None:
            return 0.0
        return round(float(val), 2)
    except (ValueError, TypeError):
        return 0.0

def evaluar_formula_excel(texto_val):
    """
    Evalúa expresiones aritméticas tipo Excel como '=100+250.5-20' o '15*3'.
    Retorna (valor_float, formula_str).
    """
    if not texto_val or not isinstance(texto_val, str):
        return r2(texto_val), ""
    
    val_limpio = texto_val.strip()
    es_formula = val_limpio.startswith('=')
    expresion = val_limpio[1:].strip() if es_formula else val_limpio

    # Si solo contiene caracteres aritméticos válidos
    if re.match(r'^[0-9\.\+\-\*\/\s\(\)]+$', expresion):
        try:
            # Eval seguro limitado solo a operadores básicos
            resultado = eval(expresion, {"__builtins__": None}, {})
            return r2(resultado), val_limpio
        except Exception:
            pass

    try:
        return r2(float(expresion)), (val_limpio if es_formula else "")
    except Exception:
        return 0.0, ""

def compute_month_calendar_weeks(mes_str):
    """
    Calcula las semanas de calendario del mes (de Lunes a Domingo).
    Garantiza estrictamente que solo los días pertenecientes al mes especificado
    tengan fecha asignada y estén marcados como activos (en_mes=True).
    """
    try:
        year, month = map(int, mes_str.split('-'))
    except Exception:
        now = datetime.now()
        year, month = now.year, now.month
        mes_str = f"{year:04d}-{month:02d}"

    cal = calendar.Calendar(firstweekday=0) # 0 = Lunes
    raw_weeks = cal.monthdatescalendar(year, month)
    semanas_info = {}
    dias_matriz = []
    dias_nombres = ['LUNES', 'MARTES', 'MIÉRCOLES', 'JUEVES', 'VIERNES', 'SÁBADO', 'DOMINGO']

    for s_idx, w in enumerate(raw_weeks, 1):
        dias_en_mes = [d for d in w if d.month == month]
        if not dias_en_mes:
            continue
        ini_fmt = dias_en_mes[0].strftime('%d/%m')
        fin_fmt = dias_en_mes[-1].strftime('%d/%m')
        semanas_info[s_idx] = {
            'numero': s_idx,
            'inicio': str(dias_en_mes[0]),
            'fin': str(dias_en_mes[-1]),
            'label': f"Semana {s_idx} ({ini_fmt} al {fin_fmt})",
            'rango_corto': f"{ini_fmt} - {fin_fmt}"
        }
        for d_idx, d_nom in enumerate(dias_nombres, 1):
            d = w[d_idx - 1]
            if d.month == month:
                dias_matriz.append((s_idx, d_idx, d_nom, str(d), True))
            else:
                dias_matriz.append((s_idx, d_idx, d_nom, '', False))

    return semanas_info, dias_matriz

def get_week_number_for_date(fecha_str: str) -> int:
    """Calcula automáticamente a qué semana del mes (1..N) corresponde la fecha."""
    try:
        dt = datetime.strptime(fecha_str[:10], '%Y-%m-%d').date()
        mes_str = dt.strftime('%Y-%m')
        semanas_info, dias_matriz = compute_month_calendar_weeks(mes_str)
        for s_idx, d_idx, d_nom, f_dia, en_mes in dias_matriz:
            if f_dia == str(dt):
                return s_idx
        # Fallback proporcional
        return min(max(1, (dt.day - 1) // 7 + 1), len(semanas_info) or 5)
    except Exception:
        return 1

def _ensure_month_matrix(db, mes: str):
    """Asegura que existan las filas con las fechas de calendario exactas para cada día."""
    cursor = db.cursor()
    semanas_info, dias_matriz = compute_month_calendar_weeks(mes)
    
    for s_idx, d_idx, d_nom, fecha_dia, en_mes in dias_matriz:
        cursor.execute("""
            INSERT OR IGNORE INTO finanzas_ingresos_semanales 
            (mes, semana, dia_indice, dia_nombre, fecha, fuente, usd_efectivo, usdt_binance, tasa, bs, bs_a_usd, total_usd, modificado_manual)
            VALUES (?, ?, ?, ?, ?, 'Sueldo / Salario Fijo', 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0)
        """, (mes, s_idx, d_idx, d_nom, fecha_dia))
        
        if en_mes:
            cursor.execute("""
                UPDATE finanzas_ingresos_semanales
                SET fecha = ?, dia_nombre = ?
                WHERE mes = ? AND semana = ? AND dia_indice = ? AND (fecha = '' OR fecha IS NULL)
            """, (fecha_dia, d_nom, mes, s_idx, d_idx))

    # Asegurar fila de balance mensual
    cursor.execute("""
        INSERT OR IGNORE INTO finanzas_mes_balance (mes, saldo_inicio_efectivo, efectivo_en_mano, saldo_bcv, meta_ahorro_usd)
        VALUES (?, 0.0, 0.0, 1.0, 500.0)
    """, (mes,))
    db.commit()

def get_cierre_mes_anterior(mes_str, db):
    """Obtiene los saldos de cierre del mes inmediatamente anterior para rollover."""
    try:
        dt = datetime.strptime(mes_str, '%Y-%m')
        if dt.month == 1:
            mes_prev = f"{dt.year - 1}-12"
        else:
            mes_prev = f"{dt.year}-{dt.month - 1:02d}"

        prev_row = db.execute("SELECT * FROM finanzas_mes_balance WHERE mes = ?", (mes_prev,)).fetchone()
        if not prev_row:
            return 0.0, {}, 1.0

        efectivo_cierre = r2(prev_row['efectivo_en_mano']) or r2(prev_row['saldo_inicio_efectivo'])
        bancos = {}
        try:
            if prev_row['bancos_json']:
                bancos = json.loads(prev_row['bancos_json'])
        except Exception:
            pass
        tasa_bcv = r2(prev_row['saldo_bcv']) or 1.0
        return efectivo_cierre, bancos, tasa_bcv
    except Exception:
        return 0.0, {}, 1.0

# =========================================================================
# RUTAS DE INGRESOS PERSONALES DINÁMICOS (Por Pote, similar a Gastos)
# =========================================================================

@cuadre_personal_bp.route('/api/cuadre/ingresos/<mes>', methods=['GET'])
def get_ingresos(mes):
    """Retorna los ingresos personales registrados en el mes con totales por pote y por semana."""
    db = get_db()
    rows = db.execute("""
        SELECT * FROM finanzas_ingresos 
        WHERE mes = ? OR substr(fecha, 1, 7) = ?
        ORDER BY fecha DESC, id DESC
    """, (mes, mes)).fetchall()

    # Tasas activas y preferencia de valuación
    cfg_row = db.execute("SELECT tasa_bcv, tasa_bcv_euro, tasa_usdt, tasa_preferida_bs FROM app_config WHERE id = 1").fetchone()
    tasa_bcv = float(cfg_row['tasa_bcv']) if cfg_row and cfg_row['tasa_bcv'] else 1.0
    tasa_euro = float(cfg_row['tasa_bcv_euro']) if cfg_row and cfg_row['tasa_bcv_euro'] else 1.0
    tasa_usdt = float(cfg_row['tasa_usdt']) if cfg_row and cfg_row['tasa_usdt'] else 1.0
    tasa_pref = (request.args.get('tasa_tipo') or (cfg_row['tasa_preferida_bs'] if cfg_row and 'tasa_preferida_bs' in cfg_row.keys() else 'BCV')).upper()

    tasa_activa_bs = tasa_bcv
    if tasa_pref == 'USDT':
        tasa_activa_bs = tasa_usdt
    elif tasa_pref == 'EURO':
        tasa_activa_bs = tasa_euro

    ingresos_list = []
    tot_efectivo = 0.0
    tot_binance = 0.0
    tot_bs_nominal = 0.0

    semanas_totales = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0}

    for r in rows:
        d = dict(r)
        d['monto_original'] = r2(d['monto_original'])
        m = (d['moneda'] or '').upper()

        if m in ('BINANCE', 'USDT'):
            d['monto_usd'] = r2(d['monto_usd']) or r2(d['monto_original'])
            tot_binance = r2(tot_binance + d['monto_usd'])
            d_val_equiv = d['monto_usd']
        elif m in ('BS', 'BOLIVARES'):
            # Para Bolívares se preserva el monto nominal puro y se valúa en vivo
            d['tasa'] = r2(tasa_activa_bs)
            val_bcv = r2(d['monto_original'] / tasa_bcv) if tasa_bcv > 0 else 0.0
            val_usdt = r2(d['monto_original'] / tasa_usdt) if tasa_usdt > 0 else 0.0
            val_euro = r2(d['monto_original'] / tasa_euro) if tasa_euro > 0 else 0.0
            val_elegida = r2(d['monto_original'] / tasa_activa_bs) if tasa_activa_bs > 0 else 0.0

            d['monto_usd'] = val_elegida
            d['valuaciones_en_vivo'] = {
                'bcv_usd': val_bcv,
                'binance_usdt': val_usdt,
                'bcv_euro': val_euro,
                'tasa_preferida': tasa_pref
            }
            tot_bs_nominal = r2(tot_bs_nominal + d['monto_original'])
            d_val_equiv = val_elegida
        else:
            d['monto_usd'] = r2(d['monto_usd']) or r2(d['monto_original'])
            tot_efectivo = r2(tot_efectivo + d['monto_usd'])
            d_val_equiv = d['monto_usd']

        ingresos_list.append(d)

        sem = d.get('semana', 1)
        if sem in semanas_totales:
            semanas_totales[sem] = r2(semanas_totales[sem] + d_val_equiv)

    # Valuaciones en vivo de todo el Pote de Bolívares del mes
    tot_bs_bcv = r2(tot_bs_nominal / tasa_bcv) if tasa_bcv > 0 else 0.0
    tot_bs_usdt = r2(tot_bs_nominal / tasa_usdt) if tasa_usdt > 0 else 0.0
    tot_bs_euro = r2(tot_bs_nominal / tasa_euro) if tasa_euro > 0 else 0.0
    tot_bs_elegido = r2(tot_bs_nominal / tasa_activa_bs) if tasa_activa_bs > 0 else 0.0

    tot_general = r2(tot_efectivo + tot_binance + tot_bs_elegido)

    return jsonify({
        'success': True,
        'mes': mes,
        'ingresos': ingresos_list,
        'totales_pote': {
            'efectivo_usd': tot_efectivo,
            'binance_usdt': tot_binance,
            'bs_usd': tot_bs_elegido,
            'bs_nominal': tot_bs_nominal,
            'bs_live': {
                'bcv_usd': tot_bs_bcv,
                'binance_usdt': tot_bs_usdt,
                'bcv_euro': tot_bs_euro,
                'tasa_preferida': tasa_pref,
                'tasa_usada': tasa_activa_bs
            },
            'total_usd': tot_general,
            'conteo': len(ingresos_list)
        },
        'semanas_totales': semanas_totales
    })

@cuadre_personal_bp.route('/api/cuadre/ingresos', methods=['POST'])
def crear_ingreso():
    """Registra un nuevo ingreso personal asignado al pote de entrada."""
    data = request.get_json() or {}
    mes = data.get('mes')
    fecha = data.get('fecha') or str(date.today())
    if not mes:
        mes = fecha[:7]

    semana = data.get('semana') or get_week_number_for_date(fecha)
    concepto = (data.get('concepto') or '').strip()
    fuente = (data.get('fuente') or 'Sueldo / Salario Fijo').strip()
    moneda = (data.get('moneda') or 'EFECTIVO').strip().upper()
    monto_orig = r2(data.get('monto_original', 0.0))
    tasa = r2(data.get('tasa', 1.0)) or 1.0
    referencia = (data.get('referencia') or '').strip()
    nota = (data.get('nota') or '').strip()

    if not concepto:
        return jsonify({'success': False, 'error': 'El concepto o descripción del ingreso es obligatorio'}), 400
    if monto_orig <= 0:
        return jsonify({'success': False, 'error': 'El monto del ingreso debe ser mayor a 0'}), 400

    db = get_db()
    if moneda in ('BS', 'BOLIVARES'):
        if tasa <= 1.0:
            cfg_row = db.execute("SELECT tasa_bcv FROM app_config WHERE id = 1").fetchone()
            if cfg_row and cfg_row['tasa_bcv'] and float(cfg_row['tasa_bcv']) > 1.0:
                tasa = r2(cfg_row['tasa_bcv'])
        monto_usd = r2(monto_orig / tasa) if tasa > 0 else 0.0
    else:
        monto_usd = monto_orig
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO finanzas_ingresos 
        (mes, semana, fecha, concepto, fuente, moneda, monto_original, tasa, monto_usd, referencia, nota)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (mes, semana, fecha, concepto, fuente, moneda, monto_orig, tasa, monto_usd, referencia, nota))
    db.commit()

    return jsonify({'success': True, 'id': cursor.lastrowid, 'mensaje': 'Ingreso registrado correctamente'})

@cuadre_personal_bp.route('/api/cuadre/ingresos/<int:ingreso_id>', methods=['DELETE'])
def eliminar_ingreso(ingreso_id):
    """Elimina un ingreso registrado."""
    db = get_db()
    db.execute("DELETE FROM finanzas_ingresos WHERE id = ?", (ingreso_id,))
    db.commit()
    return jsonify({'success': True, 'mensaje': 'Ingreso eliminado correctamente'})

# =========================================================================
# RUTAS DE GASTOS PERSONALES (Manejado tal cual por los 3 potes)
# =========================================================================

@cuadre_personal_bp.route('/api/cuadre/gastos/<mes>', methods=['GET'])
def get_gastos(mes):
    """Retorna los gastos personales clasificados por los 3 potes y semanas."""
    db = get_db()
    rows = db.execute("""
        SELECT * FROM finanzas_gastos 
        WHERE mes = ? OR substr(fecha, 1, 7) = ?
        ORDER BY fecha DESC, id DESC
    """, (mes, mes)).fetchall()

    # Tasas activas y preferencia de valuación
    cfg_row = db.execute("SELECT tasa_bcv, tasa_bcv_euro, tasa_usdt, tasa_preferida_bs FROM app_config WHERE id = 1").fetchone()
    tasa_bcv = float(cfg_row['tasa_bcv']) if cfg_row and cfg_row['tasa_bcv'] else 1.0
    tasa_euro = float(cfg_row['tasa_bcv_euro']) if cfg_row and cfg_row['tasa_bcv_euro'] else 1.0
    tasa_usdt = float(cfg_row['tasa_usdt']) if cfg_row and cfg_row['tasa_usdt'] else 1.0
    tasa_pref = (request.args.get('tasa_tipo') or (cfg_row['tasa_preferida_bs'] if cfg_row and 'tasa_preferida_bs' in cfg_row.keys() else 'BCV')).upper()

    tasa_activa_bs = tasa_bcv
    if tasa_pref == 'USDT':
        tasa_activa_bs = tasa_usdt
    elif tasa_pref == 'EURO':
        tasa_activa_bs = tasa_euro

    gastos_list = []
    tot_efectivo = 0.0
    tot_binance = 0.0
    tot_bs_nominal = 0.0

    for r in rows:
        d = dict(r)
        d['monto_original'] = r2(d['monto_original'])
        d['tasa'] = r2(d['tasa']) or 1.0
        d['monto_usd'] = r2(d['monto_usd'])

        m = (d['moneda'] or '').upper()
        if m in ('BINANCE', 'USDT'):
            d['monto_usd'] = r2(d['monto_usd']) or r2(d['monto_original'])
            tot_binance = r2(tot_binance + d['monto_usd'])
        elif m in ('BS', 'BOLIVARES'):
            d['tasa'] = r2(tasa_activa_bs)
            val_bcv = r2(d['monto_original'] / tasa_bcv) if tasa_bcv > 0 else 0.0
            val_usdt = r2(d['monto_original'] / tasa_usdt) if tasa_usdt > 0 else 0.0
            val_euro = r2(d['monto_original'] / tasa_euro) if tasa_euro > 0 else 0.0
            val_elegida = r2(d['monto_original'] / tasa_activa_bs) if tasa_activa_bs > 0 else 0.0

            d['monto_usd'] = val_elegida
            d['valuaciones_en_vivo'] = {
                'bcv_usd': val_bcv,
                'binance_usdt': val_usdt,
                'bcv_euro': val_euro,
                'tasa_preferida': tasa_pref
            }
            tot_bs_nominal = r2(tot_bs_nominal + d['monto_original'])
        else:
            d['monto_usd'] = r2(d['monto_usd']) or r2(d['monto_original'])
            tot_efectivo = r2(tot_efectivo + d['monto_usd'])

        gastos_list.append(d)

    tot_bs_bcv = r2(tot_bs_nominal / tasa_bcv) if tasa_bcv > 0 else 0.0
    tot_bs_usdt = r2(tot_bs_nominal / tasa_usdt) if tasa_usdt > 0 else 0.0
    tot_bs_euro = r2(tot_bs_nominal / tasa_euro) if tasa_euro > 0 else 0.0
    tot_bs_elegido = r2(tot_bs_nominal / tasa_activa_bs) if tasa_activa_bs > 0 else 0.0

    tot_general = r2(tot_efectivo + tot_binance + tot_bs_elegido)

    return jsonify({
        'success': True,
        'mes': mes,
        'gastos': gastos_list,
        'totales_pote': {
            'efectivo_usd': tot_efectivo,
            'binance_usdt': tot_binance,
            'bs_usd': tot_bs_elegido,
            'bs_nominal': tot_bs_nominal,
            'bs_live': {
                'bcv_usd': tot_bs_bcv,
                'binance_usdt': tot_bs_usdt,
                'bcv_euro': tot_bs_euro,
                'tasa_preferida': tasa_pref,
                'tasa_usada': tasa_activa_bs
            },
            'total_usd': tot_general,
            'conteo': len(gastos_list)
        }
    })

@cuadre_personal_bp.route('/api/cuadre/gastos', methods=['POST'])
def crear_gasto():
    """Registra un nuevo gasto personal asignado a su pote."""
    data = request.get_json() or {}
    mes = data.get('mes')
    fecha = data.get('fecha') or str(date.today())
    if not mes:
        mes = fecha[:7]

    semana = data.get('semana') or get_week_number_for_date(fecha)
    descripcion = (data.get('descripcion') or '').strip()
    categoria = data.get('categoria') or 'Alimentación y Supermercado'
    moneda = (data.get('moneda') or 'EFECTIVO').strip().upper()
    monto_orig = r2(data.get('monto_original', 0.0))
    tasa = r2(data.get('tasa', 1.0)) or 1.0
    referencia = (data.get('referencia') or '').strip()

    if not descripcion:
        return jsonify({'success': False, 'error': 'La descripción del gasto es obligatoria'}), 400
    if monto_orig <= 0:
        return jsonify({'success': False, 'error': 'El monto debe ser mayor a 0'}), 400

    db = get_db()
    if moneda in ('BS', 'BOLIVARES'):
        if tasa <= 1.0:
            cfg_row = db.execute("SELECT tasa_bcv FROM app_config WHERE id = 1").fetchone()
            if cfg_row and cfg_row['tasa_bcv'] and float(cfg_row['tasa_bcv']) > 1.0:
                tasa = r2(cfg_row['tasa_bcv'])
        monto_usd = r2(monto_orig / tasa) if tasa > 0 else 0.0
    else:
        monto_usd = monto_orig

    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO finanzas_gastos 
        (mes, semana, fecha, descripcion, categoria, moneda, monto_original, tasa, monto_usd, referencia)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (mes, semana, fecha, descripcion, categoria, moneda, monto_orig, tasa, monto_usd, referencia))
    db.commit()

    return jsonify({'success': True, 'id': cursor.lastrowid, 'mensaje': 'Gasto registrado correctamente'})

@cuadre_personal_bp.route('/api/cuadre/gastos/<int:gasto_id>', methods=['DELETE'])
def eliminar_gasto(gasto_id):
    """Elimina un gasto personal."""
    db = get_db()
    db.execute("DELETE FROM finanzas_gastos WHERE id = ?", (gasto_id,))
    db.commit()
    return jsonify({'success': True, 'mensaje': 'Gasto eliminado correctamente'})

# =========================================================================
# RUTAS DE CAMBIOS INTERNOS ENTRE POTES (Arbitraje / Transferencias)
# =========================================================================

@cuadre_personal_bp.route('/api/cuadre/cambios-internos/<mes>', methods=['GET'])
def get_cambios_internos(mes):
    """Retorna los cambios internos entre potes del mes."""
    db = get_db()
    rows = db.execute("""
        SELECT * FROM finanzas_cambios_internos 
        WHERE mes = ? 
        ORDER BY fecha DESC, id DESC
    """, (mes,)).fetchall()

    cambios_list = []
    efectivo_entradas = 0.0
    efectivo_salidas = 0.0
    binance_entradas = 0.0
    binance_salidas = 0.0
    bs_entradas_nominal = 0.0
    bs_salidas_nominal = 0.0
    bs_entradas_usd = 0.0
    bs_salidas_usd = 0.0

    for r in rows:
        d = dict(r)
        p_orig = (d['pote_origen'] or '').strip().upper()
        p_dest = (d['pote_destino'] or '').strip().upper()
        m_orig = r2(d['monto_origen'])
        m_dest = r2(d['monto_destino'])
        t = r2(d['tasa']) or 1.0

        d['monto_origen'] = m_orig
        d['monto_destino'] = m_dest
        d['tasa'] = t
        cambios_list.append(d)

        if p_dest == 'EFECTIVO':
            efectivo_entradas = r2(efectivo_entradas + m_dest)
        if p_orig == 'EFECTIVO':
            efectivo_salidas = r2(efectivo_salidas + m_orig)

        if p_dest == 'BINANCE':
            binance_entradas = r2(binance_entradas + m_dest)
        if p_orig == 'BINANCE':
            binance_salidas = r2(binance_salidas + m_orig)

        if p_dest in ('BOLIVARES', 'BS'):
            bs_entradas_nominal = r2(bs_entradas_nominal + m_dest)
            usd_equiv = m_orig if p_orig in ('EFECTIVO', 'BINANCE') else (r2(m_dest / t) if t > 0 else 0.0)
            bs_entradas_usd = r2(bs_entradas_usd + usd_equiv)
        if p_orig in ('BOLIVARES', 'BS'):
            bs_salidas_nominal = r2(bs_salidas_nominal + m_orig)
            usd_equiv = m_dest if p_dest in ('EFECTIVO', 'BINANCE') else (r2(m_orig / t) if t > 0 else 0.0)
            bs_salidas_usd = r2(bs_salidas_usd + usd_equiv)

    return jsonify({
        'success': True,
        'mes': mes,
        'cambios': cambios_list,
        'netos': {
            'efectivo_neto': r2(efectivo_entradas - efectivo_salidas),
            'binance_neto': r2(binance_entradas - binance_salidas),
            'bs_neto_usd': r2(bs_entradas_usd - bs_salidas_usd),
            'bs_neto_nominal': r2(bs_entradas_nominal - bs_salidas_nominal)
        }
    })

@cuadre_personal_bp.route('/api/cuadre/cambios-internos', methods=['POST'])
def crear_cambio_interno():
    """Registra una transferencia o cambio de divisa entre potes."""
    data = request.get_json() or {}
    mes = data.get('mes')
    fecha = data.get('fecha') or str(date.today())
    if not mes:
        mes = fecha[:7]

    pote_origen = (data.get('pote_origen') or '').strip().upper()
    monto_origen = r2(data.get('monto_origen', 0.0))
    pote_destino = (data.get('pote_destino') or '').strip().upper()
    monto_destino = r2(data.get('monto_destino', 0.0))
    tasa = r2(data.get('tasa', 1.0)) or 1.0
    nota = (data.get('nota') or '').strip()

    if pote_origen == pote_destino:
        return jsonify({'success': False, 'error': 'El pote de origen y destino deben ser diferentes'}), 400
    if monto_origen <= 0 or monto_destino <= 0:
        return jsonify({'success': False, 'error': 'Los montos deben ser mayores a 0'}), 400

    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO finanzas_cambios_internos 
        (mes, fecha, pote_origen, monto_origen, pote_destino, monto_destino, tasa, nota)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (mes, fecha, pote_origen, monto_origen, pote_destino, monto_destino, tasa, nota))
    db.commit()

    return jsonify({'success': True, 'id': cursor.lastrowid, 'mensaje': 'Transferencia interna registrada'})

@cuadre_personal_bp.route('/api/cuadre/cambios-internos/<int:cambio_id>', methods=['DELETE'])
def eliminar_cambio_interno(cambio_id):
    """Elimina un cambio interno."""
    db = get_db()
    db.execute("DELETE FROM finanzas_cambios_internos WHERE id = ?", (cambio_id,))
    db.commit()
    return jsonify({'success': True, 'mensaje': 'Cambio interno eliminado'})

# =========================================================================
# RUTAS DE FONDO DE AHORROS Y METAS
# =========================================================================

@cuadre_personal_bp.route('/api/cuadre/ahorro/<mes>', methods=['GET'])
def get_ahorros(mes):
    """Retorna los movimientos y saldo acumulado del fondo de ahorros."""
    db = get_db()
    rows = db.execute("""
        SELECT * FROM finanzas_ahorros 
        WHERE mes = ? OR substr(fecha, 1, 7) = ?
        ORDER BY fecha ASC, id ASC
    """, (mes, mes)).fetchall()

    bal_row = db.execute("SELECT ahorro_saldo_inicial FROM finanzas_mes_balance WHERE mes = ?", (mes,)).fetchone()
    saldo_inicial = r2(bal_row['ahorro_saldo_inicial']) if (bal_row and bal_row['ahorro_saldo_inicial'] is not None) else 0.0

    ahorros_list = []
    total_aportes = 0.0
    total_retiros = 0.0
    saldo_acum = saldo_inicial

    for r in rows:
        d = dict(r)
        m = r2(d['monto_usd'] or d.get('total', 0.0))
        d['monto_usd'] = m
        tipo = (d.get('tipo') or 'APORTE').upper()
        if tipo == 'RETIRO':
            total_retiros = r2(total_retiros + m)
            saldo_acum = r2(saldo_acum - m)
        else:
            total_aportes = r2(total_aportes + m)
            saldo_acum = r2(saldo_acum + m)
        d['saldo_acumulado'] = saldo_acum
        ahorros_list.append(d)

    return jsonify({
        'success': True,
        'mes': mes,
        'saldo_inicial': saldo_inicial,
        'ahorros': ahorros_list,
        'total_aportes': total_aportes,
        'total_retiros': total_retiros,
        'saldo_final': saldo_acum
    })

@cuadre_personal_bp.route('/api/cuadre/ahorro', methods=['POST'])
def crear_ahorro():
    """Registra un aporte o retiro del fondo de ahorros."""
    data = request.get_json() or {}
    mes = data.get('mes')
    fecha = data.get('fecha') or str(date.today())
    if not mes:
        mes = fecha[:7]

    tipo = (data.get('tipo') or 'APORTE').upper()
    concepto = (data.get('concepto') or '').strip()
    monto_usd = r2(data.get('monto_usd', 0.0))
    referencia = (data.get('referencia') or '').strip()

    if monto_usd <= 0:
        return jsonify({'success': False, 'error': 'El monto de ahorro debe ser mayor a 0'}), 400

    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO finanzas_ahorros (mes, fecha, tipo, concepto, monto_usd, referencia)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (mes, fecha, tipo, concepto, monto_usd, referencia))
    db.commit()

    return jsonify({'success': True, 'id': cursor.lastrowid, 'mensaje': 'Movimiento de ahorro registrado'})

@cuadre_personal_bp.route('/api/cuadre/ahorro/saldo-inicial', methods=['POST'])
def guardar_ahorro_saldo_inicial():
    """Configura el saldo inicial de ahorro del mes."""
    data = request.get_json() or {}
    mes = data.get('mes')
    saldo_inicial = r2(data.get('saldo_inicial', 0.0))

    if not mes:
        return jsonify({'success': False, 'error': 'El mes es requerido'}), 400

    db = get_db()
    db.execute("""
        INSERT INTO finanzas_mes_balance (mes, ahorro_saldo_inicial)
        VALUES (?, ?)
        ON CONFLICT(mes) DO UPDATE SET ahorro_saldo_inicial = excluded.ahorro_saldo_inicial
    """, (mes, saldo_inicial))
    db.commit()

    return jsonify({'success': True, 'mensaje': 'Saldo inicial de ahorro actualizado'})

@cuadre_personal_bp.route('/api/cuadre/ahorro/<int:ahorro_id>', methods=['DELETE'])
def eliminar_ahorro(ahorro_id):
    """Elimina un movimiento de ahorro."""
    db = get_db()
    db.execute("DELETE FROM finanzas_ahorros WHERE id = ?", (ahorro_id,))
    db.commit()
    return jsonify({'success': True, 'mensaje': 'Registro de ahorro eliminado'})

# =========================================================================
# RUTAS DE BALANCE MENSUAL Y GANANCIAS VS PÉRDIDAS (Adaptado a Personal)
# =========================================================================

@cuadre_personal_bp.route('/api/cuadre/balance/<mes>', methods=['GET'])
def get_balance_mensual(mes):
    """
    Consolida el balance general mensual de Ganancias y Pérdidas adaptado a Uso Personal:
    Pilar 1: Arqueo de Caja Físico (Efectivo en Mano vs Teórico).
    Pilar 2: Posición de Liquidez de los 3 Potes + Cuentas Bancarias.
    Pilar 3: Rendimiento y Superávit Neto (Ingresos Personales - Gastos Personales).
    """
    db = get_db()
    _ensure_month_matrix(db, mes)

    # 1. Configuración y Balance del mes
    bal_row = db.execute("SELECT * FROM finanzas_mes_balance WHERE mes = ?", (mes,)).fetchone()
    saldo_inicio_efectivo = 0.0
    efectivo_en_mano = 0.0
    saldo_bcv = 1.0
    bancos = {
        'cuentas_bs': [
            {'id': 'banesco', 'nombre': 'Banesco', 'saldo': 0.0},
            {'id': 'venezuela', 'nombre': 'Banco de Venezuela', 'saldo': 0.0},
            {'id': 'mercantil', 'nombre': 'Mercantil', 'saldo': 0.0}
        ]
    }
    notas = ""
    meta_ahorro_usd = 500.0

    cierre_prev_efectivo, bancos_prev, tasa_prev = get_cierre_mes_anterior(mes, db)

    if bal_row:
        saldo_inicio_efectivo = r2(bal_row['saldo_inicio_efectivo'])
        efectivo_en_mano = r2(bal_row['efectivo_en_mano'])
        saldo_bcv = r2(bal_row['saldo_bcv']) or 1.0
        notas = bal_row['notas'] or ""
        meta_ahorro_usd = r2(bal_row['meta_ahorro_usd']) or 500.0
        try:
            if bal_row['bancos_json']:
                bancos = json.loads(bal_row['bancos_json'])
        except Exception:
            pass

    # Rollover automático si está en 0
    if saldo_inicio_efectivo == 0.0 and cierre_prev_efectivo > 0.0:
        saldo_inicio_efectivo = cierre_prev_efectivo

    # 2. Sumatoria de Ingresos del Mes por Pote (dinámico desde finanzas_ingresos)
    ing_rows = db.execute("""
        SELECT moneda, SUM(monto_usd) as tot, SUM(monto_original) as tot_orig
        FROM finanzas_ingresos
        WHERE mes = ? OR substr(fecha, 1, 7) = ?
        GROUP BY moneda
    """, (mes, mes)).fetchall()

    ingreso_efectivo = 0.0
    ingreso_usdt = 0.0
    ingreso_bs_a_usd = 0.0
    ingreso_bs_nominal = 0.0

    for ir in ing_rows:
        m = (ir['moneda'] or '').upper()
        if m in ('BINANCE', 'USDT'):
            ingreso_usdt = r2(ingreso_usdt + (ir['tot'] or 0.0))
        elif m in ('BS', 'BOLIVARES'):
            ingreso_bs_a_usd = r2(ingreso_bs_a_usd + (ir['tot'] or 0.0))
            ingreso_bs_nominal = r2(ingreso_bs_nominal + (ir['tot_orig'] or 0.0))
        else:
            ingreso_efectivo = r2(ingreso_efectivo + (ir['tot'] or 0.0))

    total_ingresos_mes = r2(ingreso_efectivo + ingreso_usdt + ingreso_bs_a_usd)

    # 3. Sumatoria de Gastos Personales del Mes por Pote
    gastos_rows = db.execute("""
        SELECT moneda, SUM(monto_usd) as tot, SUM(monto_original) as tot_orig
        FROM finanzas_gastos
        WHERE mes = ? OR substr(fecha, 1, 7) = ?
        GROUP BY moneda
    """, (mes, mes)).fetchall()

    gastos_efectivo_usd = 0.0
    gastos_binance_usdt = 0.0
    gastos_bs_a_usd = 0.0
    gastos_bs_nominal = 0.0

    for gr in gastos_rows:
        m = (gr['moneda'] or '').upper()
        if m in ('BINANCE', 'USDT'):
            gastos_binance_usdt = r2(gastos_binance_usdt + (gr['tot'] or 0.0))
        elif m in ('BS', 'BOLIVARES'):
            gastos_bs_a_usd = r2(gastos_bs_a_usd + (gr['tot'] or 0.0))
            gastos_bs_nominal = r2(gastos_bs_nominal + (gr['tot_orig'] or 0.0))
        else:
            gastos_efectivo_usd = r2(gastos_efectivo_usd + (gr['tot'] or 0.0))

    total_gastos_mes = r2(gastos_efectivo_usd + gastos_binance_usdt + gastos_bs_a_usd)

    # 4. Cambios Internos entre Potes
    cambios_rows = db.execute("SELECT * FROM finanzas_cambios_internos WHERE mes = ?", (mes,)).fetchall()
    cambios_efectivo_neto = 0.0
    cambios_binance_neto = 0.0
    cambios_bs_neto_usd = 0.0
    cambios_bs_neto_nominal = 0.0

    for cr in cambios_rows:
        p_orig = (cr['pote_origen'] or '').strip().upper()
        p_dest = (cr['pote_destino'] or '').strip().upper()
        m_orig = r2(cr['monto_origen'])
        m_dest = r2(cr['monto_destino'])
        t = r2(cr['tasa']) or 1.0

        if p_dest == 'EFECTIVO':
            cambios_efectivo_neto = r2(cambios_efectivo_neto + m_dest)
        if p_orig == 'EFECTIVO':
            cambios_efectivo_neto = r2(cambios_efectivo_neto - m_orig)

        if p_dest == 'BINANCE':
            cambios_binance_neto = r2(cambios_binance_neto + m_dest)
        if p_orig == 'BINANCE':
            cambios_binance_neto = r2(cambios_binance_neto - m_orig)

        if p_dest in ('BOLIVARES', 'BS'):
            cambios_bs_neto_nominal = r2(cambios_bs_neto_nominal + m_dest)
            usd_eq = m_orig if p_orig in ('EFECTIVO', 'BINANCE') else (r2(m_dest / t) if t > 0 else 0.0)
            cambios_bs_neto_usd = r2(cambios_bs_neto_usd + usd_eq)
        if p_orig in ('BOLIVARES', 'BS'):
            cambios_bs_neto_nominal = r2(cambios_bs_neto_nominal - m_orig)
            usd_eq = m_dest if p_dest in ('EFECTIVO', 'BINANCE') else (r2(m_orig / t) if t > 0 else 0.0)
            cambios_bs_neto_usd = r2(cambios_bs_neto_usd - usd_eq)

    # 5. Ahorro del Mes
    ahorro_row = db.execute("""
        SELECT SUM(monto_usd) as tot 
        FROM finanzas_ahorros 
        WHERE (mes = ? OR substr(fecha, 1, 7) = ?) AND (tipo = 'APORTE' OR tipo IS NULL)
    """, (mes, mes)).fetchone()
    total_ahorro_aportes = r2(ahorro_row['tot']) if ahorro_row and ahorro_row['tot'] else 0.0

    # 6. Pilar 1: Arqueo de Efectivo Físico
    efectivo_teorico = r2(saldo_inicio_efectivo + ingreso_efectivo - gastos_efectivo_usd - total_ahorro_aportes + cambios_efectivo_neto)
    diferencia_arqueo = r2(efectivo_en_mano - efectivo_teorico)
    if abs(diferencia_arqueo) < 0.01:
        estado_arqueo = 'CUADRADO'
    elif diferencia_arqueo > 0:
        estado_arqueo = 'SOBRANTE'
    else:
        estado_arqueo = 'FALTANTE'

    # 7. Saldos Netos de los 3 Potes con Valuación en Vivo
    cfg_rates = db.execute("SELECT tasa_bcv, tasa_bcv_euro, tasa_usdt, tasa_preferida_bs FROM app_config WHERE id = 1").fetchone()
    tasa_bcv = float(cfg_rates['tasa_bcv']) if cfg_rates and cfg_rates['tasa_bcv'] else (saldo_bcv or 1.0)
    tasa_euro = float(cfg_rates['tasa_bcv_euro']) if cfg_rates and cfg_rates['tasa_bcv_euro'] else 1.0
    tasa_usdt = float(cfg_rates['tasa_usdt']) if cfg_rates and cfg_rates['tasa_usdt'] else 1.0
    tasa_pref = (request.args.get('tasa_tipo') or (cfg_rates['tasa_preferida_bs'] if cfg_rates and 'tasa_preferida_bs' in cfg_rates.keys() else 'BCV')).upper()

    tasa_elegida = tasa_bcv
    if tasa_pref == 'USDT':
        tasa_elegida = tasa_usdt
    elif tasa_pref == 'EURO':
        tasa_elegida = tasa_euro

    # Valuaciones en vivo de gastos e ingresos en Bs
    ingreso_bs_a_usd = r2(ingreso_bs_nominal / tasa_elegida) if tasa_elegida > 0 else 0.0
    gastos_bs_a_usd = r2(gastos_bs_nominal / tasa_elegida) if tasa_elegida > 0 else 0.0
    total_ingresos_mes = r2(ingreso_efectivo + ingreso_usdt + ingreso_bs_a_usd)
    total_gastos_mes = r2(gastos_efectivo_usd + gastos_binance_usdt + gastos_bs_a_usd)

    pote_efectivo_neto = r2(ingreso_efectivo - gastos_efectivo_usd + cambios_efectivo_neto)
    pote_binance_neto = r2(ingreso_usdt - gastos_binance_usdt + cambios_binance_neto)
    pote_bs_neto_nominal = r2(ingreso_bs_nominal - gastos_bs_nominal + cambios_bs_neto_nominal)

    # Valuaciones en vivo del Pote de Bolívares
    bs_live_bcv = r2(pote_bs_neto_nominal / tasa_bcv) if tasa_bcv > 0 else 0.0
    bs_live_usdt = r2(pote_bs_neto_nominal / tasa_usdt) if tasa_usdt > 0 else 0.0
    bs_live_euro = r2(pote_bs_neto_nominal / tasa_euro) if tasa_euro > 0 else 0.0
    pote_bs_neto_usd = r2(pote_bs_neto_nominal / tasa_elegida) if tasa_elegida > 0 else 0.0

    # 8. Cuentas Bancarias en Bolívares convertidas a USD con tasa en vivo
    cuentas_bs_list = bancos.get('cuentas_bs', [])
    total_bancos_bs = r2(sum(float(c.get('saldo', 0.0) or 0.0) for c in cuentas_bs_list))
    total_bancos_bs_a_usd = r2(total_bancos_bs / tasa_elegida) if tasa_elegida > 0 else 0.0

    # 9. Pilar 2: Posición de Liquidez y Patrimonio Líquido (USD)
    liquidez_total_usd = r2(efectivo_en_mano + pote_binance_neto + total_bancos_bs_a_usd + total_ahorro_aportes)

    # 10. Pilar 3: Rendimiento y Superávit Neto Personal
    superavit_neto = r2(total_ingresos_mes - total_gastos_mes)
    tasa_ahorro_pct = r2((superavit_neto / total_ingresos_mes * 100.0) if total_ingresos_mes > 0 else 0.0)

    return jsonify({
        'success': True,
        'mes': mes,
        'config': {
            'saldo_inicio_efectivo': saldo_inicio_efectivo,
            'efectivo_en_mano': efectivo_en_mano,
            'saldo_bcv': saldo_bcv,
            'bancos': bancos,
            'notas': notas,
            'meta_ahorro_usd': meta_ahorro_usd
        },
        'pilar1_arqueo': {
            'saldo_inicio': saldo_inicio_efectivo,
            'ingresos_efectivo': ingreso_efectivo,
            'gastos_efectivo': gastos_efectivo_usd,
            'ahorros_efectivo': total_ahorro_aportes,
            'cambios_netos': cambios_efectivo_neto,
            'efectivo_teorico': efectivo_teorico,
            'efectivo_en_mano': efectivo_en_mano,
            'diferencia': diferencia_arqueo,
            'estado': estado_arqueo
        },
        'potes': {
            'efectivo': {
                'entradas': ingreso_efectivo,
                'gastos': gastos_efectivo_usd,
                'cambios_neto': cambios_efectivo_neto,
                'neto': pote_efectivo_neto
            },
            'binance': {
                'entradas': ingreso_usdt,
                'gastos': gastos_binance_usdt,
                'cambios_neto': cambios_binance_neto,
                'neto': pote_binance_neto
            },
            'bolivares': {
                'entradas_nominal': ingreso_bs_nominal,
                'entradas_usd': ingreso_bs_a_usd,
                'gastos_nominal': gastos_bs_nominal,
                'gastos_usd': gastos_bs_a_usd,
                'cambios_neto_nominal': cambios_bs_neto_nominal,
                'neto_usd': pote_bs_neto_usd,
                'neto_nominal': pote_bs_neto_nominal,
                'tasa_preferida': tasa_pref,
                'tasa_usada': tasa_elegida,
                'live': {
                    'bcv_usd': bs_live_bcv,
                    'binance_usdt': bs_live_usdt,
                    'bcv_euro': bs_live_euro
                }
            }
        },
        'bancos': {
            'cuentas': cuentas_bs_list,
            'total_bs': total_bancos_bs,
            'total_usd': total_bancos_bs_a_usd,
            'tasa_usada': tasa_elegida,
            'tasa_bcv': tasa_bcv
        },
        'pilar2_liquidez_patrimonial': {
            'efectivo_en_mano': efectivo_en_mano,
            'binance_usdt': pote_binance_neto,
            'bancos_bs_en_usd': total_bancos_bs_a_usd,
            'fondo_ahorro': total_ahorro_aportes,
            'liquidez_total_usd': liquidez_total_usd
        },
        'pilar3_rendimiento': {
            'total_ingresos': total_ingresos_mes,
            'total_gastos': total_gastos_mes,
            'superavit_neto': superavit_neto,
            'tasa_ahorro_pct': tasa_ahorro_pct,
            'estado': 'SUPERAVIT' if superavit_neto >= 0 else 'DEFICIT'
        }
    })

@cuadre_personal_bp.route('/api/cuadre/balance/<mes>', methods=['POST'])
def guardar_balance_mensual(mes):
    """Guarda los parámetros de balance (efectivo en mano, bancos, tasa BCV, etc.)."""
    data = request.get_json() or {}
    saldo_inicio = r2(data.get('saldo_inicio_efectivo', 0.0))
    efectivo_en_mano = r2(data.get('efectivo_en_mano', 0.0))
    saldo_bcv = r2(data.get('saldo_bcv', 1.0)) or 1.0
    notas = (data.get('notas') or '').strip()
    meta_ahorro = r2(data.get('meta_ahorro_usd', 500.0))

    bancos_dict = data.get('bancos') or {}
    bancos_json = json.dumps(bancos_dict, ensure_ascii=False)

    db = get_db()
    db.execute("""
        INSERT INTO finanzas_mes_balance 
        (mes, saldo_inicio_efectivo, efectivo_en_mano, saldo_bcv, bancos_json, notas, meta_ahorro_usd)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(mes) DO UPDATE SET
            saldo_inicio_efectivo = excluded.saldo_inicio_efectivo,
            efectivo_en_mano = excluded.efectivo_en_mano,
            saldo_bcv = excluded.saldo_bcv,
            bancos_json = excluded.bancos_json,
            notas = excluded.notas,
            meta_ahorro_usd = excluded.meta_ahorro_usd
    """, (mes, saldo_inicio, efectivo_en_mano, saldo_bcv, bancos_json, notas, meta_ahorro))
    db.commit()

    return jsonify({'success': True, 'mensaje': 'Balance mensual actualizado correctamente'})

# =========================================================================
# RUTAS DE GESTIÓN DE TASAS DE CAMBIO (BCV Dólar, BCV Euro, Binance USDT)
# =========================================================================

@cuadre_personal_bp.route('/api/tasas', methods=['GET'])
def get_tasas_api():
    """Retorna las tasas de cambio activas del sistema y su estado."""
    from services.rates_service import get_current_rates
    rates = get_current_rates()
    return jsonify({
        'success': True,
        'tasa_bcv': rates.get('tasa_bcv', 1.0),
        'tasa_bcv_euro': rates.get('tasa_bcv_euro', 1.0),
        'tasa_usdt': rates.get('tasa_usdt', 1.0),
        'updated_at': rates.get('tasas_updated_at', ''),
        'modo': rates.get('tasas_modo', 'AUTO'),
        'tasa_preferida_bs': rates.get('tasa_preferida_bs', 'BCV')
    })

@cuadre_personal_bp.route('/api/tasas/preferencia', methods=['POST'])
def cambiar_tasa_preferida_api():
    """Cambia la tasa de referencia preferida para valuar el Pote de Bolívares ('BCV', 'USDT', 'EURO')."""
    from services.rates_service import set_tasa_preferida_bs, get_current_rates
    data = request.get_json() or {}
    pref = data.get('preferencia', 'BCV')
    nueva_pref = set_tasa_preferida_bs(pref)
    rates = get_current_rates()
    return jsonify({
        'success': True,
        'tasa_preferida_bs': nueva_pref,
        'tasas': rates,
        'mensaje': f'Valuación del Pote de Bolívares ajustada a {nueva_pref}'
    })

@cuadre_personal_bp.route('/api/tasas/actualizar', methods=['POST'])
def actualizar_tasas_en_vivo_api():
    """Fuerza la sincronización en vivo desde BCV oficial y Binance P2P."""
    from services.rates_service import update_all_rates
    try:
        rates = update_all_rates(modo='AUTO')
        return jsonify({
            'success': True,
            'mensaje': 'Tasas sincronizadas en vivo correctamente',
            'tasas': rates
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error al sincronizar tasas: {str(e)}'}), 500

@cuadre_personal_bp.route('/api/tasas/manual', methods=['POST'])
def guardar_tasas_manuales_api():
    """Guarda modificaciones manuales de las tasas de cambio."""
    from services.rates_service import update_all_rates, set_tasa_preferida_bs
    data = request.get_json() or {}
    t_bcv = data.get('tasa_bcv')
    t_euro = data.get('tasa_bcv_euro')
    t_usdt = data.get('tasa_usdt')
    pref = data.get('tasa_preferida_bs')
    if pref:
        set_tasa_preferida_bs(pref)

    try:
        rates = update_all_rates(manual_bcv=t_bcv, manual_euro=t_euro, manual_usdt=t_usdt, modo='MANUAL')
        return jsonify({
            'success': True,
            'mensaje': 'Tasas de cambio actualizadas manualmente con éxito',
            'tasas': rates
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error al guardar tasas manuales: {str(e)}'}), 500

