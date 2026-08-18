"""Worker-Threads für Konvertierung und NAS-Upload.

Enthält gegenüber der alten Version mehrere Korrekturen:
- Encodiert in eine temporäre Datei und benennt erst bei Erfolg atomar um,
  damit ein Absturz/Abbruch nie eine kaputte Datei am Zielpfad hinterlässt,
  die spätere Läufe fälschlich als "schon konvertiert" überspringen würden.
- Prüft den Stop-Flag ganz am Anfang jeder Task, bevor irgendetwas passiert -
  dadurch starten in der Warteschlange befindliche, aber noch nicht
  begonnene Konvertierungen nach "Stoppen" gar nicht erst.
- Liest stderr nur einmal (Ringpuffer) statt es nach dem Verbrauch für die
  Fehlermeldung erneut zu lesen (das lieferte vorher immer einen leeren String).
- Löscht die Quelldatei/den lokalen NAS-Ordner nur, nachdem der Erfolg der
  Konvertierung bzw. der vollständige Kopiervorgang verifiziert wurde.
"""

import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

from PyQt5.QtCore import QThread, pyqtSignal

from ffmpeg_processor import FFmpegProcessor, chroma_fallback
from i18n import tr
from run_lock import held_by_other
from models import (
    FAILED_FOLDER_NAME, INPROGRESS_FOLDER_NAME, VIDEO_EXTENSIONS, FileStatus, NASUploadItem, NASUploadStatus, VideoFile,
    cq_maximum_for, preset_bucket_for,
)

_CREATIONFLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
_TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+\.?\d*)")

_PROCESS_SUSPEND_RESUME = 0x0800


def _set_process_suspended(pid: int, suspend: bool) -> bool:
    """Hält einen laufenden Prozess an bzw. lässt ihn weiterlaufen (Windows).

    Ohne das war "Pause" praktisch wirkungslos: pausiert wurde nur die
    stderr-Leseschleife, ffmpeg selbst encodierte weiter, bis irgendwann die
    stderr-Pipe volllief (64 KB, bei ffmpeg-Fortschrittsausgabe rund eine Minute).
    Gibt False zurück, wenn das Anhalten nicht möglich war - dann bleibt es beim
    alten Verhalten, aber nichts geht kaputt."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(_PROCESS_SUSPEND_RESUME, False, pid)
        if not handle:
            return False
        try:
            fn = ctypes.windll.ntdll.NtSuspendProcess if suspend else ctypes.windll.ntdll.NtResumeProcess
            return fn(handle) == 0
        finally:
            kernel32.CloseHandle(handle)
    except (OSError, AttributeError):
        return False


# Windows-Flags für SetThreadExecutionState.
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


def _keep_system_awake(active: bool) -> bool:
    """Hindert Windows am Einschlafen, solange gearbeitet wird.

    Ein Stapel läuft schnell mehrere Stunden und typischerweise nachts. Schläft
    der Rechner dabei ein, steht die Konvertierung bis jemand ihn weckt - und
    ein eingestelltes "danach herunterfahren" löst nie aus. Der Bildschirm wird
    bewusst NICHT wachgehalten (kein ES_DISPLAY_REQUIRED): er darf ausgehen,
    nur schlafen legen soll sich der Rechner nicht.

    Gibt False zurück, wenn das nicht möglich war - dann bleibt es beim
    bisherigen Verhalten, kaputt geht nichts."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        flags = _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED if active else _ES_CONTINUOUS
        return ctypes.windll.kernel32.SetThreadExecutionState(flags) != 0
    except (OSError, AttributeError):
        return False


def _erklaere_fehler(ffmpeg_ausgabe: str, ziel: Optional[Path]) -> str:
    """Macht aus einer FFmpeg-Fehlerausgabe eine Erklärung, mit der man etwas
    anfangen kann.

    Die rohe Ausgabe beginnt mit dem Versionsbanner und Bibliotheksnummern; in
    der Spalte "Fehler" der Oberfläche stand davon dann eine Zeile wie
    "libavformat 61. 7.100" - also nichts, was weiterhilft. Für die Fälle, die
    tatsächlich vorkommen, gibt es hier einen Satz samt Ausweg."""
    text = ffmpeg_ausgabe.lower()
    ist_mp4 = ziel is not None and ziel.suffix.lower() == ".mp4"

    if ist_mp4 and ("experimental" in text or "could not find tag" in text):
        return tr("Diese Tonspur passt nicht in MP4 (z.B. TrueHD oder DTS-HD MA). "
                  "Mit MKV als Container bleibt sie erhalten.")
    if "no capable devices found" in text:
        # Die gängigen Fälle (4:4:4, 4:2:2) rechnet Amboss inzwischen selbst um,
        # siehe ffmpeg_processor.CHROMA_FALLBACK. Bleibt die Meldung trotzdem,
        # liegt es an einem Format, das dort nicht steht, oder an der Karte
        # selbst - deshalb hier kein Verweis mehr auf die Farbabtastung, der
        # in die falsche Richtung schicken würde.
        return tr("Die Grafikkarte unterstützt diese Kombination von Codec und "
                  "Videoformat nicht. Ein anderer Codec (H.265) kommt oft damit "
                  "zurecht.")
    if "no space left" in text:
        return tr("Kein Speicherplatz mehr auf dem Ziellaufwerk.")
    if "permission denied" in text:
        return tr("Kein Schreibzugriff auf den Zielordner.")

    # Unbekannter Fall: die letzten Zeilen zeigen, das Banner nicht.
    zeilen = [z.strip() for z in ffmpeg_ausgabe.strip().splitlines() if z.strip()]
    nutzbar = [z for z in zeilen
               if not z.startswith(("ffmpeg version", "built with", "configuration:", "lib"))]
    return (nutzbar[-1] if nutzbar else (zeilen[-1] if zeilen else tr("Unbekannter Fehler")))[:300]


