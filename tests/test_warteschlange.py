# -*- coding: utf-8 -*-
"""Die Warteschlange: Staffeln, Filter, Zahlen - und dass die Tabelle sie trifft.

Seit Folgen unter einer Staffel-Zeile stehen, ist eine Tabellenzeile nicht mehr
der Index der Datei. Jede Stelle, die das noch annimmt, schriebe Fortschritt in
die falsche Zeile. Geprueft wird deshalb beides: was angezeigt werden soll
(queue_model) und dass die Tabelle es an der richtigen Stelle zeigt.

Aufruf:  python -u tests/test_warteschlange.py
"""

import os
import sys
import tempfile
from pathlib import Path, PureWindowsPath

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="amboss_schlange_")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import FileStatus, MediaType, VideoFile, VideoMetadata
from queue_model import (
    build_rows, format_duration, format_size_short, relative_target, remaining_seconds,
    size_change, status_counts, summarize,
)

fehler = []
geprueft = 0
GB = 1024 ** 3


def pruefe(bezeichnung, ist, soll):
    global geprueft
    geprueft += 1
    if ist != soll:
        fehler.append(f"{bezeichnung}: ist {ist!r}, erwartet {soll!r}")


def folge(name, staffel, nummer, typ=MediaType.SERIEN):
    v = VideoFile(source_path=Path(f"{name} S{staffel:02d}E{nummer:02d}.mkv"),
                  media_type=typ, series_name=name, season=staffel, episode=nummer)
    v.original_size = 2 * GB
    v.target_path = Path("Converted") / "Serien" / name / f"Season {staffel:02d}" / f"{nummer}.mp4"
    return v


def film(name):
    v = VideoFile(source_path=Path(f"{name}.mkv"), media_type=MediaType.FILME, movie_name=name)
    v.original_size = 10 * GB
    v.target_path = Path("Converted") / "Filme" / name / f"{name}.mp4"
    return v


# =======================================================================
# 1. Zeilen: Staffeln ab zwei Folgen, alles andere steht allein
# =======================================================================
# Bewusst durcheinander: Serie A, Film, Serie A, einzelne Folge von Serie B.
videos = [folge("A", 1, 2), film("Film"), folge("A", 1, 1), folge("B", 3, 7), folge("A", 2, 1)]
zeilen = build_rows(videos)
form = [("Staffel", z.group.name, z.group.season) if z.is_group
        else ("Datei", z.index, z.parent is not None) for z in zeilen]
pruefe("Staffel steht bei ihrer ersten Folge, Folgen nach Nummer sortiert", form, [
    ("Staffel", "A", 1), ("Datei", 2, True), ("Datei", 0, True),
    ("Datei", 1, False), ("Datei", 3, False), ("Datei", 4, False),
])
pruefe("jede Datei genau einmal", sorted(z.index for z in zeilen if not z.is_group), [0, 1, 2, 3, 4])
pruefe("leere Warteschlange", build_rows([]), [])

# =======================================================================
# 2. Zusammenfassung einer Staffel
# =======================================================================
staffel = zeilen[0].group
videos[0].status, videos[0].progress, videos[0].new_size = FileStatus.FERTIG, 100, GB // 2
videos[2].status, videos[2].progress = FileStatus.VERARBEITET, 40
s = summarize(staffel, videos)
pruefe("eine von zwei fertig", (s.done, s.total, s.running, s.failed), (1, 2, 1, 0))
pruefe("Fortschritt ist der Mittelwert", s.progress, 70)
pruefe("vorher/nachher erst, wenn alle fertig sind", s.new_size, 0)
videos[2].status, videos[2].new_size = FileStatus.FERTIG, GB // 2
pruefe("dann die Summe", summarize(staffel, videos).new_size, GB)
videos[2].status = FileStatus.UEBERSPRUNGEN
videos[2].progress = 0
pruefe("uebersprungene zaehlen als erledigt", summarize(staffel, videos).progress, 100)

# =======================================================================
# 3. Filter und Zaehler
# =======================================================================
videos[3].status = FileStatus.FEHLER
pruefe("Zaehler je Filter", status_counts(videos),
       {"all": 5, "waiting": 2, "processing": 0, "done": 2, "error": 1})

# =======================================================================
# 4. Texte
# =======================================================================
basis = PureWindowsPath(r"D:\Downloads\Converted")
pruefe("Ziel relativ zum Zielordner",
       relative_target(basis / "Filme" / "Dune" / "Dune.mp4", basis), r"Filme\Dune\Dune.mp4")
pruefe("anderswo: voller Pfad",
       relative_target(PureWindowsPath(r"E:\x\Dune.mp4"), basis), r"E:\x\Dune.mp4")
