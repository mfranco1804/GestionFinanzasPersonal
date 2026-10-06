"""
database.py — Módulo de Base de Datos SQLite para Gestión Financiera Personal.
Provee conexión con WAL mode, row_factory y migraciones automáticas.
"""
import os
import sqlite3
import json
from flask import g
import sys

# Si la aplicación está compilada con PyInstaller, el directorio base debe ser
# la carpeta permanente donde reside el .exe, para que la base de datos NUNCA se borre ni se cree en _MEIPASS.
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(BASE_DIR, 'finanzas_personales.db')

def get_db():
    """Retorna la conexión a la base de datos dentro del contexto de Flask."""
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode = WAL")
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

def close_connection(e=None):
    """Cierra la conexión al finalizar la petición."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def get_cached_config():
    """Obtiene la configuración general de la aplicación."""
    try:
        db = get_db()
        row = db.execute("SELECT * FROM app_config WHERE id = 1").fetchone()
        if row:
            cfg = dict(row)
            try:
                cfg['cuentas_bancarias'] = json.loads(cfg.get('cuentas_bancarias_json') or '[]')
            except Exception:
                cfg['cuentas_bancarias'] = []
            try:
                cfg['categorias_gastos'] = json.loads(cfg.get('categorias_gastos_json') or '[]')
            except Exception:
                cfg['categorias_gastos'] = []
            try:
                cfg['fuentes_ingresos'] = json.loads(cfg.get('fuentes_ingresos_json') or '[]')
            except Exception:
                cfg['fuentes_ingresos'] = []
            return cfg
    except Exception:
        pass
    return {
        'nombre_app': 'Gestión Financiera Personal',
        'usuario_nombre': 'Miguel',
        'moneda_principal': 'USD',
        'tasa_bcv_default': 1.0,
        'cuentas_bancarias': [
            {'id': 'banesco', 'nombre': 'Banesco', 'saldo': 0.0},
            {'id': 'venezuela', 'nombre': 'Banco de Venezuela', 'saldo': 0.0},
            {'id': 'mercantil', 'nombre': 'Mercantil', 'saldo': 0.0}
        ],
        'categorias_gastos': [
            "Alimentación y Supermercado", "Servicios Básicos (Luz/Agua/Net)",
            "Vivienda y Alquiler", "Transporte y Gasolina", "Salud y Medicinas",
            "Educación y Desarrollo", "Entretenimiento y Ocio", "Mantenimiento / Hogar",
            "Gastos Personales", "Otros Gastos"
        ],
        'fuentes_ingresos': [
            "Sueldo / Salario Fijo", "Honorarios Profesionales", "Freelance / Proyectos",
            "Inversiones / Rendimientos", "Remesas / Familia", "Entrada Extraordinaria"
        ]
    }

def init_db():
    """Inicializa el esquema de la base de datos si no existe."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA foreign_keys = ON")

    # Tabla de Configuración de la Aplicación
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS app_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            nombre_app TEXT DEFAULT 'Gestión Financiera Personal',
            usuario_nombre TEXT DEFAULT 'Miguel',
            moneda_principal TEXT DEFAULT 'USD',
            tasa_bcv_default REAL DEFAULT 1.0,
            cuentas_bancarias_json TEXT DEFAULT '[{"id": "banesco", "nombre": "Banesco", "saldo": 0.0}, {"id": "venezuela", "nombre": "Banco de Venezuela", "saldo": 0.0}, {"id": "mercantil", "nombre": "Mercantil", "saldo": 0.0}]',
            categorias_gastos_json TEXT DEFAULT '["Alimentación y Supermercado", "Servicios Básicos (Luz/Agua/Net)", "Vivienda y Alquiler", "Transporte y Gasolina", "Salud y Medicinas", "Educación y Desarrollo", "Entretenimiento y Ocio", "Mantenimiento / Hogar", "Gastos Personales", "Otros Gastos"]',
            fuentes_ingresos_json TEXT DEFAULT '["Sueldo / Salario Fijo", "Honorarios Profesionales", "Freelance / Proyectos", "Inversiones / Rendimientos", "Remesas / Familia", "Entrada Extraordinaria"]'
        )
    ''')

    # Migración de columnas de tasas si no existen
    cursor.execute("PRAGMA table_info(app_config)")
    cfg_cols = [c[1] for c in cursor.fetchall()]
    for col_def, col_name in [
        ('tasa_bcv REAL DEFAULT 1.0', 'tasa_bcv'),
        ('tasa_bcv_euro REAL DEFAULT 1.0', 'tasa_bcv_euro'),
        ('tasa_usdt REAL DEFAULT 1.0', 'tasa_usdt'),
        ('tasas_updated_at TEXT DEFAULT \'\'', 'tasas_updated_at'),
        ('tasas_modo TEXT DEFAULT \'AUTO\'', 'tasas_modo'),
        ('tasa_preferida_bs TEXT DEFAULT \'BCV\'', 'tasa_preferida_bs')
    ]:
        if col_name not in cfg_cols:
            cursor.execute(f"ALTER TABLE app_config ADD COLUMN {col_def}")

    cursor.execute('''
        INSERT OR IGNORE INTO app_config (id, nombre_app, usuario_nombre)
        VALUES (1, 'Gestión Financiera Personal', 'Miguel')
    ''')

    # Tabla de Historial de Tasas de Cambio
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historial_tasas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tasa_bcv REAL NOT NULL,
            tasa_bcv_euro REAL NOT NULL,
            tasa_usdt REAL NOT NULL,
            origen TEXT DEFAULT 'AUTO',
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_historial_tasas_fecha ON historial_tasas(fecha)')

    # Tabla de Ingresos Personales Dinámicos (Registro transaccional por Pote)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS finanzas_ingresos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes TEXT NOT NULL,
            semana INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            concepto TEXT NOT NULL,
            fuente TEXT DEFAULT 'Sueldo / Salario Fijo',
            moneda TEXT NOT NULL,
            monto_original REAL DEFAULT 0.0,
            tasa REAL DEFAULT 1.0,
            monto_usd REAL DEFAULT 0.0,
            referencia TEXT DEFAULT '',
            nota TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ingresos_mes ON finanzas_ingresos(mes)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ingresos_fecha ON finanzas_ingresos(fecha)')

    # Tabla de Ingresos Semanales Matriz
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS finanzas_ingresos_semanales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes TEXT NOT NULL,
            semana INTEGER NOT NULL,
            dia_indice INTEGER NOT NULL,
            dia_nombre TEXT NOT NULL,
            fecha TEXT DEFAULT '',
            fuente TEXT DEFAULT 'Sueldo / Salario Fijo',
            usd_efectivo REAL DEFAULT 0.0,
            usdt_binance REAL DEFAULT 0.0,
            tasa REAL DEFAULT 1.0,
            bs REAL DEFAULT 0.0,
            bs_a_usd REAL DEFAULT 0.0,
            total_usd REAL DEFAULT 0.0,
            modificado_manual INTEGER DEFAULT 0,
            UNIQUE(mes, semana, dia_indice)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ing_sem_mes ON finanzas_ingresos_semanales(mes)')

    # Tabla de Gastos Personales (Idéntica a APH pero adaptada a finanzas personales)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS finanzas_gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes TEXT NOT NULL,
            semana INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            categoria TEXT DEFAULT 'Alimentación y Supermercado',
            moneda TEXT NOT NULL,
            monto_original REAL DEFAULT 0.0,
            tasa REAL DEFAULT 1.0,
            monto_usd REAL DEFAULT 0.0,
            referencia TEXT DEFAULT ''
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_gastos_mes ON finanzas_gastos(mes)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_gastos_fecha ON finanzas_gastos(fecha)')

    # Tabla de Cambios Internos entre Potes (Arbitraje / Transferencias)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS finanzas_cambios_internos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes TEXT NOT NULL,
            fecha TEXT NOT NULL,
            pote_origen TEXT NOT NULL,
            monto_origen REAL NOT NULL,
            pote_destino TEXT NOT NULL,
            monto_destino REAL NOT NULL,
            tasa REAL DEFAULT 1.0,
            nota TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cambios_mes ON finanzas_cambios_internos(mes)')

    # Tabla de Inyecciones de Capital / Aportes Externos (Extraordinarios)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS finanzas_inyecciones_capital (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes TEXT NOT NULL,
            fecha TEXT NOT NULL,
            tipo TEXT DEFAULT 'APORTE',
            pote_destino TEXT NOT NULL,
            monto REAL NOT NULL,
            tasa REAL DEFAULT 1.0,
            monto_usd REAL NOT NULL,
            nota TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_inyecciones_mes ON finanzas_inyecciones_capital(mes)')

    # Tabla de Fondo de Ahorros y Metas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS finanzas_ahorros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes TEXT NOT NULL,
            fecha TEXT NOT NULL,
            tipo TEXT DEFAULT 'APORTE',
            concepto TEXT DEFAULT '',
            monto_usd REAL DEFAULT 0.0,
            monto_200 REAL DEFAULT 0.0,
            monto_50 REAL DEFAULT 0.0,
            total REAL DEFAULT 0.0,
            referencia TEXT DEFAULT '',
            saldo_acumulado REAL DEFAULT 0.0
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ahorros_mes ON finanzas_ahorros(mes)')

    # Tabla de Balance Mensual y Arqueo (Cuadre Ganancias vs Pérdidas / Patrimonio)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS finanzas_mes_balance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes TEXT UNIQUE NOT NULL,
            saldo_inicio_efectivo REAL DEFAULT 0.0,
            efectivo_en_mano REAL DEFAULT 0.0,
            saldo_bcv REAL DEFAULT 1.0,
            bancos_json TEXT DEFAULT '{}',
            ahorro_saldo_inicial REAL DEFAULT NULL,
            meta_ahorro_usd REAL DEFAULT 500.0,
            notas TEXT DEFAULT ''
        )
    ''')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_balance_mes ON finanzas_mes_balance(mes)')

    # Tabla de Configuración de WhatsApp
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS finanzas_whatsapp_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            grupo_nombre TEXT DEFAULT 'Finanzas Personales',
            enlace_grupo TEXT DEFAULT '',
            ultima_sincronizacion TEXT DEFAULT '',
            estado TEXT DEFAULT 'DESCONECTADO'
        )
    ''')
    cursor.execute('''
        INSERT OR IGNORE INTO finanzas_whatsapp_config (id, grupo_nombre)
        VALUES (1, 'Finanzas Personales')
    ''')

    # Tabla de Bandeja de Entrada (Inbox) de WhatsApp para Ingresos, Gastos y Cambios
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS finanzas_whatsapp_inbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mensaje_hash TEXT UNIQUE NOT NULL,
            fecha_mensaje TEXT NOT NULL,
            fecha TEXT NOT NULL,
            mes TEXT NOT NULL,
            semana INTEGER DEFAULT 1,
            remitente TEXT NOT NULL,
            texto_original TEXT NOT NULL,
            tipo_movimiento TEXT NOT NULL,
            pote TEXT DEFAULT 'EFECTIVO',
            monto_original REAL DEFAULT 0.0,
            tasa REAL DEFAULT 1.0,
            monto_usd REAL DEFAULT 0.0,
            concepto TEXT DEFAULT '',
            categoria_fuente TEXT DEFAULT '',
            pote_origen TEXT DEFAULT '',
            monto_origen REAL DEFAULT 0.0,
            pote_destino TEXT DEFAULT '',
            monto_destino REAL DEFAULT 0.0,
            dudoso INTEGER DEFAULT 0,
            estado TEXT DEFAULT 'PENDIENTE',
            registro_id INTEGER DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_wa_inbox_mes ON finanzas_whatsapp_inbox(mes)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_wa_inbox_estado ON finanzas_whatsapp_inbox(estado)')

    # Tabla de Configuración de Telegram Bot
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS finanzas_telegram_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            bot_token TEXT DEFAULT '',
            bot_username TEXT DEFAULT '',
            chat_id_autorizado TEXT DEFAULT '',
            modo_guardado TEXT DEFAULT 'DIRECTO',
            activo INTEGER DEFAULT 0,
            ultimo_update_id INTEGER DEFAULT 0,
            ultima_actividad TEXT DEFAULT ''
        )
    ''')
    cursor.execute('''
        INSERT OR IGNORE INTO finanzas_telegram_config (id, modo_guardado)
        VALUES (1, 'DIRECTO')
    ''')

    # Tabla de Proyección y Pronóstico Financiero (Gastos Fijos vs Entradas Fijas)
    # Totalmente desacoplada del cuadre transaccional mensual
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS finanzas_proyeccion_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            concepto TEXT NOT NULL,
            categoria TEXT NOT NULL,
            frecuencia TEXT NOT NULL DEFAULT 'MENSUAL',
            moneda TEXT NOT NULL DEFAULT 'USD',
            monto_original REAL NOT NULL DEFAULT 0.0,
            tasa REAL NOT NULL DEFAULT 1.0,
            monto_mensual_usd REAL NOT NULL DEFAULT 0.0,
            monto_anual_usd REAL NOT NULL DEFAULT 0.0,
            activo INTEGER NOT NULL DEFAULT 1,
            dia_pago INTEGER DEFAULT NULL,
            notas TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_proyeccion_tipo ON finanzas_proyeccion_items(tipo)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_proyeccion_activo ON finanzas_proyeccion_items(activo)')

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Base de datos inicializada correctamente en:", DB_PATH)
