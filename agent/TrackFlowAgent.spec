# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['collector_windows.py'],
    pathex=[],
    binaries=[],
    datas=[('X:\\Varahe Analtics\\Productivity-Tracker-windows\\Productivity-Tracker\\backend\\.env', '.'), ('trackflow-context-0.0.1.vsix', '.'), ('X:\\Varahe Analtics\\Productivity-Tracker-windows\\Productivity-Tracker\\chrome-extension', 'chrome-extension')],
    hiddenimports=[],
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
    name='TrackFlowAgent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