pruefe("ohne Ziel", relative_target(None, basis), "-")
pruefe("Groesse kurz", [format_size_short(n) for n in (0, 640 * 1024 ** 2, int(2.6 * GB), 17 * GB)],
       ["0 B", "640 MB", "2.6 GB", "17.0 GB"])
pruefe("kleiner geworden", size_change(4 * GB, GB), "4.0 GB → 1.0 GB (−75 %)")
pruefe("groesser geworden", size_change(GB, 2 * GB), "1.0 GB → 2.0 GB (+100 %)")
pruefe("noch kein Ergebnis", size_change(4 * GB, 0), "4.0 GB")
pruefe("Dauer", [format_duration(n) for n in (0, 192, 3792)], ["00:00", "03:12", "1:03:12"])

laeuft = film("Laeuft")
laeuft.status, laeuft.progress, laeuft.encode_speed = FileStatus.VERARBEITET, 50, 10.0
laeuft.source_metadata = VideoMetadata(duration_seconds=6000.0)
pruefe("Restzeit aus dem Tempo von ffmpeg", remaining_seconds(laeuft), 300.0)
laeuft.status = FileStatus.WARTEND
pruefe("keine Restzeit, solange nichts laeuft", remaining_seconds(laeuft), None)

# =======================================================================
# 5. Die Tabelle: richtige Zeile, Zuklappen, Filter
# =======================================================================
from PyQt5.QtWidgets import QApplication

app = QApplication(sys.argv)
from ui.queue_table import COL_NAME, COL_SIZE, COL_STATUS, COL_TARGET, QueueTable

videos = [folge("A", 1, 2), film("Film"), folge("A", 1, 1)]
tabelle = QueueTable()
tabelle.set_videos(videos, Path("Converted"))
pruefe("Staffel + zwei Folgen + Film", tabelle.rowCount(), 4)
pruefe("Datei 0 steht nicht in Zeile 0", tabelle.row_of(0), 2)
pruefe("der Film steht am Ende", tabelle.row_of(1), 3)
pruefe("Staffel-Zeile nennt die Serie", "A" in tabelle.item(0, COL_NAME).text(), True)
pruefe("Ziel des Films ist relativ",
       tabelle.item(3, COL_TARGET).text(), str(Path("Filme") / "Film" / "Film.mp4"))
pruefe("voller Pfad im Tooltip",
       tabelle.item(3, COL_TARGET).toolTip(), str(videos[1].target_path))

videos[0].status, videos[0].progress, videos[0].new_size = FileStatus.FERTIG, 100, GB // 2
tabelle.refresh_video(0)
pruefe("Status landet in der Zeile der Datei", tabelle.item(2, COL_STATUS).text(), "Fertig")
pruefe("nicht in der Zeile mit ihrer Nummer", tabelle.item(0, COL_STATUS).text(), "1/2 fertig")
pruefe("Groesse vorher/nachher", tabelle.item(2, COL_SIZE).text(), "2.0 GB → 512 MB (−75 %)")
tabelle.refresh_video(99)   # darf nichts tun und nicht abstuerzen

tabelle._on_cell_clicked(0, 0)
pruefe("zugeklappt: Folgen weg", [tabelle.isRowHidden(r) for r in range(4)],
       [False, True, True, False])
tabelle._on_cell_clicked(0, 0)
pruefe("aufgeklappt: alles da", [tabelle.isRowHidden(r) for r in range(4)], [False] * 4)

tabelle.set_filter("done")
pruefe("Filter Fertig: Staffel und ihre fertige Folge",
       [tabelle.isRowHidden(r) for r in range(4)], [False, True, False, True])
tabelle.set_filter("error")
pruefe("Filter Fehler: nichts, auch keine leere Staffel-Zeile",
       [tabelle.isRowHidden(r) for r in range(4)], [True] * 4)
tabelle.set_filter("all")

gewaehlt = []
tabelle.video_selected.connect(gewaehlt.append)
tabelle._on_cell_clicked(3, 0)
tabelle._on_cell_clicked(0, 0)
pruefe("Klick auf eine Datei waehlt sie, auf eine Staffel nicht", gewaehlt, [videos[1]])

lang = [folge("Lang", 1, n) for n in range(1, 15)]
tabelle.set_videos(lang, Path("Converted"))
pruefe("lange Warteschlange: Staffel startet zugeklappt",
       [tabelle.isRowHidden(r) for r in range(3)], [False, True, True])

print(f"\n{geprueft - len(fehler)}/{geprueft} bestanden")
for e in fehler:
    print("  FEHLER:", e)
sys.stdout.flush()
os._exit(1 if fehler else 0)
