"""
utils/whatsapp_parser.py — Parser inteligente de mensajes de WhatsApp
para Finanzas Personales. Clasifica automáticamente en:
1. GASTOS (Egresos)
2. INGRESOS (Entradas)
3. CAMBIOS ENTRE POTES (Transferencias / Arbitraje)

Soporta palabras con y sin acentos de forma idéntica mediante normalización NFKD.
"""
import re
import hashlib
import unicodedata
from datetime import datetime
from typing import Dict, Any, List

def quitar_acentos(texto: str) -> str:
    """
    Elimina acentos y tildes conservando letras base.
    Ej: 'cobré' -> 'cobre', 'nómina' -> 'nomina', 'cambié' -> 'cambie', 'día' -> 'dia'.
    """
    if not texto:
        return ""
    texto_norm = unicodedata.normalize('NFD', texto)
    return ''.join(c for c in texto_norm if unicodedata.category(c) != 'Mn').lower()

def calcular_hash_mensaje(fecha_hora_str: str, remitente: str, texto: str) -> str:
    """Genera una firma SHA-256 única para evitar registros duplicados."""
    base = f"{fecha_hora_str.strip()}|{remitente.strip().lower()}|{texto.strip()}".encode('utf-8')
    return hashlib.sha256(base).hexdigest()

def normalizar_numero(val_str: str) -> float:
    """
    Normaliza representaciones numéricas comunes en Venezuela/LATAM:
    '80.000', '80,000.50', '80.000,50', '80000.00', etc.
    """
    if not val_str:
        return 0.0
    s = val_str.strip()
    if '.' in s and ',' in s:
        if s.rfind(',') > s.rfind('.'):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    elif ',' in s:
        partes = s.split(',')
        if len(partes) == 2 and len(partes[1]) == 3 and '.' not in s:
            s = s.replace(',', '')
        else:
            s = s.replace(',', '.')
    elif '.' in s:
        partes = s.split('.')
        if len(partes) == 2 and len(partes[1]) == 3 and len(partes[0]) <= 3:
            s = s.replace('.', '')
    try:
        return round(float(s), 2)
    except ValueError:
        return 0.0

def limpiar_concepto(texto: str, remitente: str = '') -> str:
    """Limpia palabras sueltas, conectores y formatea el concepto contable."""
    c = re.sub(r'[\r\n\t]+', ' ', texto)
    c = re.sub(r'^[,\s\-:;+>]+|[,\s\-:;+>]+$', '', c).strip()
    c = re.sub(r'\s{2,}', ' ', c)
    if not c:
        c = "Movimiento registrado"
    c = c[0].upper() + c[1:] if len(c) > 1 else c.upper()
    return c

def clasificar_categoria_gasto(concepto_norm: str) -> str:
    """Sugiere una categoría de gasto personal basada en palabras clave sin acento."""
    if any(k in concepto_norm for k in ['gasolina', 'combustible', 'gasoil', 'estacionamiento', 'parqueo', 'peaje', 'taxi', 'ridery', 'yummy', 'uber', 'transporte', 'pasaje', 'moto', 'flete', 'aceite carro']):
        return 'Transporte y Gasolina'
    if any(k in concepto_norm for k in ['almuerzo', 'comida', 'desayuno', 'cena', 'mercado', 'supermercado', 'viveres', 'panaderia', 'cafe', 'agua', 'hielo', 'carne', 'pollo', 'queso', 'restaurante', 'dulce', 'merienda']):
        return 'Alimentación y Supermercado'
    if any(k in concepto_norm for k in ['luz', 'electricidad', 'agua potable', 'internet', 'fibra', 'cantv', 'netuno', 'inter', 'recarga', 'digitel', 'movistar', 'movilnet', 'condominio', 'bombona']) or re.search(r'\bgas\b', concepto_norm):
        return 'Servicios Básicos (Luz/Agua/Net)'
    if any(k in concepto_norm for k in ['alquiler', 'arriendo', 'casa', 'apartamento', 'cuota casa']):
        return 'Vivienda y Alquiler'
    if any(k in concepto_norm for k in ['farmacia', 'medicina', 'medicamento', 'pastilla', 'medico', 'consulta', 'laboratorio', 'examen', 'dentista', 'odontologo', 'clinica']):
        return 'Salud y Medicinas'
    if any(k in concepto_norm for k in ['curso', 'libro', 'estudio', 'universidad', 'colegio', 'taller', 'capacitacion']):
        return 'Educación y Desarrollo'
    if any(k in concepto_norm for k in ['cine', 'salida', 'paseo', 'viaje', 'cerveza', 'tragos', 'discoteca', 'concierto', 'videojuego', 'suscripcion', 'netflix', 'spotify']):
        return 'Entretenimiento y Ocio'
    if any(k in concepto_norm for k in ['reparacion', 'bombillo', 'plomero', 'pintura', 'herramienta', 'ferreteria', 'limpieza', 'cloro', 'jabon', 'detergente', 'jardin']):
        return 'Mantenimiento / Hogar'
    if any(k in concepto_norm for k in ['peluqueria', 'barberia', 'corte', 'ropa', 'zapatos', 'estetica', 'gym', 'gimnasio']):
        return 'Gastos Personales'
    return 'Otros Gastos'

