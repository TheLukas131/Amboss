# -*- coding: utf-8 -*-
"""Der Abgleich zwischen Quelle und Ergebnis - ohne Grafikkarte pruefbar.

Die Konvertierung liest eine Datei nur noch einmal mit ffprobe und leitet
Laufzeit, Spurenzahl und Untertitel-Auswahl aus diesem einen Ergebnis ab. An
diesen Angaben haengt, ob eine Quelldatei geloescht werden darf. Der Test
belegt deshalb, dass der eine Aufruf dasselbe liefert wie vorher die einzelnen
- und dass eine unlesbare Datei als unlesbar gilt statt als "hat keine Spuren".

Braucht FFmpeg, aber keinen NVENC-Encoder.

Aufruf:  python -u tests/test_abgleich.py
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path, PureWindowsPath

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ffmpeg_processor import FFmpegProcessor, text_subtitle_indices
from library_dispatch import media_folder_of, ready_folders
from models import FileStatus, VideoFile

fehler = []
geprueft = 0


def pruefe(bezeichnung, ist, soll):
    global geprueft
    geprueft += 1
    if ist != soll:
        fehler.append(f"{bezeichnung}: ist {ist!r}, erwartet {soll!r}")


# =======================================================================
# 1. Untertitel-Auswahl: nur Text, gezaehlt unter den Untertitelspuren
# =======================================================================
pruefe("Text-Untertitel zwischen Bild-Untertiteln",
       text_subtitle_indices(["hdmv_pgs_subtitle", "subrip", "dvd_subtitle", "ASS", ""]), [1, 3])
pruefe("keine Untertitel", text_subtitle_indices([]), [])

# =======================================================================
# 2. Vorgezogenes Verschieben: der Ordner ergibt sich aus dem Pfad allein
# =======================================================================
basis = PureWindowsPath(r"D:\Downloads\Converted")


def mit_ziel(pfad, status=FileStatus.FERTIG):
    video = VideoFile(source_path=Path("gibt-es-nicht.mkv"))
    video.target_path = pfad
    video.status = status
    return video


pruefe("Serie: Ordner der Serie",
       media_folder_of(mit_ziel(basis / "Serien" / "The Bear" / "Season 02" / "x.mp4"), basis),
       basis / "Serien" / "The Bear")
pruefe("andere Schreibweise desselben Laufwerks",
       media_folder_of(mit_ziel(PureWindowsPath("d:/downloads/converted/Filme/Dune/Dune.mp4")), basis),
       basis / "Filme" / "Dune")
pruefe("ohne Umbenennen: keine Einheit",
       media_folder_of(mit_ziel(basis / "x.mp4"), basis), None)

staffel = basis / "Serien" / "The Bear" / "Season 02"
pruefe("offene Folge haelt den Ordner zurueck",
       ready_folders([mit_ziel(staffel / "1.mp4"),
                      mit_ziel(staffel / "2.mp4", FileStatus.WARTEND)], basis), [])
pruefe("gescheiterte Folge haelt den Ordner zurueck",
       ready_folders([mit_ziel(staffel / "1.mp4"),
                      mit_ziel(staffel / "2.mp4", FileStatus.FEHLER)], basis), [])
pruefe("alles fertig: Ordner ist frei",
       ready_folders([mit_ziel(staffel / "1.mp4"), mit_ziel(staffel / "2.mp4")], basis),
       [basis / "Serien" / "The Bear"])
pruefe("schon losgeschickt: nicht noch einmal",
       ready_folders([mit_ziel(staffel / "1.mp4")], basis, {basis / "Serien" / "The Bear"}), [])

# =======================================================================
# 3. Ein ffprobe-Aufruf liefert dasselbe wie vorher die einzelnen
# =======================================================================
ffmpeg = FFmpegProcessor()
if not ffmpeg.is_available():
    print("FFmpeg fehlt - Dateipruefungen uebersprungen")
    print(f"{geprueft - len(fehler)}/{geprueft} bestanden")
    for e in fehler:
        print("  FEHLER:", e)
    sys.exit(1 if fehler else 0)

arbeit = Path(tempfile.mkdtemp(prefix="amboss_abgleich_"))
untertitel = arbeit / "u.srt"
untertitel.write_text("1\n00:00:00,500 --> 00:00:01,500\nHallo\n", encoding="utf-8")

quelle = arbeit / "quelle.mkv"
subprocess.run([
    ffmpeg.ffmpeg_path, "-y", "-v", "error",
    "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25:duration=3",
    "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
    "-f", "lavfi", "-i", "sine=frequency=880:duration=3",
    "-i", str(untertitel),
    "-map", "0:v", "-map", "1:a", "-map", "2:a", "-map", "3:s",
    "-c:v", "libx264", "-c:a", "aac", "-c:s", "srt", str(quelle),
], capture_output=True, timeout=180,
    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
pruefe("Testdatei erzeugt", quelle.is_file(), True)

if quelle.is_file():
    gelesen = ffmpeg.get_video_metadata(quelle)
    pruefe("Datei gilt als gelesen", gelesen.probed, True)
    pruefe("Spurenzahl wie count_streams",
           gelesen.stream_counts(), ffmpeg.count_streams(quelle))
    pruefe("zwei Tonspuren gezaehlt", len(gelesen.audio_codecs), 2)
    pruefe("Untertitel-Auswahl wie get_text_subtitle_indices",
           text_subtitle_indices(gelesen.subtitle_codecs),
           ffmpeg.get_text_subtitle_indices(quelle))
    pruefe("Laufzeit wie get_duration",
           abs(gelesen.duration_seconds - ffmpeg.get_duration(quelle)) < 0.01, True)
    pruefe("Pixelformat wie pixel_format",
           gelesen.pixel_format, ffmpeg.pixel_format(quelle))

# Eine unlesbare Datei darf nicht wie "Datei ohne Tonspur" aussehen - sonst
# liesse die Pruefung nach dem Encode eine verlorene Spur durchgehen.
kaputt = arbeit / "kaputt.mkv"
kaputt.write_bytes(b"das ist kein Video" * 64)
pruefe("unlesbare Datei gilt als nicht gelesen",
       ffmpeg.get_video_metadata(kaputt).probed, False)
pruefe("fehlende Datei gilt als nicht gelesen",
       ffmpeg.get_video_metadata(arbeit / "fehlt.mkv").probed, False)

print(f"\n{geprueft - len(fehler)}/{geprueft} bestanden")
for e in fehler:
    print("  FEHLER:", e)
sys.exit(1 if fehler else 0)
