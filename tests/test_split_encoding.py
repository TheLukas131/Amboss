# -*- coding: utf-8 -*-
"""Split Frame Encoding: wann es gesetzt wird - ohne Grafikkarte pruefbar.

Eine Datei, die allein laeuft, wird auf alle Encoder-Einheiten der Karte
verteilt. Geprueft wird die Entscheidung und der Befehl, nicht der Encoder
selbst: ob die Karte dadurch schneller wird, laesst sich nur an der Karte
messen.

Aufruf:  python -u tests/test_split_encoding.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ffmpeg_processor import FFmpegProcessor, SPLIT_ENCODE_MODE, use_split_encode
from models import MediaType, VideoFile

fehler = []
geprueft = 0


def pruefe(bezeichnung, ist, soll):
    global geprueft
    geprueft += 1
    if ist != soll:
        fehler.append(f"{bezeichnung}: ist {ist!r}, erwartet {soll!r}")


# =======================================================================
# 1. Die Entscheidung
# =======================================================================
pruefe("allein, drei Einheiten, AV1", use_split_encode("av1_nvenc", 3, 1), True)
pruefe("allein, zwei Einheiten, H.265", use_split_encode("hevc_nvenc", 2, 1), True)
pruefe("H.264 kann es nicht", use_split_encode("h264_nvenc", 3, 1), False)
pruefe("eine Einheit: nichts zu verteilen", use_split_encode("av1_nvenc", 1, 1), False)
pruefe("zwei Dateien nebeneinander", use_split_encode("av1_nvenc", 3, 2), False)
pruefe("drei Dateien nebeneinander", use_split_encode("av1_nvenc", 3, 3), False)
pruefe("unbekannte Karte: versuchen", use_split_encode("av1_nvenc", None, 1), True)

# =======================================================================
# 2. Der Befehl
# =======================================================================
ffmpeg = FFmpegProcessor()
video = VideoFile(source_path=Path("Film.mkv"), media_type=MediaType.FILME, movie_name="Film")


def befehl(codec, verteilt):
    return ffmpeg.build_command(video, 37, "p5", False, codec, Path("Film.mp4"),
                                [], "yuv420p", verteilt)


mit = befehl("av1_nvenc", True)
pruefe("Option steht im Befehl", "-split_encode_mode" in mit, True)
if "-split_encode_mode" in mit:
    pruefe("mit dem vorgesehenen Wert",
           mit[mit.index("-split_encode_mode") + 1], SPLIT_ENCODE_MODE)
    pruefe("vor der Ausgabedatei", mit.index("-split_encode_mode") < len(mit) - 1, True)
pruefe("ohne Wunsch keine Option", "-split_encode_mode" in befehl("av1_nvenc", False), False)
pruefe("bei H.264 nie", "-split_encode_mode" in befehl("h264_nvenc", True), False)
pruefe("H.264 wird gar nicht erst gefragt", ffmpeg.supports_split_encode("h264_nvenc"), False)

print(f"\n{geprueft - len(fehler)}/{geprueft} bestanden")
for e in fehler:
    print("  FEHLER:", e)
sys.exit(1 if fehler else 0)