def clasificar_fuente_ingreso(concepto_norm: str) -> str:
    """Sugiere una fuente de ingreso basada en palabras clave sin acento."""
    if any(k in concepto_norm for k in ['sueldo', 'salario', 'quincena', 'nomina', 'mensualidad', 'pago fijo']):
        return 'Sueldo / Salario Fijo'
    if any(k in concepto_norm for k in ['honorario', 'asesoria', 'consultoria', 'servicio prestado']):
        return 'Honorarios Profesionales'
    if any(k in concepto_norm for k in ['freelance', 'proyecto', 'cliente', 'web', 'programacion', 'diseno', 'landing', 'comision']):
        return 'Freelance / Proyectos'
    if any(k in concepto_norm for k in ['interes', 'dividendo', 'rendimiento', 'inversion', 'ganancia cripto', 'staking', 'trading']):
        return 'Inversiones / Rendimientos'
    if any(k in concepto_norm for k in ['remesa', 'familia', 'mama', 'papa', 'hermano', 'ayuda']):
        return 'Remesas / Familia'
    return 'Entrada Extraordinaria'

PATRON_MONTO_MONEDA = re.compile(
    r'(?:'
    # 1. Moneda ANTES del monto: $100, Bs 13000, usdt50, ustd50, etc.
    r'(?P<pre_curr>usdt|ustd|binance|bs\.?|bolivares|bolivar|bsf|bsd|\$|usd|dolares|dolar|efectivo)\s*(?P<monto1>\d+(?:[.,]\d+)?)'
    r'|'
    # 2. Moneda DESPUÉS del monto: 13000Bs, 13000 bs, 50usdt, 50ustd, 100$, 25usd, etc.
    r'(?P<monto2>\d+(?:[.,]\d+)?)\s*(?P<post_curr>usdt|ustd|binance|bs\.?|bolivares|bolivar|bsf|bsd|\$|usd|dolares|dolar|efectivo)'
    r'|'
    # 3. Solo número sin moneda explícita: 13000, 25.50
    r'(?P<monto_solo>\d+(?:[.,]\d+)?)'
    r')', re.IGNORECASE
)

