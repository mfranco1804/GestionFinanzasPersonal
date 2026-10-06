"""
services/rates_service.py — Servicio de Tasas de Cambio en Tiempo Real.
Obtiene automáticamente:
1. Tasa BCV Dólar Oficial (USD/VES)
2. Tasa BCV Euro Oficial (EUR/VES)
3. Tasa Binance P2P (USDT/VES)
Incluye fallbacks resilientes y almacenamiento en historial y app_config.
"""
import os
import sqlite3
import json
import ssl
import urllib.request
from datetime import datetime
from bs4 import BeautifulSoup
from database import DB_PATH

def scrape_bcv_rates():
    """
    Scrapea las tasas de cambio oficiales directamente del sitio web del Banco Central de Venezuela.
    Retorna: (tasa_dolar, tasa_euro) o (None, None)
    """
    dolar_val = None
    euro_val = None
    
    # 1. Intento primario: Web scraping a BCV oficial
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        url = "http://www.bcv.org.ve/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=12) as response:
            soup = BeautifulSoup(response.read(), 'html.parser')
            
            # Dólar BCV
            div_dolar = soup.find('div', id='dolar')
            if div_dolar:
                strong = div_dolar.find('strong')
                if strong:
                    raw = strong.get_text().strip().replace('.', '').replace(',', '.')
                    dolar_val = round(float(raw), 4)

            # Euro BCV
            div_euro = soup.find('div', id='euro')
            if div_euro:
                strong = div_euro.find('strong')
                if strong:
                    raw = strong.get_text().strip().replace('.', '').replace(',', '.')
                    euro_val = round(float(raw), 4)

    except Exception as e:
        print(f"[RATES WARNING] Falló scraping directo de BCV: {e}")

    # 2. Intento de respaldo (Fallback) vía API espejo si alguno no se obtuvo
    if not dolar_val or not euro_val:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            if not dolar_val:
                req_dolar = urllib.request.Request('https://ve.dolarapi.com/v1/dolares/oficial', headers=headers)
                with urllib.request.urlopen(req_dolar, timeout=6) as res:
                    data = json.loads(res.read().decode())
                    if data.get('promedio'):
                        dolar_val = round(float(data['promedio']), 4)
            if not euro_val:
                req_euro = urllib.request.Request('https://ve.dolarapi.com/v1/euros/oficial', headers=headers)
                with urllib.request.urlopen(req_euro, timeout=6) as res:
                    data = json.loads(res.read().decode())
                    if data.get('promedio'):
                        euro_val = round(float(data['promedio']), 4)
        except Exception as e:
            print(f"[RATES WARNING] Falló API de respaldo BCV: {e}")

    return dolar_val, euro_val


def fetch_binance_p2p_rates():
    """
    Obtiene la cotización real de USDT/VES desde el libro de órdenes P2P de Binance.
    Promedia los primeros 3 comerciantes verificados para mayor estabilidad.
    Retorna: tasa_usdt o None
    """
    try:
        url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "Accept": "*/*"
        }
        
        # 1. Comerciantes VENDIENDO USDT (usuarios compran)
        payload_sell = {
            "asset": "USDT", "fiat": "VES", "tradeType": "SELL",
            "rows": 5, "page": 1, "publisherType": "merchant", "payTypes": []
        }
        req_sell = urllib.request.Request(url, data=json.dumps(payload_sell).encode('utf-8'), headers=headers)
        sell_prices = []
        with urllib.request.urlopen(req_sell, timeout=8) as res:
            data = json.loads(res.read().decode())
            for item in data.get('data', []):
                try:
                    sell_prices.append(float(item['adv']['price']))
                except Exception:
                    pass

        # 2. Comerciantes COMPRANDO USDT (usuarios venden)
        payload_buy = {
            "asset": "USDT", "fiat": "VES", "tradeType": "BUY",
            "rows": 5, "page": 1, "publisherType": "merchant", "payTypes": []
        }
        req_buy = urllib.request.Request(url, data=json.dumps(payload_buy).encode('utf-8'), headers=headers)
        buy_prices = []
        with urllib.request.urlopen(req_buy, timeout=8) as res:
            data = json.loads(res.read().decode())
            for item in data.get('data', []):
                try:
                    buy_prices.append(float(item['adv']['price']))
                except Exception:
                    pass

        if sell_prices and buy_prices:
            avg_sell = sum(sell_prices[:3]) / len(sell_prices[:3])
            avg_buy = sum(buy_prices[:3]) / len(buy_prices[:3])
            tasa_usdt = round(max(avg_sell, avg_buy), 2)
            return tasa_usdt
        elif sell_prices:
            return round(sum(sell_prices[:3]) / len(sell_prices[:3]), 2)
        elif buy_prices:
            return round(sum(buy_prices[:3]) / len(buy_prices[:3]), 2)

    except Exception as e:
        print(f"[RATES WARNING] Falló Binance P2P directo: {e}")

    # Fallback a DolarAPI paralelo
    try:
        req = urllib.request.Request(
            'https://ve.dolarapi.com/v1/dolares/paralelo',
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=6) as res:
            data = json.loads(res.read().decode())
            if data.get('promedio'):
                return round(float(data['promedio']), 2)
    except Exception as e:
        print(f"[RATES ERROR] Fallback de USDT falló: {e}")

    return None


