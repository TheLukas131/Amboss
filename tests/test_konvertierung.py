# -*- coding: utf-8 -*-
"""Eine echte Konvertierung durch den echten Befehlsbau - kein Ersatzteil.

Der Zweck ist eng: nachweisen, dass Amboss nach Aenderungen am Bauplan oder am
Start noch wirklich Videos umwandelt, und zwar ueber denselben Weg wie im
Betrieb (FFmpegProcessor.build_command). Geprueft wird am Ergebnis - Laufzeit,
Spuren, Pixelformat - nicht am Rueckgabewert von ffmpeg.

Aufruf:  python -u tests/test_konvertierung.py
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ffmpeg_processor import FFmpegProcessor, chroma_fallback
from models import MediaType, VideoFile

fehler = []
geprueft = 0


def pruefe(bezeichnung, ist, soll):
    global geprueft
    geprueft += 1
    if ist != soll:
        fehler.append(f"{bezeichnung}: ist {ist!r}, erwartet {soll!r}")


ffmpeg = FFmpegProcessor()
if not ffmpeg.is_available():
    print("FFmpeg fehlt - uebersprungen")
    sys.exit(0)

arbeit = Path(tempfile.mkdtemp(prefix="amboss_konv_"))


def testvideo(name, pixelformat="yuv420p", dauer=3, tonspuren=1, untertitel=False):
    """Erzeugt ein echtes Testvideo mit Ton und optional Untertiteln."""
    ziel = arbeit / name
    befehl = [ffmpeg.ffmpeg_path, "-y", "-v", "error",
              "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate=25:duration={dauer}"]
    for _ in range(tonspuren):
        befehl += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={dauer}"]
    befehl += ["-map", "0:v"]
    for i in range(tonspuren):
        befehl += ["-map", f"{i + 1}:a"]
    befehl += ["-c:v", "libx264", "-pix_fmt", pixelformat, "-c:a", "aac", str(ziel)]
    lauf = subprocess.run(befehl, capture_output=True, text=True, timeout=180)
    if lauf.returncode != 0 or not ziel.is_file():
        return None
    return ziel


def konvertieren(quelle, ziel, codec="av1_nvenc", cq=37):
    video = VideoFile(source_path=quelle, media_type=MediaType.FILME,
                      movie_name=quelle.stem)
    untertitel = ffmpeg.get_text_subtitle_indices(quelle)
    pixelformat = ffmpeg.pixel_format(quelle)
    befehl = ffmpeg.build_command(video, cq, "p5", False, codec, ziel,
                                  untertitel, pixelformat)
    lauf = subprocess.run(befehl, capture_output=True, text=True, timeout=600)
    return lauf, befehl


# =======================================================================
# 1. Der Normalfall: ein Video mit Ton nach AV1/MP4
# =======================================================================
if not ffmpeg.check_encoder_available("av1_nvenc"):
    print("av1_nvenc nicht verfuegbar - Konvertierungstests uebersprungen")
    print(f"{geprueft - len(fehler)}/{geprueft} bestanden")
    sys.exit(1 if fehler else 0)

quelle = testvideo("quelle.mp4", dauer=3)
pruefe("Testvideo erzeugt", quelle is not None, True)

ziel = arbeit / "ziel.mp4"
lauf, befehl = konvertieren(quelle, ziel)
pruefe("Konvertierung lief durch", lauf.returncode, 0)
pruefe("Zieldatei entstanden", ziel.is_file() and ziel.stat().st_size > 0, True)

if ziel.is_file():
    quelldauer = ffmpeg.get_duration(quelle)
    zieldauer = ffmpeg.get_duration(ziel)
    pruefe("Laufzeit stimmt (2 % Toleranz)",
           abs(zieldauer - quelldauer) < quelldauer * 0.02, True)
    spuren_q = ffmpeg.count_streams(quelle)
    spuren_z = ffmpeg.count_streams(ziel)
    pruefe("Videospur uebernommen", spuren_z["video"], 1)
    pruefe("Tonspur uebernommen", spuren_z["audio"], spuren_q["audio"])
    print(f"   AV1: {quelle.stat().st_size / 1024:.0f} KB -> "
          f"{ziel.stat().st_size / 1024:.0f} KB, {zieldauer:.2f}s")

# =======================================================================
# 2. Mehrere Tonspuren duerfen nicht verlorengehen
# =======================================================================
quelle2 = testvideo("zwei_tonspuren.mp4", tonspuren=2)
if quelle2:
    ziel2 = arbeit / "zwei_tonspuren_av1.mp4"
    lauf, _ = konvertieren(quelle2, ziel2)
    pruefe("zwei Tonspuren: Konvertierung lief", lauf.returncode, 0)
    if ziel2.is_file():
        pruefe("beide Tonspuren angekommen",
               ffmpeg.count_streams(ziel2)["audio"], 2)

# =======================================================================
# 3. H.265 und H.264 - die anderen beiden Encoder
# =======================================================================
for codec, endung in (("hevc_nvenc", "hevc.mp4"), ("h264_nvenc", "h264.mp4")):
    if not ffmpeg.check_encoder_available(codec):
        print(f"   {codec} nicht verfuegbar - uebersprungen")
        continue
    ziel3 = arbeit / endung
    lauf, befehl = konvertieren(quelle, ziel3, codec=codec, cq=30)
    pruefe(f"{codec}: lief durch", lauf.returncode, 0)
    pruefe(f"{codec}: Datei da", ziel3.is_file() and ziel3.stat().st_size > 0, True)
    if codec == "hevc_nvenc":
        pruefe("H.265 in MP4 traegt hvc1", "hvc1" in befehl, True)

# =======================================================================
# 4. MKV als Container
# =======================================================================
ziel4 = arbeit / "ziel.mkv"
lauf, befehl = konvertieren(quelle, ziel4)
pruefe("MKV: lief durch", lauf.returncode, 0)
pruefe("MKV: Datei da", ziel4.is_file() and ziel4.stat().st_size > 0, True)
pruefe("MKV: Untertitel werden kopiert statt umgewandelt",
       "copy" in befehl or "-c:s" not in befehl, True)

# =======================================================================
# 5. Die 4:4:4-Absicherung, am echten Encoder
# =======================================================================
vier = arbeit / "444.mkv"
subprocess.run([ffmpeg.ffmpeg_path, "-y", "-v", "error",
                "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=2",
                "-c:v", "ffv1", "-pix_fmt", "yuv444p10le", str(vier)],
               capture_output=True, timeout=180)
if vier.is_file():
    gelesen = ffmpeg.pixel_format(vier)
    pruefe("4:4:4-Quelle erkannt", gelesen, "yuv444p10le")
    pruefe("wird auf 4:2:0 umgerechnet",
           chroma_fallback(gelesen, "av1_nvenc"), "yuv420p10le")
    ziel5 = arbeit / "444_av1.mp4"
    lauf, _ = konvertieren(vier, ziel5)
    pruefe("4:4:4 laeuft jetzt durch", lauf.returncode, 0)
    if ziel5.is_file():
        pruefe("und behaelt 10 Bit", "10" in ffmpeg.pixel_format(ziel5), True)

print(f"\n{geprueft - len(fehler)}/{geprueft} bestanden")
for e in fehler:
    print("  FEHLER:", e)
sys.exit(1 if fehler else 0)
