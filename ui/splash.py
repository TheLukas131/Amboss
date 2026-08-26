"""Ladebildschirm für die Zeit, in der noch kein Fenster da ist.

Zwischen Doppelklick und fertigem Fenster liegen zwei Abschnitte: der
PyInstaller-Bootloader packt das Archiv aus, danach lädt Python die Oberfläche
und baut sie auf. Der erste Abschnitt ist für die Anwendung unerreichbar - dort
läuft noch kein Python. Den zweiten kann sie überbrücken, und das ist gut die
Hälfte der Wartezeit.

Ohne das passiert nach dem Doppelklick sichtbar nichts, und wer das nicht
gewohnt ist, klickt ein zweites Mal - und startet Amboss zweimal.

Bewusst mit Qt-Bordmitteln gezeichnet statt mit einem fertigen Bild: PyInstaller
bringt zwar einen eigenen Startbildschirm mit, der aber Tcl/Tk in die exe zieht
(rund 12 MB) - für eine Anwendung, die gerade um zwei Drittel kleiner geworden
ist, ein schlechter Tausch.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt5.QtWidgets import QSplashScreen

BREITE = 420
HOEHE = 200

# Der Ladebildschirm erscheint, bevor das Design der Anwendung angewendet wird.
# Er richtet sich deshalb selbst nach dem Windows-Design - sonst blitzt vor
# einer dunklen Oberfläche eine helle Fläche auf.
_DUNKEL = {"grund": "#202020", "text": "#FFFFFF", "leise": "#A0A0A0", "rand": "#3A3A3A"}
_HELL = {"grund": "#F3F3F3", "text": "#1A1A1A", "leise": "#606060", "rand": "#D0D0D0"}


def _farben() -> dict:
    from ui.theme import detect_system_theme
    return _DUNKEL if detect_system_theme() == "dark" else _HELL


def erzeuge_splash(logo_pfad, app_name: str, version: str, hinweis: str) -> QSplashScreen:
    """Baut den Ladebildschirm. Anzeigen muss ihn der Aufrufer."""
    farben = _farben()
    verhaeltnis = 2  # für scharfe Darstellung auf hochauflösenden Bildschirmen

    bild = QPixmap(BREITE * verhaeltnis, HOEHE * verhaeltnis)
    bild.setDevicePixelRatio(verhaeltnis)
    bild.fill(QColor(farben["grund"]))

    maler = QPainter(bild)
    maler.setRenderHint(QPainter.Antialiasing)
    maler.setRenderHint(QPainter.SmoothPixmapTransform)

    maler.setPen(QColor(farben["rand"]))
    maler.drawRect(0, 0, BREITE - 1, HOEHE - 1)

    logo = QPixmap(str(logo_pfad)) if logo_pfad else QPixmap()
    if not logo.isNull():
        logo = logo.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        maler.drawPixmap(40, (HOEHE - 64) // 2 - 12, logo)

    links = 128 if not logo.isNull() else 40

    schrift = QFont()
    schrift.setPointSize(20)
    schrift.setBold(True)
    maler.setFont(schrift)
    maler.setPen(QColor(farben["text"]))
    maler.drawText(links, 78, app_name)

    schrift.setPointSize(9)
    schrift.setBold(False)
    maler.setFont(schrift)
    maler.setPen(QColor(farben["leise"]))
    maler.drawText(links, 100, f"v{version}")
    maler.drawText(links, 130, hinweis)

    maler.end()

    splash = QSplashScreen(bild, Qt.WindowStaysOnTopHint)
    splash.setAttribute(Qt.WA_DeleteOnClose)
    return splash
