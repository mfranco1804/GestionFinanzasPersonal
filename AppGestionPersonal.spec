# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\Miguel F\\.gemini\\antigravity\\scratch\\App Gestion Personal\\app.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\Miguel F\\.gemini\\antigravity\\scratch\\App Gestion Personal\\templates', 'templates'), ('C:\\Users\\Miguel F\\.gemini\\antigravity\\scratch\\App Gestion Personal\\routes', 'routes'), ('C:\\Users\\Miguel F\\.gemini\\antigravity\\scratch\\App Gestion Personal\\services', 'services'), ('C:\\Users\\Miguel F\\.gemini\\antigravity\\scratch\\App Gestion Personal\\utils', 'utils')],
    hiddenimports=['waitress', 'sqlite3', 'certifi', 'updater', 'bs4', 'dotenv'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AppGestionPersonal',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,
    icon=['C:\\Users\\Miguel F\\.gemini\\antigravity\\scratch\\App Gestion Personal\\icono.ico'],
)
