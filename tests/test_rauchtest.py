# -*- coding: utf-8 -*-
"""Rauchtest: jede Seite, jeder Dialog, beide Designs, beide Sprachen.

Anlass: scipy, numpy, PIL und colorthief fliegen aus der exe. Sie haengen an
qfluentwidgets' Acryl-Weichzeichner, den Amboss abschaltet - die Bibliothek
faengt ihr Fehlen selbst ab (isAcrylicAvailable = False). Dieser Test soll
belegen, dass ohne sie nichts umkippt, und zwar an der Oberflaeche und nicht
nur an der Importzeile.

Jede unbehandelte Ausnahme in einem Qt-Slot faellt hier auf, weil der
excepthook sie aufsammelt statt sie verschwinden zu lassen.
"""

import json
import os
import sys
import tempfile
import traceback
from pathlib import Path
from unittest import mock

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="amboss_rauch_")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# --- Die exe ohne scipy/numpy/PIL/colorthief nachstellen -----------------
# Muss vor dem ersten qfluentwidgets-Import stehen: dort entscheidet ein
# try/except beim Laden ein fuer alle Mal, ob Acryl verfuegbar ist. Ohne diese
# Sperre pruefte der Test die Entwicklungsumgebung (mit scipy) statt der exe.
import importlib.abc

NICHT_IN_DER_EXE = {"scipy", "numpy", "PIL", "colorthief"}


