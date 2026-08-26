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
# Der win32/qframelesswindow-Unterbau fuer den rahmenlosen Fensterrahmen muss
# dagegen ausdruecklich mit, ebenso darkdetect fuer Theme.AUTO.
#
# NICHT mit muessen scipy, numpy, PIL und colorthief. Sie haengen an genau einer
# Stelle: qfluentwidgets/common/image_utils.py, und die wird nur von
# acrylic_label.py gebraucht - fuer den Weichzeichner des Acryl-Effekts, den
# Amboss abschaltet (setMicaEffectEnabled(False), setAcrylicEnabled(False)).
#
# Die Bibliothek sieht den Verzicht selbst vor: acrylic_label faengt den Import
# mit try/except ImportError ab, setzt isAcrylicAvailable = False und liefert
# das Bild eben unscharf-los zurueck. Genau das ist der Unterschied zwischen
# `pip install PyQt-Fluent-Widgets` und `[full]`.
#
# Gemessen, was das kostete: 4,0 der 5,2 Sekunden Startzeit gingen fuer
# `import qfluentwidgets` drauf, praktisch vollstaendig fuer scipy.ndimage und
# numpy - und 101 der 199 MB im entpackten Archiv, das bei jedem Start neu
# ausgepackt wird.
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
        # Siehe die Begruendung oberhalb von Analysis: haengen ausschliesslich
        # am Acryl-Weichzeichner, den Amboss nicht benutzt.
        'scipy',
        'numpy',
        'PIL',
        'colorthief',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Von PyQt5 mitgeschleppte Bibliotheken, die Amboss nie anfasst.
#
# Gemessen am laufenden Programm (Modulliste des Prozesses, nicht des
# PyInstaller-Bootloaders - der laedt Qt gar nicht): keine davon wird geladen.
# Sie werden trotzdem bei jedem Start mit entpackt.
#
# - opengl32sw.dll (20 MB) ist Mesas Software-OpenGL. Qt laedt eine
#   GL-Implementierung erst, wenn jemand einen GL-Kontext anfordert. Amboss
#   besteht aus gewoehnlichen Widgets und fordert keinen an; gemessen wird
#   ueberhaupt keine GL-Bibliothek geladen, auch nicht die des Treibers.
# - Qt5Quick/Qt5Qml/Qt5QmlModels (7,8 MB) sind QML. Amboss benutzt kein QML.
# - qwebgl/qminimal/qoffscreen sind Anzeige-Backends fuer Faelle, die es in
#   einer Windows-Anwendung nicht gibt (qoffscreen brauchen nur die Tests, und
#   die laufen aus dem Quellcode, nicht aus der exe).
#
# ANGLE (libGLESv2, d3dcompiler_47) bleibt bewusst drin, obwohl auch es nicht
# geladen wird: es ist Qts Rueckfallebene, falls auf irgendeinem Rechner doch
# ein GL-Kontext angefordert wird. 7 MB als Versicherung gegen ein Programm,
# das bei einem Fremden gar nicht erst startet, ist ein guter Tausch - das
# Software-OpenGL darunter waere ohnehin nur die dritte Stufe.
_UNGENUTZT = {
    "opengl32sw.dll",
    "Qt5Quick.dll", "Qt5Qml.dll", "Qt5QmlModels.dll", "Qt5QuickWidgets.dll",
    "qwebgl.dll", "qminimal.dll", "qoffscreen.dll",
}
_vorher = len(a.binaries)
a.binaries = [eintrag for eintrag in a.binaries
              if Path(eintrag[0]).name not in _UNGENUTZT]
print(f"amboss.spec: {_vorher - len(a.binaries)} ungenutzte Qt-Bibliotheken entfernt")

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
