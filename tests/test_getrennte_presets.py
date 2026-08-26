# -*- coding: utf-8 -*-
"""Bei getrennten Presets muss man den ignorierten Werten ansehen, dass sie es sind.

Gemeldet am 26.08.2026: Codec- und Preset-Auswahl waren ausgegraut, der
Qualitaetsregler daneben nicht - obwohl der Hinweis darunter sagt, dass alle
drei ignoriert werden.

Ursache war nicht der Code (setEnabled(False) stand da), sondern
qfluentwidgets: sein Slider zeichnet sich abgeschaltet pixelgleich wie
eingeschaltet. Deshalb wird hier am Bild geprueft, nicht an isEnabled().

Aufruf:  python -u tests/test_getrennte_presets.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="amboss_presets_")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt5.QtWidgets import QApplication
from qfluentwidgets import MessageBoxBase

MessageBoxBase.exec = lambda self, *a, **k: 0
MessageBoxBase.exec_ = lambda self, *a, **k: 0

from settings_manager import CONFIG_PATH

CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
CONFIG_PATH.write_text(json.dumps({"language": "de", "check_for_updates": False}),
                       encoding="utf-8")

app = QApplication(sys.argv)
import ui.main_window as mw

fehler = []
geprueft = 0


def pruefe(bezeichnung, ist, soll):
    global geprueft
    geprueft += 1
    if ist != soll:
        fehler.append(f"{bezeichnung}: ist {ist!r}, erwartet {soll!r}")


def bild(widget):
    widget.show()
    app.processEvents()
    return widget.grab().toImage()


def unterschied(a, b):
    """Anteil der Pixel, die sich unterscheiden."""
    if a.size() != b.size():
        return 1.0
    anders = sum(1 for y in range(a.height()) for x in range(a.width())
                 if a.pixel(x, y) != b.pixel(x, y))
    return anders / max(a.width() * a.height(), 1)


fenster = mw.MainWindow()
fenster.resize(1400, 900)
fenster.stackedWidget.setCurrentWidget(fenster.convert_page)
app.processEvents()

# Die drei Bedienelemente der immer sichtbaren Zeile. Die Beschriftung darueber
# ist bewusst nicht dabei: qfluentwidgets-Labels setzen ihre Farbe selbst und
# ueberschreiben jeden Versuch von aussen (gemessen: 0,0 % Unterschied, sowohl
# per Stylesheet als auch per setTextColor). Der Hinweis unter der Zeile sagt
# ohnehin ausdruecklich, dass die Werte oben nicht gelten.
BETROFFEN = ("codec_combo", "preset_combo", "crf_slider")

# --- Aus: alles bedienbar ----------------------------------------------
fenster.separate_presets_check.setChecked(False)
app.processEvents()
for name in BETROFFEN:
    pruefe(f"{name} bedienbar", getattr(fenster, name).isEnabled(), True)
vorher = {name: bild(getattr(fenster, name)) for name in BETROFFEN}

# --- An: alles muss abgeschaltet UND sichtbar anders sein ---------------
fenster.separate_presets_check.setChecked(True)
app.processEvents()

for name in BETROFFEN:
    pruefe(f"{name} abgeschaltet", getattr(fenster, name).isEnabled(), False)

for name in BETROFFEN:
    nachher = bild(getattr(fenster, name))
    anteil = unterschied(vorher[name], nachher)
    pruefe(f"{name} sieht sichtbar anders aus", anteil > 0.01, True)
    print(f"   {name:14} Pixelunterschied: {anteil * 100:5.1f} %")

pruefe("Hinweis wird eingeblendet", fenster.split_presets_hint.isHidden(), False)
pruefe("die Bucket-Regler erscheinen", fenster.split_encoding_widget.isHidden(), False)

# --- Und wieder aus: alles zurueck --------------------------------------
fenster.separate_presets_check.setChecked(False)
app.processEvents()
for name in BETROFFEN:
    pruefe(f"{name} wieder bedienbar", getattr(fenster, name).isEnabled(), True)
for name in BETROFFEN:
    zurueck = bild(getattr(fenster, name))
    pruefe(f"{name} sieht wieder aus wie vorher",
           unterschied(vorher[name], zurueck) < 0.01, True)

# --- Mehrfaches Umschalten darf nichts anhaeufen -------------------------
for _ in range(5):
    fenster.separate_presets_check.setChecked(True)
    app.processEvents()
    fenster.separate_presets_check.setChecked(False)
    app.processEvents()
for name in BETROFFEN:
    zurueck = bild(getattr(fenster, name))
    pruefe(f"{name} nach 5x Umschalten unveraendert",
           unterschied(vorher[name], zurueck) < 0.01, True)

print(f"\n{geprueft - len(fehler)}/{geprueft} bestanden")
for e in fehler:
    print("  FEHLER:", e)

sys.stdout.flush()
os._exit(1 if fehler else 0)
