# -*- coding: utf-8 -*-
"""Laesst alle Testreihen nacheinander laufen und fasst zusammen.

Jede Reihe laeuft als eigener Prozess: mehrere QApplication-Instanzen in einem
Prozess bringen Qt unter der Offscreen-Anzeige zum Absturz, und ein Absturz in
einer Reihe soll die Ergebnisse der anderen nicht mitnehmen.

Aufruf:  python -u tests/alle_tests.py
"""

import re
import subprocess
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent

REIHEN = [
    ("Rauchtest: Seiten, Dialoge, Designs", "test_rauchtest.py"),
    ("Echte Konvertierung", "test_konvertierung.py"),
]

RAUSCHEN = re.compile(r"QFontDatabase|Note that Qt|QFluentWidgets Pro|^\s*$")
ERGEBNIS = re.compile(r"(\d+)/(\d+) bestanden")

gesamt_ok = gesamt = 0
kaputt = []

for bezeichnung, datei in REIHEN:
    pfad = HIER / datei
    if not pfad.is_file():
        print(f"{bezeichnung:38} -- fehlt ({datei})")
        continue

    lauf = subprocess.run([sys.executable, "-u", str(pfad)],
                          capture_output=True, text=True, timeout=3600)
    zeilen = [z for z in ((lauf.stdout or "") + (lauf.stderr or "")).splitlines()
              if not RAUSCHEN.search(z)]

    treffer = None
    for zeile in zeilen:
        m = ERGEBNIS.search(zeile)
        if m:
            treffer = m

    if treffer:
        ok, alle = int(treffer.group(1)), int(treffer.group(2))
        gesamt_ok += ok
        gesamt += alle
        print(f"{bezeichnung:38} {'OK  ' if ok == alle else 'FEHL'} {ok}/{alle}")
        if ok != alle:
            kaputt.append((bezeichnung, [z for z in zeilen if "FEHLER" in z]))
    elif lauf.returncode == 0:
        print(f"{bezeichnung:38} OK   (ohne Zaehlung)")
    else:
        print(f"{bezeichnung:38} FEHL (Exitcode {lauf.returncode})")
        kaputt.append((bezeichnung, zeilen[-6:]))

print("-" * 60)
print(f"Summe: {gesamt_ok}/{gesamt} bestanden")
for bezeichnung, zeilen in kaputt:
    print(f"\n{bezeichnung}:")
    for zeile in zeilen:
        print("   ", zeile.strip())

sys.exit(1 if gesamt_ok != gesamt or kaputt else 0)
