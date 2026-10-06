# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\Miguel F\\.gemini\\antigravity\\scratch\\App Gestion Personal\\instalador\\instalador.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\Miguel F\\.gemini\\antigravity\\scratch\\App Gestion Personal\\compilado\\AppGestionPersonal.exe', '.'), ('C:\\Users\\Miguel F\\.gemini\\antigravity\\scratch\\App Gestion Personal\\compilado\\finanzas_personales.db', '.'), ('C:\\Users\\Miguel F\\.gemini\\antigravity\\scratch\\App Gestion Personal\\icono.ico', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy', 'PIL', 'Pillow', 'pandas', 'scipy', 'matplotlib', 'torch', 'torchvision', 'flask', 'werkzeug', 'jinja2', 'waitress'],
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
    name='Instalar_AppGestionPersonal',
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
