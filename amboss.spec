# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Spec-Datei fuer Amboss
==============================================

Kompilierung:
    pyinstaller amboss.spec
"""

block_cipher = None

# qfluentwidgets bundles its own icons/qss as a compiled Qt resource module
# (qfluentwidgets/_rc/resource.py), so no extra `datas` collection is needed -
# PyInstaller's normal import analysis picks that up like any other .py file.
# Its Mica/Acrylic effects and Theme.AUTO detection do pull in PIL/numpy/scipy
# and the win32/qframelesswindow frameless-window backend, so those must NOT
# be excluded (unlike the old single-file app, which never used them).
a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('icon.ico', '.'), ('logo.png', '.')],
    hiddenimports=[
        'PyQt5',
        'PyQt5.QtCore',
        'PyQt5.QtWidgets',
        'PyQt5.QtGui',
        'PyQt5.sip',
        'qfluentwidgets',
        'qframelesswindow',
        'darkdetect',
        'colorthief',
        'win32gui',
        'win32con',
        'win32api',
        'win32print',
        'win32com',
        'win32comext',
        'pywintypes',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'pandas',
        'cv2',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Amboss',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI-Anwendung ohne Konsolenfenster
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
    version='version_info.txt',
)
