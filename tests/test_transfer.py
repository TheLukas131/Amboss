# -*- coding: utf-8 -*-
"""Der Transfer in die Mediathek: geprueft, abbrechbar, mit Fortschritt.

Nach dem Transfer werden lokale Ordner geloescht. Der Test belegt deshalb vor
allem, was passiert, wenn etwas schiefgeht: eine verfaelschte oder gekuerzte
Kopie darf nie unter dem endgueltigen Namen liegen, eine vorhandene aeltere
Fassung muss einen Abbruch ueberleben, und geloescht wird nur nach einem
bestandenen Vergleich.

Dazu: gescheiterte Quellen landen in _Failed, auch ohne "Quelle loeschen".

Braucht weder Grafikkarte noch (ausser fuer den letzten Abschnitt) FFmpeg.

Aufruf:  python -u tests/test_transfer.py
"""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="amboss_transfer_")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import file_transfer
from file_transfer import (
    COPYING, TRANSFER_TEMP_SUFFIX, VERIFYING, TransferCancelled, VerificationFailed,
    copy_verified,
)

fehler = []
geprueft = 0


def pruefe(bezeichnung, ist, soll):
    global geprueft
    geprueft += 1
    if ist != soll:
        fehler.append(f"{bezeichnung}: ist {ist!r}, erwartet {soll!r}")


def wirft(aktion):
    try:
        aktion()
    except BaseException as e:  # noqa: BLE001 - genau die Art interessiert
        return type(e).__name__
    return None


# Kleine Bloecke, damit "mitten in der Datei" mit kleinen Dateien pruefbar ist.
file_transfer.CHUNK_SIZE = 64 * 1024
BLOCK = file_transfer.CHUNK_SIZE

arbeit = Path(tempfile.mkdtemp(prefix="amboss_transfer_d_"))
inhalt = os.urandom(BLOCK * 5 + 1234)          # endet bewusst nicht auf einer Blockgrenze
quelle = arbeit / "quelle.mkv"
quelle.write_bytes(inhalt)
os.utime(quelle, (1_700_000_000, 1_700_000_000))


def reste(ordner):
    return [p.name for p in ordner.iterdir() if p.name.endswith(TRANSFER_TEMP_SUFFIX)]


# =======================================================================
# 1. Der Normalfall
# =======================================================================
ziel_ordner = arbeit / "ziel"
ziel_ordner.mkdir()
ziel = ziel_ordner / "film.mkv"
gemeldet = {COPYING: 0, VERIFYING: 0}
copy_verified(quelle, ziel, lambda a, n: gemeldet.__setitem__(a, gemeldet[a] + n))
pruefe("Inhalt ist identisch", ziel.read_bytes() == inhalt, True)
pruefe("Aenderungszeit uebernommen", int(ziel.stat().st_mtime), 1_700_000_000)
pruefe("keine Zwischendatei uebrig", reste(ziel_ordner), [])
pruefe("jedes Byte einmal kopiert und einmal verglichen", gemeldet,
       {COPYING: len(inhalt), VERIFYING: len(inhalt)})

leer = arbeit / "leer.mkv"
leer.write_bytes(b"")
copy_verified(leer, ziel_ordner / "leer.mkv")
pruefe("leere Datei", (ziel_ordner / "leer.mkv").stat().st_size, 0)

# =======================================================================
# 2. Abbruch mitten in der Datei: die alte Fassung bleibt
# =======================================================================
alt = b"alte Fassung, die nicht verlorengehen darf"
ziel.write_bytes(alt)
for abschnitt in (COPYING, VERIFYING):
    stand = {"n": 0, "stop": False}

    def melde(a, n, abschnitt=abschnitt, stand=stand):
        stand["n"] += n
        if a == abschnitt and stand["n"] >= BLOCK * 2:
            stand["stop"] = True

    pruefe(f"Abbruch beim Abschnitt '{abschnitt}' wird gemeldet",
           wirft(lambda: copy_verified(quelle, ziel, melde, lambda: stand["stop"])),
           "TransferCancelled")
    pruefe(f"  die alte Datei ist unberuehrt ({abschnitt})", ziel.read_bytes(), alt)
    pruefe(f"  keine Zwischendatei uebrig ({abschnitt})", reste(ziel_ordner), [])
    pruefe(f"  es wurde wirklich mittendrin abgebrochen ({abschnitt})",
           stand["n"] < len(inhalt) * 2, True)

# =======================================================================
# 3. Eine Kopie, die nicht stimmt, bekommt den Namen nicht
# =======================================================================
echt = file_transfer._copy


def verfaelscht(q, z, melde, abgebrochen):
    """Gleiche Laenge, ein Byte anders - das, was ein Groessenvergleich nicht sieht."""
    echt(q, z, melde, abgebrochen)
    daten = bytearray(z.read_bytes())
    daten[BLOCK * 3 + 7] ^= 0xFF
    z.write_bytes(daten)


def gekuerzt(q, z, melde, abgebrochen):
    echt(q, z, melde, abgebrochen)
    z.write_bytes(z.read_bytes()[:-100])


for name, kaputt in (("ein Byte anders", verfaelscht), ("gekuerzt", gekuerzt)):
    file_transfer._copy = kaputt
    try:
        pruefe(f"{name}: wird erkannt",
               wirft(lambda: copy_verified(quelle, ziel)), "VerificationFailed")
    finally:
        file_transfer._copy = echt
    pruefe(f"  {name}: die alte Datei ist unberuehrt", ziel.read_bytes(), alt)
    pruefe(f"  {name}: keine Zwischendatei uebrig", reste(ziel_ordner), [])