def extraer_monto_y_moneda(texto: str, texto_norm: str):
    """
    Extrae con precisión el monto numérico, la moneda/pote detectada
    y remueve el fragmento monetario del texto para obtener el concepto limpio.
    Si no hay referencia de moneda, retorna moneda='SIN_DEFINIR' y dudoso=1.
    """
    m = PATRON_MONTO_MONEDA.search(texto)
    if not m:
        return 0.0, 'SIN_DEFINIR', texto, 1

    c_raw = (m.group('pre_curr') or m.group('post_curr') or '').strip().lower()
    val_str = m.group('monto1') or m.group('monto2') or m.group('monto_solo')
    monto = normalizar_numero(val_str)

    dudoso = 0
    if c_raw in ['bs', 'bs.', 'bolivares', 'bolivar', 'bsf', 'bsd']:
        moneda = 'BOLIVARES'
    elif c_raw in ['usdt', 'ustd', 'binance', 'cripto', 'crypto']:
        moneda = 'BINANCE'
    elif c_raw in ['$', 'usd', 'dolares', 'dolar', 'efectivo', 'cash']:
        moneda = 'EFECTIVO'
    else:
        # No tiene moneda adherida directamente al número. Buscar pistas en el resto del texto
        if any(k in texto_norm for k in ['pago movil', 'pagomovil', 'bcv', 'bolivares', 'bolivar', 'bs']):
            moneda = 'BOLIVARES'
        elif any(k in texto_norm for k in ['usdt', 'ustd', 'binance', 'cripto', 'crypto']):
            moneda = 'BINANCE'
        elif any(k in texto_norm for k in ['dolares', 'dolar', 'efectivo', 'cash', '$', 'usd']):
            moneda = 'EFECTIVO'
        else:
            # ¡SIN REFERENCIA MONETARIA! Dejar en SIN_DEFINIR para que el usuario confirme antes de migrar
            moneda = 'SIN_DEFINIR'
            dudoso = 1

    # Remover el token del monto para obtener el concepto limpio
    span = m.span()
    concepto_resto = texto[:span[0]] + ' ' + texto[span[1]:]
    concepto_resto = re.sub(
        r'\b(pago movil|pagomovil|bcv|pague|compre|gaste|gasto|ingreso|cobre|entro|recibi|me pagaron)\b|\$|\b(usdt|ustd|binance|bs|bolivares|usd|dolares)\b',
        '', concepto_resto, flags=re.IGNORECASE
    )
    return monto, moneda, concepto_resto, dudoso