def get_current_rates():
    """Obtiene las tasas activas registradas en app_config."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cols = [c[1] for c in cursor.execute("PRAGMA table_info(app_config)").fetchall()]
    has_pref = 'tasa_preferida_bs' in cols
    query = "SELECT tasa_bcv, tasa_bcv_euro, tasa_usdt, tasas_updated_at, tasas_modo" + (", tasa_preferida_bs" if has_pref else "") + " FROM app_config WHERE id = 1"
    row = cursor.execute(query).fetchone()
    conn.close()
    if row:
        d = dict(row)
        if 'tasa_preferida_bs' not in d:
            d['tasa_preferida_bs'] = 'BCV'
        return d
    return {
        'tasa_bcv': 1.0,
        'tasa_bcv_euro': 1.0,
        'tasa_usdt': 1.0,
        'tasas_updated_at': '',
        'tasas_modo': 'AUTO',
        'tasa_preferida_bs': 'BCV'
    }


def set_tasa_preferida_bs(preferencia):
    """Guarda la preferencia de valuación para el Pote de Bolívares ('BCV', 'USDT', 'EURO')."""
    pref = (preferencia or 'BCV').strip().upper()
    if pref not in ('BCV', 'USDT', 'EURO'):
        pref = 'BCV'
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE app_config SET tasa_preferida_bs = ? WHERE id = 1", (pref,))
    conn.commit()
    conn.close()
    return pref


def update_all_rates(manual_bcv=None, manual_euro=None, manual_usdt=None, modo=None):
    """
    Actualiza las 3 tasas en app_config y en historial_tasas.
    Si se suministran valores manuales, se guardan como modo='MANUAL'.
    De lo contrario, se obtienen automáticamente de BCV y Binance.
    """
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    current = get_current_rates()
    
    nuevo_bcv = current.get('tasa_bcv', 1.0)
    nuevo_euro = current.get('tasa_bcv_euro', 1.0)
    nuevo_usdt = current.get('tasa_usdt', 1.0)
    origen = modo or ('MANUAL' if (manual_bcv or manual_euro or manual_usdt) else 'AUTO')

    if origen == 'MANUAL':
        if manual_bcv is not None and float(manual_bcv) > 0:
            nuevo_bcv = round(float(manual_bcv), 4)
        if manual_euro is not None and float(manual_euro) > 0:
            nuevo_euro = round(float(manual_euro), 4)
        if manual_usdt is not None and float(manual_usdt) > 0:
            nuevo_usdt = round(float(manual_usdt), 2)
    else:
        # Obtención automática
        dolar_bcv, euro_bcv = scrape_bcv_rates()
        usdt_binance = fetch_binance_p2p_rates()
        
        if dolar_bcv and dolar_bcv > 0:
            nuevo_bcv = dolar_bcv
        if euro_bcv and euro_bcv > 0:
            nuevo_euro = euro_bcv
        if usdt_binance and usdt_binance > 0:
            nuevo_usdt = usdt_binance

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE app_config 
        SET tasa_bcv = ?, tasa_bcv_euro = ?, tasa_usdt = ?, tasas_updated_at = ?, tasas_modo = ?
        WHERE id = 1
    ''', (nuevo_bcv, nuevo_euro, nuevo_usdt, now_str, origen))

    # Guardar en historial
    cursor.execute('''
        INSERT INTO historial_tasas (tasa_bcv, tasa_bcv_euro, tasa_usdt, origen, fecha)
        VALUES (?, ?, ?, ?, ?)
    ''', (nuevo_bcv, nuevo_euro, nuevo_usdt, origen, now_str))

    # También actualizar la tasa BCV del mes en curso si no tiene una personalizada
    mes_actual = datetime.now().strftime('%Y-%m')
    cursor.execute('''
        UPDATE finanzas_mes_balance 
        SET saldo_bcv = ? 
        WHERE mes = ? AND (saldo_bcv IS NULL OR saldo_bcv <= 1.0)
    ''', (nuevo_bcv, mes_actual))

    conn.commit()
    conn.close()

    return {
        'tasa_bcv': nuevo_bcv,
        'tasa_bcv_euro': nuevo_euro,
        'tasa_usdt': nuevo_usdt,
        'tasas_updated_at': now_str,
        'tasas_modo': origen
    }


def sincronizar_tasas_arrancada():
    """
    Obtiene las 3 tasas (BCV Dólar, BCV Euro, Binance USDT) UNA SOLA VEZ al arrancar la aplicación.
    NO programa tareas recurrentes, NO usa bucles ni timers, y NO verifica cada X tiempo.
    Las actualizaciones posteriores se realizan exclusivamente bajo demanda cuando el usuario
    presiona el botón 'Actualizar en vivo' o el botón 'Sincronizar'.
    """
    import threading
    import time
    def run_worker():
        time.sleep(0.5)  # Breve pausa para permitir que el servidor web inicialice
        try:
            r = update_all_rates(modo='AUTO')
            print(f"[RATES ARRANCADA] Tasas verificadas una única vez al inicio del sistema:")
            print(f"  - Dólar BCV:  {r.get('tasa_bcv')} Bs")
            print(f"  - Euro BCV:   {r.get('tasa_bcv_euro')} Bs")
            print(f"  - Binance:    {r.get('tasa_usdt')} Bs")
            print(f"  [AVISO] Verificación periódica desactivada. Solo se actualizarán bajo demanda con 'Actualizar en vivo' o 'Sincronizar'.")
        except Exception as e:
            print(f"[RATES ARRANCADA ERROR] No se pudieron sincronizar las tasas al inicio: {e}")

    worker_thread = threading.Thread(target=run_worker, daemon=True)
    worker_thread.start()

# Alias por compatibilidad
start_rates_scheduler = sincronizar_tasas_arrancada