neu = ziel_ordner / "neu.mkv"
file_transfer._copy = verfaelscht
try:
    wirft(lambda: copy_verified(quelle, neu))
finally:
    file_transfer._copy = echt
pruefe("ohne alte Fassung entsteht gar keine Datei", neu.exists(), False)

# =======================================================================
# 4. Der Worker: ganzer Ordner, Abbruch, verfaelschte Kopie
# =======================================================================
from PyQt5.QtCore import QCoreApplication

app = QCoreApplication(sys.argv)
import workers
from models import FileStatus, MediaType, NASUploadItem, NASUploadStatus, VideoFile


def ordner(name):
    o = arbeit / "Converted" / "Filme" / name
    (o / "Extras").mkdir(parents=True)
    (o / f"{name}.mkv").write_bytes(inhalt)
    (o / "Extras" / "bonus.mkv").write_bytes(inhalt[: BLOCK * 2])
    return o


def transfer(name, vorher=None, loeschen=True):
    lokal = ordner(name)
    mediathek = arbeit / "Mediathek" / name
    mediathek.mkdir(parents=True)
    item = NASUploadItem(folder_path=lokal, name=name, media_type=MediaType.FILME,
                         target_category="Filme")
    w = workers.NASUploadWorker([item], {"Filme": str(mediathek)}, delete_after=loeschen)
    balken = []
    w.total_progress_updated.connect(balken.append)
    if vorher:
        vorher(w)
    w.run()
    app.processEvents()
    return item, lokal, mediathek / name, balken


item, lokal, drueben, balken = transfer("Gut")
pruefe("Ordner uebertragen", item.status, NASUploadStatus.FERTIG)
pruefe("beide Dateien identisch angekommen",
       ((drueben / "Gut.mkv").read_bytes() == inhalt,
        (drueben / "Extras" / "bonus.mkv").read_bytes() == inhalt[: BLOCK * 2]), (True, True))
pruefe("lokaler Ordner danach geloescht", lokal.exists(), False)
pruefe("Balken endet bei 100", balken[-1] if balken else None, 100)
pruefe("Balken laeuft nie rueckwaerts", balken, sorted(balken))


def stoppt_mittendrin(w):
    echt_kopie = workers.copy_verified

    def kopie(q, z, melde, abgebrochen):
        def melde_und_stoppe(a, n):
            melde(a, n)
            w.stop()
        return echt_kopie(q, z, melde_und_stoppe, abgebrochen)
    workers.copy_verified = kopie
    w.all_completed.connect(lambda: setattr(workers, "copy_verified", echt_kopie))


item, lokal, drueben, _ = transfer("Abbruch", stoppt_mittendrin)
workers.copy_verified = copy_verified
pruefe("Abbruch: als Fehler gemeldet", item.status, NASUploadStatus.FEHLER)
pruefe("Abbruch: lokaler Ordner bleibt", lokal.exists(), True)
pruefe("Abbruch: nichts Halbes in der Mediathek",
       [p.name for p in drueben.rglob("*") if p.is_file()], [])


def verfaelscht_alles(_w):
    file_transfer._copy = verfaelscht


item, lokal, drueben, _ = transfer("Verfaelscht", verfaelscht_alles)
file_transfer._copy = echt
pruefe("verfaelschte Kopie: als Fehler gemeldet", item.status, NASUploadStatus.FEHLER)
pruefe("verfaelschte Kopie: Grund steht dabei", "weicht" in item.error_message, True)
pruefe("verfaelschte Kopie: lokaler Ordner bleibt trotz 'lokal loeschen'", lokal.exists(), True)
pruefe("verfaelschte Kopie: liegt nicht in der Mediathek",
       [p.name for p in drueben.rglob("*") if p.is_file()], [])

# =======================================================================
# 5. Gescheiterte Quellen landen in _Failed - auch ohne "Quelle loeschen"
# =======================================================================
from ffmpeg_processor import FFmpegProcessor
from models import FAILED_FOLDER_NAME

ffmpeg = FFmpegProcessor()
if not ffmpeg.is_available():
    print("FFmpeg fehlt - Abschnitt 5 uebersprungen")
else:
    eingang = arbeit / "Downloads" / "_InProgress"
    eingang.mkdir(parents=True)
    kaputt = eingang / "kein Video.mkv"
    kaputt.write_bytes(b"das ist kein Video" * 200)
    video = VideoFile(source_path=kaputt, media_type=MediaType.FILME, movie_name="kein Video",
                      target_path=arbeit / "Downloads" / "Converted" / "kein Video.mp4")
    w = workers.ConversionWorker([video], {
        "cq": 37, "preset": "p5", "codec": "av1_nvenc", "parallel_tasks": 1,
        "normalize_audio": False, "delete_source_after_convert": False,
    }, ffmpeg)
    w.run()
    app.processEvents()
    pruefe("unlesbare Quelle scheitert", video.status, FileStatus.FEHLER)
    pruefe("und liegt danach in _Failed",
           (eingang / FAILED_FOLDER_NAME / "kein Video.mkv").is_file(), True)
    pruefe("der Pfad der Datei zeigt dorthin", video.source_path.parent.name, FAILED_FOLDER_NAME)
    pruefe("am alten Ort liegt sie nicht mehr", kaputt.exists(), False)

print(f"\n{geprueft - len(fehler)}/{geprueft} bestanden")
for e in fehler:
    print("  FEHLER:", e)
sys.stdout.flush()
os._exit(1 if fehler else 0)
