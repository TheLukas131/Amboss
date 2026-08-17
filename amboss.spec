# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Spec-Datei fuer Amboss
==============================================

Kompilierung:
    pyinstaller amboss.spec
"""

import re
from pathlib import Path

block_cipher = None

# Die Versionsangabe in den Dateieigenschaften wird aus models.py erzeugt statt
# von Hand gepflegt. Von Hand gepflegt stand dort zuletzt 1.0.0, waehrend die
# Anwendung sich selbst als 1.2.2 bezeichnete - und ausgerechnet die Angabe,
# die Windows im Eigenschaften-Dialog zeigt, sieht man beim Entwickeln nie.
_quelle = Path("models.py").read_text(encoding="utf-8")
APP_VERSION = re.search(r'APP_VERSION = "([^"]+)"', _quelle).group(1)
_vierstellig = tuple(int(t) for t in (APP_VERSION.split(".") + ["0", "0", "0"])[:4])

Path("version_info.txt").write_text(f"""# UTF-8
#
# Erzeugt von amboss.spec aus models.APP_VERSION - nicht von Hand aendern.
#
# Erlaeuterung zu 'ffi':
# https://docs.microsoft.com/en-us/windows/win32/menurc/versioninfo-resource

VSVersionInfo(
    ffi=FixedFileInfo(
        filevers={_vierstellig},
        prodvers={_vierstellig},
        mask=0x3f,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0)
    ),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    u'040904B0',
                    [
                        StringStruct(u'CompanyName', u''),
                        StringStruct(u'FileDescription', u'Amboss - Videokonverter fuer AV1, H.265 und H.264 (NVENC)'),
                        StringStruct(u'FileVersion', u'{APP_VERSION}.0'),
                        StringStruct(u'InternalName', u'Amboss'),
                        StringStruct(u'LegalCopyright', u'GNU General Public License v3.0'),
                        StringStruct(u'OriginalFilename', u'Amboss.exe'),
                        StringStruct(u'ProductName', u'Amboss'),
                        StringStruct(u'ProductVersion', u'{APP_VERSION}.0')
                    ]
                )
            ]
        ),
        VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
    ]
)
""", encoding="utf-8")

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
    datas=[('icon.ico', '.'), ('logo.png', '.'), ('CHANGELOG.md', '.')],
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