def parsear_mensaje_whatsapp(texto: str, remitente: str = '', tasa_referencial: float = 1.0) -> Dict[str, Any]:
    """
    Analiza un mensaje y determina si es GASTO, INGRESO o CAMBIO INTERNO.
    Retorna diccionario normalizado para la bandeja de WhatsApp.
    """
    texto_raw = (texto or '').strip()
    texto_norm = quitar_acentos(texto_raw)
    
    res = {
        'es_valido': False,
        'tipo_movimiento': 'IGNORAR',
        'remitente': remitente.strip() or 'Desconocido',
        'texto_original': texto_raw,
        'moneda': 'EFECTIVO',
        'monto_original': 0.0,
        'tasa': tasa_referencial if tasa_referencial > 0 else 1.0,
        'monto_usd': 0.0,
        'concepto': '',
        'categoria_fuente': '',
        'pote_origen': '',
        'monto_origen': 0.0,
        'pote_destino': '',
        'monto_destino': 0.0,
        'dudoso': 0
    }

    if not texto_raw:
        return res

    # -------------------------------------------------------------------------
    # 0. DETECCIÓN PREVIA DE TASA DE CAMBIO EXPLÍCITA
    # Ej: "tasa 980", "a 975.5", "@ 980", "tasa: 980"
    # -------------------------------------------------------------------------
    patron_tasa = re.search(r'\b(?:tasa[:\s]*|a\s+|@\s*)(\d{2,6}(?:[.,]\d{1,4})?)', texto_raw, re.IGNORECASE)
    tasa_detectada = None
    texto_sin_tasa = texto_raw
    if patron_tasa:
        posible_tasa = normalizar_numero(patron_tasa.group(1))
        if posible_tasa >= 10:  # En Venezuela las tasas cambiarias son > 10
            tasa_detectada = posible_tasa
            res['tasa'] = tasa_detectada
            # Eliminar la tasa del texto analizado para no confundir con montos
            texto_sin_tasa = texto_raw[:patron_tasa.start()] + ' ' + texto_raw[patron_tasa.end():]
    
    texto_sin_tasa_norm = quitar_acentos(texto_sin_tasa)

    # -------------------------------------------------------------------------
    # 1. ¿ES UN CAMBIO INTERNO / ARBITRAJE? (Máxima Prioridad)
    # Detecta transferencias entre potes:
    # Ej: "cambie 50 usdt a bs tasa 975", "vendi 20$ a bs a 870", "50 usdt -> bs",
    #     "pase 100$ a binance", "compre 30 usdt con 30$ efectivo"
    # -------------------------------------------------------------------------
    es_cambio = False
    p_cambio = re.search(r'\b(cambi[eo]|vendi|compre|pase|transferi|traspas[eo]|traspaso)\b|->|=>|\ba\s+(bs|bolivares|usdt|binance|dolar|dolares|efectivo)\b', texto_sin_tasa_norm)
    
    # También si menciona dos monedas distintas (ej: "usdt" y "bs", o "$" y "binance")
    tiene_usdt = bool(re.search(r'\b(usdt|binance)\b', texto_sin_tasa_norm))
    tiene_bs = bool(re.search(r'\b(bs|bolivar|bolivares|bsf|bsd)\b', texto_sin_tasa_norm))
    tiene_dolar = bool(re.search(r'\$|\b(usd|dolar|dolares|efectivo)\b', texto_sin_tasa_norm))
    
    monedas_presentes = sum([tiene_usdt, tiene_bs, tiene_dolar])
    if p_cambio or monedas_presentes >= 2:
        # Extraer montos
        numeros = re.findall(r'\b\d+(?:[.,]\d+)?\b', texto_sin_tasa)
        if numeros:
            monto_1 = normalizar_numero(numeros[0])
            monto_2 = normalizar_numero(numeros[1]) if len(numeros) > 1 else 0.0

            # Determinar sentido de la transferencia
            # Caso 1: USDT -> BS (muy común)
            if (tiene_usdt and tiene_bs) or ('usdt a bs' in texto_sin_tasa_norm) or ('binance a bs' in texto_sin_tasa_norm) or ('vendi usdt' in texto_sin_tasa_norm):
                res['tipo_movimiento'] = 'CAMBIO'
                res['pote_origen'] = 'BINANCE'
                res['pote_destino'] = 'BOLIVARES'
                res['monto_origen'] = monto_1
                t = tasa_detectada or tasa_referencial
                res['tasa'] = t
                res['monto_destino'] = monto_2 if monto_2 > monto_1 else round(monto_1 * t, 2)
                res['concepto'] = "Venta USDT a Bolívares"
                res['es_valido'] = True
                return res

            # Caso 2: EFECTIVO ($) -> BS
            if (tiene_dolar and tiene_bs) or ('$ a bs' in texto_sin_tasa_norm) or ('dolar a bs' in texto_sin_tasa_norm) or ('efectivo a bs' in texto_sin_tasa_norm) or ('vendi dolares' in texto_sin_tasa_norm):
                res['tipo_movimiento'] = 'CAMBIO'
                res['pote_origen'] = 'EFECTIVO'
                res['pote_destino'] = 'BOLIVARES'
                res['monto_origen'] = monto_1
                t = tasa_detectada or tasa_referencial
                res['tasa'] = t
                res['monto_destino'] = monto_2 if monto_2 > monto_1 else round(monto_1 * t, 2)
                res['concepto'] = "Cambio Efectivo a Bolívares"
                res['es_valido'] = True
                return res

            # Caso 3: EFECTIVO ($) -> BINANCE (USDT)
            if (tiene_dolar and tiene_usdt) and ('a binance' in texto_sin_tasa_norm or 'a usdt' in texto_sin_tasa_norm or 'compre usdt' in texto_sin_tasa_norm):
                res['tipo_movimiento'] = 'CAMBIO'
                res['pote_origen'] = 'EFECTIVO'
                res['pote_destino'] = 'BINANCE'
                res['monto_origen'] = monto_1
                res['monto_destino'] = monto_2 or monto_1
                res['tasa'] = 1.0
                res['concepto'] = "Depósito / Compra USDT con Efectivo"
                res['es_valido'] = True
                return res

            # Caso 4: BINANCE (USDT) -> EFECTIVO ($)
            if (tiene_dolar and tiene_usdt) and ('a efectivo' in texto_sin_tasa_norm or 'a dolares' in texto_sin_tasa_norm or 'retiro usdt' in texto_sin_tasa_norm):
                res['tipo_movimiento'] = 'CAMBIO'
                res['pote_origen'] = 'BINANCE'
                res['pote_destino'] = 'EFECTIVO'
                res['monto_origen'] = monto_1
                res['monto_destino'] = monto_2 or monto_1
                res['tasa'] = 1.0
                res['concepto'] = "Retiro Binance a Efectivo"
                res['es_valido'] = True
                return res

            # Caso 5: BS -> BINANCE (USDT)
            if (tiene_bs and tiene_usdt) and ('bs a usdt' in texto_sin_tasa_norm or 'compre usdt' in texto_sin_tasa_norm):
                res['tipo_movimiento'] = 'CAMBIO'
                res['pote_origen'] = 'BOLIVARES'
                res['pote_destino'] = 'BINANCE'
                res['monto_origen'] = monto_1
                t = tasa_detectada or tasa_referencial
                res['tasa'] = t
                res['monto_destino'] = monto_2 if (0 < monto_2 < monto_1) else (round(monto_1 / t, 2) if t > 0 else 0.0)
                res['concepto'] = "Compra USDT con Bolívares"
                res['es_valido'] = True
                return res

    # -------------------------------------------------------------------------
    # 2. ¿ES UN INGRESO? (Segunda Prioridad)
    # Detecta entradas:
    # Ej: "+300$ sueldo", "cobre 150 usdt freelance", "entro 5000 bs asesoria",
    #     "ingreso 80$ regalo", "me pagaron quincena 400$"
    # -------------------------------------------------------------------------
    palabras_ingreso = [
        'cobre', 'ingreso', 'entro', 'sueldo', 'salario', 'quincena', 
        'nomina', 'recibi', 'me pagaron', 'honorario', 'honorarios', 
        'freelance', 'abono', 'deposito'
    ]
    empieza_con_mas = texto_sin_tasa_norm.startswith('+')
    tiene_palabra_ingreso = any(re.search(rf'\b{p}\b', texto_sin_tasa_norm) for p in palabras_ingreso)

    if empieza_con_mas or tiene_palabra_ingreso:
        monto, moneda, concepto_resto, dudoso = extraer_monto_y_moneda(texto_sin_tasa, texto_sin_tasa_norm)
        if monto > 0:
            res['es_valido'] = True
            res['tipo_movimiento'] = 'INGRESO'
            res['moneda'] = moneda
            res['monto_original'] = monto
            res['dudoso'] = dudoso
            t = res['tasa'] if res['tasa'] > 0 else 1.0
            if moneda == 'BOLIVARES':
                res['monto_usd'] = round(monto / t, 2) if t > 0 else 0.0
            elif moneda in ('EFECTIVO', 'BINANCE'):
                res['monto_usd'] = monto
            else:
                res['monto_usd'] = 0.0

            concepto_limpio = limpiar_concepto(concepto_resto, remitente)
            if not concepto_limpio or concepto_limpio == "Movimiento registrado":
                concepto_limpio = "Ingreso personal"
            res['concepto'] = concepto_limpio
            res['categoria_fuente'] = clasificar_fuente_ingreso(texto_sin_tasa_norm)
            return res

    # -------------------------------------------------------------------------
    # 3. ¿ES UN GASTO? (Comportamiento Estándar para Salidas)
    # Detecta:
    # Ej: "Almuerzo 12$", "Gasolina 450 bs", "45 usdt supermercado", "-20 farmacia"
    # -------------------------------------------------------------------------
    monto, moneda, concepto_resto, dudoso = extraer_monto_y_moneda(texto_sin_tasa, texto_sin_tasa_norm)

    if monto > 0:
        # Descartar mensajes que sean solo saludos o texto no financiero
        palabras_significativas = [w for w in texto_sin_tasa_norm.split() if not w.isdigit() and len(w) > 2]
        if any(w in ['gracias', 'hola', 'buenas', 'saludos', 'listo'] for w in palabras_significativas) and len(palabras_significativas) <= 2 and dudoso:
            return res

        res['es_valido'] = True
        res['tipo_movimiento'] = 'GASTO'
        res['moneda'] = moneda
        res['monto_original'] = monto
        res['dudoso'] = dudoso
        t = res['tasa'] if res['tasa'] > 0 else 1.0
        if moneda == 'BOLIVARES':
            res['monto_usd'] = round(monto / t, 2) if t > 0 else 0.0
        elif moneda in ('EFECTIVO', 'BINANCE'):
            res['monto_usd'] = monto
        else:
            res['monto_usd'] = 0.0

        concepto_limpio = limpiar_concepto(concepto_resto, remitente)
        if not concepto_limpio or concepto_limpio == "Movimiento registrado":
            concepto_limpio = "Gasto personal"
        res['concepto'] = concepto_limpio
        res['categoria_fuente'] = clasificar_categoria_gasto(texto_sin_tasa_norm)
        return res

    return res

