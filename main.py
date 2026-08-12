#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Amboss - konvertiert Videos nach AV1 & H.264 über NVIDIA NVENC.

Erkennt Serien, Anime und Filme am Dateinamen, sortiert sie in eine
passende Ordnerstruktur und schiebt sie auf Wunsch in die Mediathek.

Version: 1.0.0
Lizenz: GPLv3 (siehe LICENSE) - die Anwendung bindet PyQt5 und
PyQt-Fluent-Widgets ein, die beide unter der GPLv3 stehen.
"""

import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

import crash_logging
import i18n
from models import APP_NAME, APP_VERSION
from resources import resource_path
from ui.main_window import MainWindow

# Muss vor allem anderen laufen: ohne eigenen excepthook beendet PyQt5 den
# Prozess bei jeder unbehandelten Ausnahme in einem Slot sofort per qFatal(),
# ohne Meldung und ohne Protokoll (siehe crash_logging.py).
crash_logging.install()


APP_USER_MODEL_ID = "Amboss.VideoConverter"


def set_app_user_model_id():
    """Meldet der Windows-Shell eine eigene AppUserModelID an.

    Ohne die ordnet Windows 10/11 die Benachrichtigungen der App keinem Absender
    zu und zeigt sie schlicht nicht an - QSystemTrayIcon.showMessage() meldet
    trotzdem Erfolg, sichtbar wird aber nichts. Mit gesetzter ID erscheint die App
    unter Einstellungen > Benachrichtigungen und kann dort auch verwaltet werden.
    Muss vor dem Erzeugen der QApplication laufen."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except (OSError, AttributeError):
        pass  # ohne ID gibt es eben keine Toasts - kein Grund, den Start zu verhindern


def main():
    set_app_user_model_id()
    # PassThrough statt der Default-Rundung auf ganzzahlige Skalierungsfaktoren -
    # bei gebrochenen Windows-Skalierungen (125%/150%) rundete Qt sonst leicht daneben,
    # was bei qfluentwidgets' pixelgenau kalibrierten Buttons zu abgeschnittenem
    # Text am oberen Rand führte.
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    # Sprache festlegen, bevor irgendeine Oberflaeche gebaut wird
    from settings_manager import SettingsManager
    i18n.set_language(SettingsManager().get("language"))

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    # Kein eigenes app.setFont() mehr - qfluentwidgets setzt für jede seiner
    # Komponenten (Buttons, Labels, ...) bereits explizit die passende Fluent-
    # Schriftart/-größe; ein globaler Override hat vorher genau damit kollidiert.

    icon_path = resource_path("icon.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))
    # Anteilig zur Bildschirmgröße statt maximiert: eine feste Größe wirkte auf
    # großen Bildschirmen verloren und schnitt auf kleinen unten ab. Maximiert
    # wiederum greift erst nach dem Anzeigen, wodurch ein sofort geöffneter
    # Dialog seine Abdunkelung noch auf die alte Fenstergröße legte.
    available = app.primaryScreen().availableGeometry()
    window.resize(
        max(window.minimumWidth(), int(available.width() * 0.80)),
        max(window.minimumHeight(), int(available.height() * 0.85)),
    )
    frame = window.frameGeometry()
    frame.moveCenter(available.center())
    window.move(frame.topLeft())
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