class Sperre(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in NICHT_IN_DER_EXE:
            raise ImportError(f"{fullname} ist in der exe nicht enthalten")
        return None


sys.meta_path.insert(0, Sperre())

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
from qfluentwidgets import MessageBoxBase, Theme, setTheme

fehler = []
geprueft = 0
ausnahmen = []


def pruefe(bezeichnung, ist, soll):
    global geprueft
    geprueft += 1
    if ist != soll:
        fehler.append(f"{bezeichnung}: ist {ist!r}, erwartet {soll!r}")


def versuche(bezeichnung, aktion):
    """Fuehrt etwas aus und merkt sich eine Ausnahme, statt abzubrechen."""
    global geprueft
    geprueft += 1
    try:
        aktion()
    except Exception:
        fehler.append(f"{bezeichnung}: {traceback.format_exc().strip().splitlines()[-1]}")


# Jede Ausnahme aus einem Slot einsammeln
def _hook(t, v, tb):
    ausnahmen.append("".join(traceback.format_exception(t, v, tb)))


sys.excepthook = _hook

MessageBoxBase.exec = lambda self, *a, **k: 0
MessageBoxBase.exec_ = lambda self, *a, **k: 0
MessageBoxBase.open = lambda self, *a, **k: None

from settings_manager import CONFIG_PATH

werkstatt = Path(tempfile.mkdtemp(prefix="amboss_rauch_daten_"))
mediathek = werkstatt / "Medien" / "Filme"
mediathek.mkdir(parents=True)
converted = werkstatt / "Converted"
(converted / "Filme" / "Ein Film").mkdir(parents=True)
(converted / "Filme" / "Ein Film" / "Ein Film.mp4").write_bytes(b"x" * 2048)

CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
CONFIG_PATH.write_text(json.dumps({
    "language": "de", "check_for_updates": False,
    "category_folders": {"Anime": "", "Anime Filme": "", "Filme": str(mediathek), "Serien": ""},
    "target_folder": str(converted),
}), encoding="utf-8")

app = QApplication(sys.argv)

# --- Der Kern der Umstellung: die Bibliothek meldet Acryl als nicht verfuegbar
import qfluentwidgets.components.widgets.acrylic_label as al
pruefe("Acryl ist wie in der exe abgeschaltet", al.isAcrylicAvailable, False)
for verboten in sorted(NICHT_IN_DER_EXE):
    pruefe(f"{verboten} wurde nicht geladen", verboten in sys.modules, False)

import i18n
from models import FileStatus, MediaType, NASUploadItem, VideoFile, VideoMetadata
import ui.main_window as mw

mw.MainWindow.notify_system = lambda self, *a, **k: None

fenster = mw.MainWindow()
fenster.resize(1400, 900)

videos = []
for i in range(1, 4):
    q = werkstatt / f"Serie S01E{i:02d}.mkv"
    q.write_bytes(b"y" * 1024)
    v = VideoFile(source_path=q, media_type=MediaType.SERIEN, series_name="Serie",
                  season=1, episode=i, target_path=converted / f"S01E{i:02d}.mp4")
    v.source_metadata = VideoMetadata(pixel_format="yuv420p10le", bit_depth=10,
                                      color_transfer="smpte2084",
                                      audio_codecs=["truehd"], audio_profiles=[""],
                                      subtitle_codecs=["hdmv_pgs_subtitle"])
    videos.append(v)
fenster.videos = videos
fenster.update_file_table()

# =======================================================================
# 1. Jede Seite anzeigen und zeichnen lassen
# =======================================================================
seiten = [("Konvertierung", fenster.convert_page),
          ("Protokoll", fenster.log_page), ("Mediathek", fenster.nas_page),
          ("Einstellungen", fenster.settings_page)]

for name, seite in seiten:
    def zeigen(seite=seite):
        fenster.stackedWidget.setCurrentWidget(seite)
        app.processEvents()
        seite.grab()          # zwingt zum echten Zeichnen
        app.processEvents()
    versuche(f"Seite {name} zeichnen", zeigen)

# Die Einzelheiten zu einer Datei stehen unter der Warteschlange statt auf einer
# eigenen Seite - aufklappen, zeichnen, wieder schliessen.
def einzelheiten():
    fenster.stackedWidget.setCurrentWidget(fenster.convert_page)
    fenster._toggle_details(videos[0])
    app.processEvents()
    if fenster.details_panel.isHidden() or fenster.details_panel.video is not videos[0]:
        raise AssertionError("Einzelheiten wurden nicht angezeigt")
    fenster.convert_page.grab()
    fenster._toggle_details(videos[0])
    if not fenster.details_panel.isHidden():
        raise AssertionError("zweiter Klick hat die Einzelheiten nicht geschlossen")
versuche("Einzelheiten zu einer Datei", einzelheiten)

# Das ganze Fenster inklusive Seitenleiste (dort sass der Acryl-Effekt)
versuche("Gesamtes Fenster zeichnen", lambda: fenster.grab())
versuche("Seitenleiste zeichnen", lambda: fenster.navigationInterface.grab())

# =======================================================================
# 2. Beide Designs - der Acryl-Effekt haengt am Design
# =======================================================================
for name, thema in (("Hell", Theme.LIGHT), ("Dunkel", Theme.DARK), ("System", Theme.AUTO)):
    def wechseln(thema=thema):
        setTheme(thema)
        app.processEvents()
        fenster.grab()
        fenster.navigationInterface.grab()
        app.processEvents()
    versuche(f"Design {name}", wechseln)
setTheme(Theme.DARK)

# =======================================================================
# 3. Jeder Dialog
# =======================================================================
from format_warnings import find_losses
from update_check import Release, UpdateInfo

befunde = find_losses(videos, lambda v: "h264_nvenc", "mp4")
pruefe("Befunde fuer den Dialog vorhanden", len(befunde) >= 3, True)

dialoge = [
    ("Verlustvorschau",
     lambda: __import__("ui.format_warning_dialog", fromlist=["x"])
             .FormatWarningDialog(befunde, fenster)),
    ("Update-Hinweis",
     lambda: __import__("ui.update_notice", fromlist=["x"]).UpdateDialog(
         UpdateInfo(newest=Release("9.9.9", "u", "- Neu"),
                    releases=[Release("9.9.9", "u", "- Neu")]), "1.0.0", fenster)),
    ("Aenderungsverlauf",
     lambda: __import__("ui.changelog_dialog", fromlist=["x"]).ChangelogDialog(fenster)),
    ("Medientyp-Bestaetigung",
     lambda: __import__("ui.media_type_review_dialog", fromlist=["x"])
             .MediaTypeReviewDialog(videos, fenster)),
    ("Fehlerbericht",
     lambda: __import__("ui.failure_report_dialog", fromlist=["x"])
             .FailureReportDialog(videos[:1], len(videos) - 1, fenster)),
    ("Einrichtung",
     lambda: __import__("ui.setup_dialog", fromlist=["x"])
             .SetupDialog(fenster._build_theme_toggle, fenster)),
    # ACHTUNG: ShutdownCountdownDialog.__init__ ruft direkt
    # `shutdown /s /t 60` auf - das Erzeugen des Dialogs faehrt den Rechner
    # herunter. Am 20.08.2026 genau so passiert und der Nutzer hat dabei
    # ungespeicherte Arbeit verloren. Der Aufruf wird deshalb abgefangen, und
    # der Test prueft zusaetzlich, DASS er kommen wollte.
    ("Herunterfahren (Systembefehl abgefangen)", lambda: _herunterfahren_pruefen()),
    ("FFmpeg-Download",
     lambda: __import__("ui.ffmpeg_download", fromlist=["x"])
             .FFmpegDownloadDialog(fenster)),
]

def _herunterfahren_pruefen():
    """Baut den Dialog, ohne den Rechner anzufassen."""
    modul = __import__("ui.shutdown_countdown_dialog", fromlist=["x"])
    befehle = []
    with mock.patch.object(modul.subprocess, "run",
                           side_effect=lambda cmd, **k: befehle.append(list(cmd))):
        dialog = modul.ShutdownCountdownDialog(fenster)
        app.processEvents()
        dialog.widget.grab()
        dialog._timer.stop()          # sonst tickt er weiter
    if not any("/s" in b for b in befehle):
        raise AssertionError(f"kein Shutdown-Befehl abgesetzt: {befehle}")
    return dialog


for name, bauen in dialoge:
    def oeffnen(bauen=bauen):
        d = bauen()
        app.processEvents()
        d.widget.grab()       # wirklich zeichnen, nicht nur bauen
        app.processEvents()
    versuche(f"Dialog {name}", oeffnen)

# Zusammenfuehren-Dialog braucht Kandidaten, deshalb getrennt
versuche("Dialog Zusammenfuehren", lambda: __import__(
    "ui.merge_review_dialog", fromlist=["x"]).MergeReviewDialog([], fenster).widget.grab())

# =======================================================================
# 3b. Der Ladebildschirm - auch er darf ohne PIL entstehen
# =======================================================================
from resources import resource_path
import ui.theme as thema_modul
from ui.splash import erzeuge_splash

for modus in ("dark", "light"):
    def bauen(modus=modus):
        echt = thema_modul.detect_system_theme
        thema_modul.detect_system_theme = lambda: modus
        try:
            s = erzeuge_splash(resource_path("logo.png"), "Amboss", "9.9.9",
                               "Wird geladen...")
            if s.pixmap().isNull() or s.pixmap().width() < 100:
                raise AssertionError("Ladebildschirm ist leer")
            s.show()
            app.processEvents()
            s.close()
        finally:
            thema_modul.detect_system_theme = echt
    versuche(f"Ladebildschirm ({modus})", bauen)

# Ohne Logo darf er ebenfalls entstehen
versuche("Ladebildschirm ohne Logo",
         lambda: erzeuge_splash(None, "Amboss", "9.9.9", "x").pixmap().isNull() and
                 (_ for _ in ()).throw(AssertionError("leer")))

# =======================================================================
# 4. Auf Englisch alles noch einmal
# =======================================================================
i18n.set_language("en")
zweites = mw.MainWindow()
zweites.resize(1400, 900)
for name, seite in [("Konvertierung", zweites.convert_page),
                    ("Mediathek", zweites.nas_page),
                    ("Einstellungen", zweites.settings_page)]:
    def zeigen(seite=seite, f=zweites):
        f.stackedWidget.setCurrentWidget(seite)
        app.processEvents()
        seite.grab()
    versuche(f"Englisch: Seite {name}", zeigen)
versuche("Englisch: Fenster zeichnen", lambda: zweites.grab())
i18n.set_language("de")

# =======================================================================
# 5. Die Mediathek-Tabelle mit Inhalt
# =======================================================================
versuche("Mediathek einlesen", fenster.scan_converted_folder)
versuche("Mediathek-Tabelle zeichnen", lambda: fenster.nas_page.grab())
pruefe("Mediathek fand den Film", len(fenster.nas_items), 1)

# =======================================================================
# 6. Nichts darf im Hintergrund geflogen sein
# =======================================================================
app.processEvents()
pruefe("keine unbehandelten Ausnahmen", ausnahmen, [])
if ausnahmen:
    for a in ausnahmen[:3]:
        print("   ", a.strip().splitlines()[-1])

print(f"\n{geprueft - len(fehler)}/{geprueft} bestanden")
for e in fehler:
    print("  FEHLER:", e)

sys.stdout.flush()
os._exit(1 if fehler else 0)