def parsear_chat_exportado_whatsapp(contenido_txt: str, tasa_referencial: float = 1.0) -> List[Dict[str, Any]]:
    """
    Parsea el contenido de un chat exportado de WhatsApp (.txt).
    Soporta formato Android ('DD/MM/AAAA, HH:MM - Nombre: Mensaje') 
    y formato iOS ('[DD/MM/AAAA, HH:MM:SS] Nombre: Mensaje').
    Descarta mensajes del sistema y clasifica cada fila en Gasto, Ingreso o Cambio.
    """
    pattern = re.compile(
        r'^(?:\[?(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})[,\s]+(\d{1,2}:\d{2}(?::\d{2})?(?:\s*(?:[apAP]\.?\s*[mM]\.?))?)\]?\s*(?:-\s*)?)([^:]+):\s*(.+)$'
    )
    movimientos_detectados = []
    lineas = contenido_txt.splitlines()

    for linea in lineas:
        l = linea.strip()
        if not l:
            continue
        m = pattern.match(l)
        if not m:
            continue

        fecha_raw, hora_raw, remitente_raw, texto_raw = m.groups()
        
        # Ignorar mensajes de sistema de WhatsApp
        remitente_clean = remitente_raw.strip()
        if any(ign in remitente_clean.lower() for ign in ['whatsapp', 'seguridad', 'cambio el icono', 'cambio el asunto', 'anadio a', 'salio del grupo']):
            continue

        partes_f = re.split(r'[\/\-\.]', fecha_raw.strip())
        if len(partes_f) == 3:
            try:
                d, mes_num, y = int(partes_f[0]), int(partes_f[1]), int(partes_f[2])
                if y < 100:
                    y += 2000
                fecha_dt = datetime(y, mes_num, d)
            except Exception:
                fecha_dt = datetime.now()
        else:
            fecha_dt = datetime.now()

        parsed = parsear_mensaje_whatsapp(texto_raw, remitente_clean, tasa_referencial=tasa_referencial)
        if parsed.get("es_valido") and parsed.get("tipo_movimiento") != 'IGNORAR':
            fecha_hora_str = f"{fecha_dt.strftime('%Y-%m-%d')} {hora_raw.strip()}"
            parsed["fecha_mensaje"] = fecha_hora_str
            parsed["fecha"] = fecha_dt.strftime('%Y-%m-%d')
            parsed["mes"] = fecha_dt.strftime('%Y-%m')
            semana = ((fecha_dt.day - 1) // 7) + 1
            parsed["semana"] = min(semana, 5)
            parsed["hash"] = calcular_hash_mensaje(fecha_hora_str, parsed["remitente"], texto_raw)
            movimientos_detectados.append(parsed)

    return movimientos_detectados