class ConversionWorker(QThread):
    """Worker-Thread für die Videokonvertierung."""

    progress_updated = pyqtSignal(int, int, str)  # file_index, progress, message
    file_completed = pyqtSignal(int, bool, str)   # file_index, success, message
    log_message = pyqtSignal(str)
    all_completed = pyqtSignal()
    file_started = pyqtSignal(int)

    def __init__(self, videos: List[VideoFile], settings: dict):
        super().__init__()
        self.videos = videos
        self.settings = settings
        self.ffmpeg = FFmpegProcessor()
        self._stop_requested = False
        self._pause_requested = False
        self._lock = threading.Lock()
        self._processes: Dict[int, subprocess.Popen] = {}
        # Erfolgreich konvertierte und geprüfte Dateien; gelöscht wird erst am
        # Ende des Laufs, siehe _delete_pending_sources.
        self._pending_source_deletions: List[VideoFile] = []

    def stop(self):
        self._stop_requested = True
        self._pause_requested = False
        with self._lock:
            for proc in self._processes.values():
                try:
                    # Falls gerade pausiert: erst fortsetzen, dann beenden - ein
                    # angehaltener Prozess soll nie hängenbleiben.
                    _set_process_suspended(proc.pid, False)
                    proc.terminate()
                except OSError as e:
                    self.log_message.emit(f"Could not terminate process: {e}")

    def pause(self):
        self._pause_requested = True

    def resume(self):
        self._pause_requested = False

    def is_paused(self) -> bool:
        return self._pause_requested

    def run(self):
        # Nichts darf aus run() entkommen: eine Ausnahme in einer QThread-Methode
        # führt bei PyQt5 zu qFatal() und damit zum sofortigen Prozessabbruch
        # ohne jede Meldung (siehe crash_logging.py).
        try:
            _keep_system_awake(True)
            max_workers = self.settings.get("parallel_tasks", 3)

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(self._process_video, idx, video): idx
                    for idx, video in enumerate(self.videos)
                    if video.status != FileStatus.UEBERSPRUNGEN
                }
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        idx = futures[future]
                        self.log_message.emit(f"Error on file {idx}: {e}")
        except Exception as e:
            self.log_message.emit(f"ERROR: fatal error in the conversion thread: {e}\n{traceback.format_exc()}")
        finally:
            # Erst hier, wenn das Ergebnis des gesamten Laufs feststeht.
            try:
                self._delete_pending_sources()
            except Exception as e:  # noqa: BLE001
                self.log_message.emit(f"Error while cleaning up source files: {e}")
            # Die Schlafsperre unbedingt wieder freigeben - auch nach einem
            # Abbruch, sonst bliebe der Rechner bis zum Beenden der App wach.
            _keep_system_awake(False)
            self.all_completed.emit()

    def _wait_while_paused(self, process: Optional[subprocess.Popen] = None):
        """Blockiert, solange pausiert ist. Läuft dabei bereits ein ffmpeg-Prozess,
        wird der für die Dauer der Pause echt angehalten und danach fortgesetzt."""
        if not self._pause_requested:
            return

        suspended = False
        if process is not None and process.poll() is None:
            suspended = _set_process_suspended(process.pid, True)

        try:
            while self._pause_requested and not self._stop_requested:
                time.sleep(0.2)
        finally:
            if suspended:
                # Auch beim Stoppen zuerst fortsetzen - ein angehaltener Prozess
                # soll nie als Waise zurückbleiben.
                _set_process_suspended(process.pid, False)

    def _process_video(self, idx: int, video: VideoFile):
        # Sofortiger Ausstieg, falls "Stoppen" gedrückt wurde, während diese Task
        # noch in der ThreadPoolExecutor-Warteschlange auf einen freien Slot wartete.
        if self._stop_requested:
            return
        self._wait_while_paused()
        if self._stop_requested:
            return

        try:
            video.conversion_start_time = time.time()
            self.file_started.emit(idx)
            self.progress_updated.emit(idx, 0, tr("Starte Konvertierung..."))

            video.target_path.parent.mkdir(parents=True, exist_ok=True)

            if video.target_path.exists():
                video.status = FileStatus.UEBERSPRUNGEN
                self.file_completed.emit(idx, True, "Datei existiert bereits")
                return

            if self.settings.get("use_separate_presets"):
                bucket = preset_bucket_for(video.media_type)
                cq = self.settings[f"cq_{bucket}"]
                preset = self.settings[f"preset_{bucket}"]
                codec = self.settings[f"codec_{bucket}"]
            else:
                cq = self.settings["cq"]
                preset = self.settings["preset"]
                codec = self.settings.get("codec", "av1_nvenc")

            # Ausnahme je Datei aus der Verlustvorschau - sie geht sowohl der
            # globalen Einstellung als auch dem Bucket vor.
            if video.codec_override:
                codec = video.codec_override
                # Und der CQ-Wert muss in die Skala des neuen Codecs passen: AV1
                # rechnet bis 63, H.265 und H.264 nur bis 51. Global fängt der
                # Regler das ab, eine Ausnahme je Datei umgeht ihn - ohne diesen
                # Deckel entstünde ein Wert, den der Encoder ablehnt.
                cq = min(cq, cq_maximum_for(codec))

            temp_path = video.target_path.with_name(
                f".{video.target_path.stem}.tmp{video.target_path.suffix}"
            )

            subtitle_indices = self.ffmpeg.get_text_subtitle_indices(video.source_path)
            # Beim Scannen wurde die Datei schon mit ffprobe gelesen; das
            # Pixelformat steht dort drin. Kein Grund, dafür einen zweiten
            # Prozess pro Datei zu starten - über ein Netzlaufwerk kostet jeder
            # davon spürbar Zeit. Gleiche Überlegung wie bei der Laufzeit weiter
            # unten.
            source_pixel_format = (
                (video.source_metadata.pixel_format if video.source_metadata else "")
                or self.ffmpeg.pixel_format(video.source_path)
            )
            cmd = self.ffmpeg.build_command(
                video, cq, preset, self.settings["normalize_audio"], codec, temp_path,
                subtitle_indices, source_pixel_format,
            )

            # Womit die Ausgabe später verglichen wird. Muss vor dem Encode
            # feststehen: danach ist die Quelle unter Umständen schon verschoben.
            # Video ist immer genau eine Spur ('-map 0:v:0'), Untertitel nur die
            # textbasierten - Bitmap-Formate werden bewusst nicht übernommen.
            expected_streams = {
                "video": 1,
                "audio": self.ffmpeg.count_streams(video.source_path)["audio"],
                "subtitle": len(subtitle_indices),
            }

            self.log_message.emit(
                f"[{video.source_path.name}] settings: CQ={cq}, preset={preset}, codec={codec}"
            )
            # Eine Umrechnung der Chroma-Unterabtastung veraendert das Bild und
            # gehoert deshalb ins Protokoll, nicht nur in die Befehlszeile.
            chroma_ersatz = chroma_fallback(source_pixel_format, codec)
            if chroma_ersatz:
                self.log_message.emit(
                    f"[{video.source_path.name}] source is {source_pixel_format}, which "
                    f"{codec} cannot encode - converting chroma to {chroma_ersatz} "
                    f"(bit depth kept)"
                )
            self.log_message.emit(f"FFmpeg command: {' '.join(cmd)}")

            # Die Dauer wurde beim Scannen schon per ffprobe ermittelt - kein Grund,
            # dafür einen zweiten Prozess pro Datei zu starten.
            duration = (
                video.source_metadata.duration_seconds
                if video.source_metadata and video.source_metadata.duration_seconds
                else self.ffmpeg.get_duration(video.source_path)
            )

            process = subprocess.Popen(
                cmd,
                # Nicht PIPE: stdout wird nirgends gelesen, ein volllaufender
                # Puffer würde ffmpeg dauerhaft blockieren.
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                creationflags=_CREATIONFLAGS,
            )

            with self._lock:
                self._processes[idx] = process

            stderr_tail = deque(maxlen=40)
            for line in process.stderr:
                stderr_tail.append(line)

                if self._stop_requested:
                    process.terminate()
                    break

                self._wait_while_paused(process)

                time_match = _TIME_RE.search(line)
                if time_match:
                    h, m, s = time_match.groups()
                    current_time = int(h) * 3600 + int(m) * 60 + float(s)
                    if duration > 0:
                        progress = min(int((current_time / duration) * 100), 99)
                        self.progress_updated.emit(idx, progress, tr("Konvertiere... {progress}%").format(progress=progress))

                if "fps=" in line:
                    self.log_message.emit(f"[{video.source_path.name}] {line.strip()}")

            process.wait()

            with self._lock:
                self._processes.pop(idx, None)

            video.conversion_end_time = time.time()

            if self._stop_requested:
                video.status = FileStatus.WARTEND
                self._cleanup_temp(temp_path)
                self.file_completed.emit(idx, False, "Abgebrochen")
                return

            if process.returncode == 0 and temp_path.exists():
                temp_path.replace(video.target_path)

                complete, reason = self._verify_output(video, duration, expected_streams)
                if not complete:
                    # Die unvollständige Zieldatei muss weg: bliebe sie liegen,
                    # würde der nächste Lauf sie als "schon konvertiert"
                    # überspringen und der Schaden wäre dauerhaft.
                    video.status = FileStatus.FEHLER
                    video.error_message = f"Überprüfung fehlgeschlagen: {reason}"
                    self._cleanup_temp(video.target_path)
                    self.file_completed.emit(idx, False, f"Überprüfung fehlgeschlagen: {reason}")
                    self.log_message.emit(
                        f"WARNING: [{video.source_path.name}] output discarded - {reason}. Source file kept."
                    )
                    return

                video.status = FileStatus.FERTIG
                video.new_size = video.target_path.stat().st_size
                self.progress_updated.emit(idx, 100, tr("Fertig"))
                self.file_completed.emit(idx, True, "Erfolgreich konvertiert")

                # Nicht sofort löschen - erst wenn der komplette Lauf sauber
                # durch ist (siehe _delete_pending_sources).
                if self.settings.get("delete_source_after_convert"):
                    with self._lock:
                        self._pending_source_deletions.append(video)
            else:
                video.status = FileStatus.FEHLER
                error_output = "".join(stderr_tail) or "Unbekannter Fehler"
                video.error_message = _erklaere_fehler(error_output, video.target_path)
                self._cleanup_temp(temp_path)
                self.file_completed.emit(idx, False, f"FFmpeg Fehler: {process.returncode}")
                self.log_message.emit(f"ERROR: {error_output}")

        except Exception as e:
            video.status = FileStatus.FEHLER
            video.error_message = str(e)
            self.file_completed.emit(idx, False, str(e))
            self.log_message.emit(f"ERROR: {e}")

    def _verify_output(self, video: VideoFile, source_duration: float,
                       expected_streams: Optional[Dict[str, int]] = None):
        """Prüft, ob die Zieldatei wirklich vollständig ist - nicht nur, ob sie
        existiert und nicht leer ist.

        Zwei Dinge werden verglichen, und beide sind nötig:

        Die **Laufzeit**, weil ein abgebrochener Encode (Absturz, Stromausfall,
        voller Datenträger) eine abspielbare, aber verkürzte Datei hinterlässt.
        Größe > 0 allein hätte die durchgewinkt.

        Die **Zahl der Spuren**, weil eine Datei mit korrekter Laufzeit trotzdem
        unvollständig sein kann: fehlt der '-map'-Parameter, wählt ffmpeg pro
        Streamtyp nur einen aus, und die zweite Tonspur verschwindet lautlos.
        Genau das ist in diesem Projekt schon einmal passiert. Die Laufzeit war
        dabei tadellos - erst danach wird die Quelldatei gelöscht."""
        target = video.target_path
        try:
            if not target.exists():
                return False, "Zieldatei fehlt"
            if target.stat().st_size == 0:
                return False, "Zieldatei ist leer"
        except OSError as e:
            return False, f"Zieldatei nicht lesbar ({e})"

        if source_duration <= 0:
            # Ohne bekannte Quelldauer ist kein Vergleich möglich; dann bleibt es
            # bei der schwachen Prüfung, aber es wird nichts gelöscht.
            return False, "Laufzeit der Quelldatei unbekannt - keine Prüfung möglich"

        target_duration = self.ffmpeg.get_duration(target)
        if target_duration <= 0:
            return False, "Laufzeit der Zieldatei nicht lesbar"

        # 2% Toleranz: je nach Keyframe-Lage weicht die Ausgabe um Sekundenbruchteile ab.
        if target_duration < source_duration * 0.98:
            return False, (
                f"Zieldatei zu kurz ({target_duration:.0f}s statt {source_duration:.0f}s)"
            )

        if expected_streams:
            actual = self.ffmpeg.count_streams(target)
            for kind, label in (("video", "Videospur"), ("audio", "Tonspur"),
                                ("subtitle", "Untertitelspur")):
                erwartet, vorhanden = expected_streams.get(kind, 0), actual.get(kind, 0)
                if vorhanden < erwartet:
                    return False, (
                        f"{label}en unvollständig ({vorhanden} statt {erwartet})"
                    )

        return True, ""

    def _delete_pending_sources(self):
        """Löscht die Quelldateien am Ende des Laufs - je Datei entschieden.

        Gelöscht wird nur, was nachweislich in Ordnung ist: die Zieldatei muss
        die Prüfung auf Laufzeit UND Streamzahl bestanden haben, erst dann landet
        die Quelle überhaupt in dieser Liste.

        Früher galt alles-oder-nichts: eine einzige gescheiterte Datei liess
        sämtliche Quellen liegen. Bei einer Staffel mit 24 Folgen, von denen eine
        fehlschlägt, blieben damit 24 Originale zurück, obwohl 23 davon fertig
        und geprüft in der Mediathek lagen. Die feinere Regel ist möglich, weil
        die Prüfung inzwischen belastbar ist - eine Datei, die durchkommt, ist
        vollständig, und eine, die es nicht tut, wird gar nicht erst
        vorgemerkt.

        Ein Abbruch bleibt die Ausnahme: dann wird nichts gelöscht, weil
        unklar ist, was noch mittendrin war."""
        with self._lock:
            pending = list(self._pending_source_deletions)
            self._pending_source_deletions.clear()

        if not pending:
            return

        if self._stop_requested:
            self.log_message.emit(
                f"No source file deleted (aborted) - "
                f"{len(pending)} source file(s) kept."
            )
            return

        deleted = 0
        for video in pending:
            try:
                video.source_path.unlink()
                deleted += 1
                self.log_message.emit(f"[{video.source_path.name}] source file deleted")
            except OSError as e:
                self.log_message.emit(
                    f"[{video.source_path.name}] source file could not be deleted: {e}"
                )
        self.log_message.emit(f"Deleted {deleted} verified source file(s)")
        self._set_aside_failed_sources()

    def _set_aside_failed_sources(self):
        """Legt die Quellen gescheiterter Dateien in einen eigenen Ordner.

        Nachdem die geprüften Quellen gelöscht sind, blieben die gescheiterten
        sonst zwischen leeren Ordnern zurück und man müsste suchen, welche es
        waren. In `_InProgress/_Failed/` steht danach genau das, was noch
        Aufmerksamkeit braucht - bei 24 Folgen, von denen eine misslang, ist das
        eine Datei statt vierundzwanzig."""
        gescheitert = [v for v in self.videos if v.status == FileStatus.FEHLER]
        if not gescheitert or self._stop_requested:
            return

        verschoben = 0
        for video in gescheitert:
            quelle = video.source_path
            if not quelle.exists():
                continue
            # Neben die Quelldatei, nicht in den Zielordner: die Datei ist ja
            # nicht konvertiert, sie gehört weiterhin zum Eingang.
            ziel_ordner = quelle.parent / FAILED_FOLDER_NAME
            if quelle.parent.name == FAILED_FOLDER_NAME:
                continue  # liegt schon dort, aus einem früheren Lauf
            try:
                ziel_ordner.mkdir(parents=True, exist_ok=True)
                ziel = ziel_ordner / quelle.name
                # Nicht überschreiben, falls aus einem früheren Lauf gleichnamig.
                zaehler = 1
                while ziel.exists():
                    ziel = ziel_ordner / f"{quelle.stem} ({zaehler}){quelle.suffix}"
                    zaehler += 1
                shutil.move(str(quelle), str(ziel))
                video.source_path = ziel
                verschoben += 1
            except OSError as e:
                self.log_message.emit(
                    f"[{quelle.name}] could not be moved to {FAILED_FOLDER_NAME}: {e}"
                )

        if verschoben:
            self.log_message.emit(
                f"Moved {verschoben} failed source file(s) to {FAILED_FOLDER_NAME}/"
            )

    @staticmethod
    def _cleanup_temp(temp_path: Path):
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass


class ScanResult:
    """Ergebnis eines Scans, gesammelt im Worker und am Stück übergeben."""

    def __init__(self):
        self.videos: List[VideoFile] = []
        self.redundant_duplicates: List[Path] = []
        self.season_pattern: str = ""
        self.ignored_count: int = 0
        self.log_lines: List[str] = []


class ScanWorker(QThread):
    """Durchsucht den Quellordner - abseits des Oberflächen-Threads.

    Das war vorher der Grund für ein rund zehn Sekunden eingefrorenes Fenster:
    der Scan lief mitten im Oberflächen-Thread, und die teuren Schritte liegen
    alle auf dem Netzlaufwerk - die Staffel-Benennung aus der Mediathek ablesen,
    den Zielordner nach Resten durchsuchen, pro Datei prüfen ob das Ziel schon
    existiert. Solange Qt darauf wartet, kann es nichts zeichnen; ein
    Ladesymbol hätte sich nicht einmal gedreht.
    """

    progress = pyqtSignal(int, int, str)   # erledigt, gesamt, aktueller Schritt
    log_message = pyqtSignal(str)
    finished_ok = pyqtSignal(object)       # ScanResult
    failed = pyqtSignal(str)

    def __init__(self, source_path: Path, target_path: Path, rename_enabled: bool,
                 enabled_categories: List[str], category_folders: Dict[str, str],
                 configured_season_pattern: str, ffmpeg: FFmpegProcessor,
                 ignored_folders: List[Path], container: str = "mp4", parent=None):
        super().__init__(parent)
        self.source_path = source_path
        self.target_path = target_path
        self.rename_enabled = rename_enabled
        self.enabled_categories = enabled_categories
        self.category_folders = category_folders
        self.configured_season_pattern = configured_season_pattern
        self.ffmpeg = ffmpeg
        self.ignored_folders = ignored_folders
        self.container = container
        self._stop_requested = False

    def stop(self):
        self._stop_requested = True

    def run(self):
        # Wie bei den anderen Workern: aus run() darf keine Ausnahme entkommen,
        # sonst bricht PyQt5 den Prozess ohne Meldung ab.
        try:
            result = self._scan()
            if not self._stop_requested:
                self.finished_ok.emit(result)
        except Exception as error:  # noqa: BLE001
            self.log_message.emit(
                f"ERROR: fatal error while scanning: {error}\n{traceback.format_exc()}")
            self.failed.emit(str(error))

    def _scan(self) -> ScanResult:
        from duplicate_detector import filter_duplicate_downloads
        from library_layout import NUMERIC_ONLY, detect_season_pattern
        from models import fold_to_enabled
        from path_generator import PathGenerator
        from pattern_matcher import PatternMatcher

        result = ScanResult()

        self.progress.emit(0, 0, "Dateien suchen")
        # os.walk statt rglob: es liefert Datei- und Ordnernamen getrennt, aus
        # dem Verzeichniseintrag selbst. rglob("*") müsste für jeden Treffer
        # zusätzlich nachfragen, ob er eine Datei ist - auf einem Netzlaufwerk
        # eine eigene Anfrage pro Eintrag. Ein rglob je Endung wäre noch
        # schlechter: zwölf Durchläufe durch denselben Baum (gemessen 613 ms
        # gegen 27 ms).
        erlaubt = {e.lower() for e in VIDEO_EXTENSIONS}

        # Arbeitet ein anderer Amboss gerade in diesem Quellordner, bleiben
        # dessen Dateien in _InProgress aussen vor - sonst griffen zwei Läufe
        # nach denselben. Der Unterordner mit den gescheiterten Dateien wird
        # trotzdem gelesen, damit man sie erneut versuchen kann.
        fremder_lauf = held_by_other(self.source_path)
        laufend = (self.source_path / INPROGRESS_FOLDER_NAME).resolve()
        fehler_ordner = (laufend / FAILED_FOLDER_NAME).resolve()

        def gesperrt(ordner: Path) -> bool:
            if fremder_lauf is None:
                return False
            try:
                aufgeloest = ordner.resolve()
            except OSError:
                return False
            if aufgeloest == fehler_ordner or fehler_ordner in aufgeloest.parents:
                return False
            return aufgeloest == laufend or laufend in aufgeloest.parents

        files = []
        uebersprungen = 0
        for wurzel, _, dateinamen in os.walk(self.source_path):
            ordner = Path(wurzel)
            if gesperrt(ordner):
                uebersprungen += sum(1 for n in dateinamen
                                     if os.path.splitext(n)[1].lower() in erlaubt)
                continue
            for name in dateinamen:
                if os.path.splitext(name)[1].lower() in erlaubt:
                    files.append(ordner / name)
        if uebersprungen:
            result.log_lines.append(
                f"Skipped {uebersprungen} file(s) - another Amboss "
                f"(process {fremder_lauf}) is working on them.")
        gefunden = len(files)

        def ist_ausgenommen(pfad: Path) -> bool:
            try:
                aufgeloest = pfad.resolve()
            except OSError:
                return False
            for ordner in self.ignored_folders:
                try:
                    aufgeloest.relative_to(ordner)
                    return True
                except ValueError:
                    continue
            return False

        files = [f for f in files if not ist_ausgenommen(f)]
        result.ignored_count = gefunden - len(files)
        if self._stop_requested:
            return result

        files, duplikat_zeilen, result.redundant_duplicates = filter_duplicate_downloads(files)
        result.log_lines.extend(duplikat_zeilen)

        # Die Staffel-Benennung aus der Mediathek abzulesen ist der teuerste
        # Einzelschritt - bis zu 60 Serienordner je Kategorie, jeder einzeln
        # aufgelistet. Deshalb steht er hier und nicht im Oberflächen-Thread.
        if self.configured_season_pattern:
            result.season_pattern = self.configured_season_pattern
        else:
            self.progress.emit(0, len(files), "Mediathek lesen")
            begonnen = time.perf_counter()
            erkannt = detect_season_pattern(self.category_folders.values())
            result.season_pattern = erkannt or NUMERIC_ONLY
            dauer = time.perf_counter() - begonnen
            if erkannt:
                result.log_lines.append(
                    f"Season naming taken from the library: '{erkannt}' "
                    f"({dauer:.1f}s) - remembered from now on")
            else:
                result.log_lines.append(
                    f"No season naming found in the library ({dauer:.1f}s)")
        if self._stop_requested:
            return result

        gesamt = len(files)
        for nummer, datei in enumerate(files, start=1):
            if self._stop_requested:
                return result
            self.progress.emit(nummer, gesamt, datei.name)

            video = PatternMatcher.analyze(datei)
            video.media_type = fold_to_enabled(video.media_type, self.enabled_categories)
            video.target_path = PathGenerator.generate(
                video, self.target_path, self.rename_enabled,
                self.category_folders, result.season_pattern, self.container)

            if video.target_path.exists():
                video.status = FileStatus.UEBERSPRUNGEN

            result.videos.append(video)
            result.log_lines.append(f"  -> {datei.name} [{video.media_type.value}]")

        if result.videos and not self._stop_requested:
            self.progress.emit(gesamt, gesamt, "Videodaten lesen")
            with ThreadPoolExecutor(max_workers=8) as executor:
                for video, metadata in zip(
                    result.videos,
                    executor.map(self.ffmpeg.get_video_metadata,
                                 [v.source_path for v in result.videos]),
                ):
                    video.source_metadata = metadata

        PathGenerator.resolve_collisions(result.videos)
        return result


class NASUploadWorker(QThread):
    """Worker-Thread für das Verschieben von Medien auf NAS."""

    progress_updated = pyqtSignal(int, int, str)
    item_completed = pyqtSignal(int, bool, str)
    log_message = pyqtSignal(str)
    all_completed = pyqtSignal()
    total_progress_updated = pyqtSignal(int)

    def __init__(self, items: List[NASUploadItem], category_folders: Dict[str, str],
                 delete_after: bool = False):
        super().__init__()
        self.items = items
        # Kategorie -> vollständiger Zielordner. Ein leerer Eintrag heißt: diese
        # Kategorie wird nicht benutzt, entsprechende Medien werden übersprungen.
        self.category_folders = category_folders
        self.delete_after = delete_after
        self._stop_requested = False
        # Erfolgreich übertragene und geprüfte Ordner; gelöscht wird erst am
        # Ende des Uploads, siehe _delete_pending_folders.
        self._pending_local_deletions: List[NASUploadItem] = []

    def stop(self):
        self._stop_requested = True

    def run(self):
        # Siehe ConversionWorker.run(): aus einer QThread-Methode darf keine
        # Ausnahme entkommen, sonst bricht PyQt5 den Prozess hart ab.
        try:
            # Auch das Verschieben soll nicht vom Ruhezustand unterbrochen werden -
            # über Netzlaufwerke dauert es bei großen Mediatheken oft länger als
            # das Konvertieren selbst.
            _keep_system_awake(True)
            # Byte-gewichtet statt Item-gewichtet: bei sehr unterschiedlich großen
            # Ordnern (z.B. 2 kleine Serien + 1 riesiger Film) wäre "2 von 3 Items
            # fertig" = 66% völlig irreführend, obwohl kaum Daten geflossen sind.
            self._total_bytes = max(sum(item.total_size for item in self.items), 1)
            self._bytes_copied = 0

            for idx, item in enumerate(self.items):
                if self._stop_requested:
                    break

                if item.status in (NASUploadStatus.FERTIG, NASUploadStatus.UEBERSPRUNGEN):
                    self._bytes_copied += item.total_size
                    self.total_progress_updated.emit(int((self._bytes_copied / self._total_bytes) * 100))
                    continue

                self._process_item(idx, item)
        except Exception as e:
            self.log_message.emit(f"ERROR: fatal error in the transfer thread: {e}\n{traceback.format_exc()}")
        finally:
            try:
                self._delete_pending_folders()
            except Exception as e:  # noqa: BLE001
                self.log_message.emit(f"Error while cleaning up local folders: {e}")
            _keep_system_awake(False)
            self.all_completed.emit()

    def _process_item(self, idx: int, item: NASUploadItem):
        try:
            self.progress_updated.emit(idx, 0, tr("Prüfe Zielordner..."))

            category_root = (self.category_folders.get(item.target_category) or "").strip()
            if not category_root:
                raise ValueError(
                    f"Für die Kategorie '{item.target_category}' ist kein Zielordner eingestellt"
                )

            base = Path(category_root)
            if not base.exists():
                raise ConnectionError(f"Zielordner nicht erreichbar: {category_root}")

            target_path = base / item.name
            self.progress_updated.emit(idx, 10, tr("Ziel: {path}").format(path=target_path))
            self.log_message.emit(f"[{item.name}] moving to: {target_path}")

            source_file_count = sum(1 for f in item.folder_path.rglob("*") if f.is_file())

            # Nichts zu übertragen ist kein Erfolg.
            #
            # Die ganze Prüfung unten ist quellenrelativ: gezählt wird, ob jede
            # Quelldatei am Ziel angekommen ist. Bei null Quelldateien ist das
            # trivial erfüllt - 0 kopiert von 0 erwartet, und _verify_transfer
            # findet nichts zu beanstanden, weil es nichts zu prüfen gibt. Ein
            # verschwundener oder unlesbarer Ordner wurde damit als "Fertig"
            # gemeldet und bei aktivem lokalen Löschen auch noch abgeräumt.
            if source_file_count == 0:
                item.status = NASUploadStatus.FEHLER
                item.error_message = "Quellordner ist leer oder nicht mehr lesbar"
                self.item_completed.emit(idx, False, "Quellordner leer oder verschwunden")
                self.log_message.emit(
                    f"[{item.name}] ERROR: source folder is empty or gone - "
                    f"nothing was transferred"
                )
                return

            if target_path.exists():
                self.progress_updated.emit(idx, 15, tr("Zielordner existiert - führe zusammen..."))
                self.log_message.emit(f"[{item.name}] target folder exists - merging")
                copied = self._merge_folders(item.folder_path, target_path, idx)
            else:
                self.progress_updated.emit(idx, 20, tr("Kopiere Ordner..."))
                copied = self._copy_folder(item.folder_path, target_path, idx)

            # Nur löschen, wenn die Übertragung nachweislich vollständig war -
            # bei Abbruch/Fehler bleibt die lokale Kopie die einzig sichere.
            if self._stop_requested or copied < source_file_count:
                item.status = NASUploadStatus.FEHLER
                item.error_message = "Übertragung abgebrochen oder unvollständig"
                self.item_completed.emit(idx, False, "Abgebrochen - lokaler Ordner NICHT gelöscht")
                self.log_message.emit(
                    f"[{item.name}] transfer incomplete ({copied}/{source_file_count} files) - nothing deleted"
                )
                return

            self.progress_updated.emit(idx, 92, tr("Prüfe Übertragung..."))
            verified, reason = self._verify_transfer(item.folder_path, target_path)
            if not verified:
                item.status = NASUploadStatus.FEHLER
                item.error_message = f"Überprüfung fehlgeschlagen: {reason}"
                self.item_completed.emit(idx, False, f"Überprüfung fehlgeschlagen - {reason}")
                self.log_message.emit(
                    f"[{item.name}] verification failed ({reason}) - local folder kept"
                )
                return

            item.status = NASUploadStatus.FERTIG
            self.progress_updated.emit(idx, 100, tr("Fertig"))
            self.item_completed.emit(idx, True, "Erfolgreich verschoben")

            # Löschen erst am Ende des kompletten Uploads (siehe _delete_pending_folders).
            if self.delete_after:
                self._pending_local_deletions.append(item)

        except Exception as e:
            item.status = NASUploadStatus.FEHLER
            item.error_message = str(e)
            self.progress_updated.emit(idx, 0, tr("Fehler: {reason}").format(reason=str(e)[:50]))
            self.item_completed.emit(idx, False, str(e))
            self.log_message.emit(f"[{item.name}] ERROR: {e}")

    def _verify_transfer(self, source: Path, target: Path):
        """Vergleicht jede Quelldatei byteweise-genau mit ihrem Gegenstück auf dem NAS.

        Der bisherige Vergleich zählte nur Dateien. Eine über SMB abgebrochene
        oder gekürzt geschriebene Datei hätte diese Zählung bestanden - und der
        lokale Ordner wäre danach gelöscht worden."""
        try:
            for src_file in source.rglob("*"):
                if not src_file.is_file():
                    continue
                dest_file = target / src_file.relative_to(source)
                if not dest_file.exists():
                    return False, f"fehlt auf dem NAS: {src_file.name}"
                if dest_file.stat().st_size != src_file.stat().st_size:
                    return False, f"Größe weicht ab: {src_file.name}"
        except OSError as e:
            return False, f"nicht prüfbar ({e})"
        return True, ""

    def _delete_pending_folders(self):
        """Löscht die lokalen Ordner erst, wenn der gesamte Upload fehlerfrei
        durchgelaufen ist - alles-oder-nichts, wie bei den Quelldateien."""
        pending = list(self._pending_local_deletions)
        self._pending_local_deletions.clear()
        if not pending:
            return

        failed = sum(1 for item in self.items if item.status == NASUploadStatus.FEHLER)
        if self._stop_requested or failed:
            grund = "abgebrochen" if self._stop_requested else f"{failed} Medium/Medien fehlgeschlagen"
            self.log_message.emit(
                f"No local folder deleted ({grund}) - {len(pending)} folder(s) kept."
            )
            return

        for item in pending:
            try:
                shutil.rmtree(item.folder_path)
                self.log_message.emit(f"[{item.name}] local folder deleted")
            except OSError as e:
                self.log_message.emit(f"[{item.name}] local folder could not be deleted: {e}")

    def _advance_overall_progress(self, file_size: int):
        """Aktualisiert den byte-gewichteten Gesamtfortschritt über alle Items hinweg."""
        self._bytes_copied += file_size
        self.total_progress_updated.emit(int((self._bytes_copied / self._total_bytes) * 100))

    def _copy_folder(self, source: Path, target: Path, idx: int) -> int:
        all_files = list(source.rglob("*"))
        total_files = len([f for f in all_files if f.is_file()])
        copied_files = 0

        target.mkdir(parents=True, exist_ok=True)

        for src_file in all_files:
            if self._stop_requested:
                break

            rel_path = src_file.relative_to(source)
            dest_file = target / rel_path

            if src_file.is_dir():
                dest_file.mkdir(parents=True, exist_ok=True)
            else:
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                file_size = src_file.stat().st_size
                shutil.copy2(src_file, dest_file)
                copied_files += 1
                progress = 20 + int((copied_files / max(total_files, 1)) * 70)
                self.progress_updated.emit(idx, progress, tr("Kopiere {done}/{total}: {name}").format(done=copied_files, total=total_files, name=src_file.name))
                self._advance_overall_progress(file_size)

        return copied_files

    def _merge_folders(self, source: Path, target: Path, idx: int) -> int:
        all_files = list(source.rglob("*"))
        total_files = len([f for f in all_files if f.is_file()])
        copied_files = 0

        for src_file in all_files:
            if self._stop_requested:
                break

            rel_path = src_file.relative_to(source)
            dest_file = target / rel_path

            if src_file.is_dir():
                dest_file.mkdir(parents=True, exist_ok=True)
            else:
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                file_size = src_file.stat().st_size
                shutil.copy2(src_file, dest_file)
                copied_files += 1
                progress = 15 + int((copied_files / max(total_files, 1)) * 75)
                self.progress_updated.emit(idx, progress, tr("Kopiere {done}/{total}: {name}").format(done=copied_files, total=total_files, name=src_file.name))
                self._advance_overall_progress(file_size)

        return copied_files
