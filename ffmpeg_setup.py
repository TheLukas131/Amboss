"""Beschafft FFmpeg, wenn es auf dem Rechner fehlt.

FFmpeg von Hand zu installieren und in den PATH einzutragen ist die Huerde, an
der die meisten Erstnutzer haengenbleiben. Amboss kann es deshalb selbst holen -
aber nur nach ausdruecklicher Zustimmung und aus der offiziellen Quelle.

Mitgeliefert wird es bewusst nicht: ffmpeg.exe und ffprobe.exe sind zusammen
ueber 280 MB und wuerden das Programm auf ein Vielfaches aufblaehen. Der Download
landet in %APPDATA%\\Amboss\\ffmpeg und wird nur von dort benutzt; am System
aendert sich nichts, und Deinstallieren heisst schlicht Ordner loeschen.

Die Herkunft wird geprueft: der Anbieter veroeffentlicht zu jedem Archiv eine
SHA256-Pruefsumme, die vor dem Entpacken gegen die heruntergeladene Datei
gehalten wird. Stimmt sie nicht, wird die Datei verworfen.
"""

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional, Tuple

# Offizielle Windows-Builds, verlinkt von ffmpeg.org. Die "essentials"-Variante
# enthaelt alles, was Amboss braucht, und ist rund ein Drittel kleiner als die
# Vollversion.
DOWNLOAD_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
CHECKSUM_URL = DOWNLOAD_URL + ".sha256"
SOURCE_NAME = "gyan.dev"

_CREATIONFLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
_NEEDED = ("ffmpeg.exe", "ffprobe.exe")


def install_dir() -> Path:
    """Ordner, in den Amboss FFmpeg ablegt - neben Konfiguration und Protokoll."""
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "Amboss" / "ffmpeg"


def installed_binaries() -> Optional[Tuple[Path, Path]]:
    """Gibt die bereits abgelegten Programme zurueck, falls beide vorhanden sind."""
    target = install_dir()
    ffmpeg, ffprobe = target / "ffmpeg.exe", target / "ffprobe.exe"
    return (ffmpeg, ffprobe) if ffmpeg.exists() and ffprobe.exists() else None


def _runs(path) -> bool:
    try:
        result = subprocess.run([str(path), "-version"], capture_output=True,
                                timeout=8, creationflags=_CREATIONFLAGS)
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False


def is_available_on_system() -> bool:
    """Ob FFmpeg *und* FFprobe regulaer im PATH stehen."""
    return all(_runs(name) for name in ("ffmpeg", "ffprobe"))


def download_size_bytes(timeout: float = 20.0) -> Optional[int]:
    """Fragt die Groesse des Archivs ab, damit die Rueckfrage sie nennen kann."""
    try:
        request = urllib.request.Request(DOWNLOAD_URL, method="HEAD")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            length = response.headers.get("Content-Length")
        return int(length) if length else None
    except (OSError, ValueError):
        return None


def _expected_checksum(timeout: float = 20.0) -> Optional[str]:
    try:
        with urllib.request.urlopen(CHECKSUM_URL, timeout=timeout) as response:
            return response.read().decode("ascii", "ignore").split()[0].strip().lower()
    except (OSError, IndexError, UnicodeError):
        return None


class DownloadCancelled(Exception):
    """Der Nutzer hat den laufenden Download abgebrochen."""


class DownloadFailed(Exception):
    """Der Download war nicht verwertbar - mit Begruendung fuer die Anzeige."""


def fetch_ffmpeg(progress: Optional[Callable[[int], None]] = None,
                 cancelled: Optional[Callable[[], bool]] = None) -> Tuple[Path, Path]:
    """Laedt FFmpeg herunter, prueft es und entpackt die beiden Programme.

    `progress` bekommt den Fortschritt in Prozent, `cancelled` wird regelmaessig
    befragt und bricht bei True ab. Gibt die Pfade zu ffmpeg.exe und ffprobe.exe
    zurueck oder wirft DownloadFailed/DownloadCancelled."""
    expected = _expected_checksum()
    scratch = Path(tempfile.mkdtemp(prefix="amboss_ffmpeg_"))
    archive = scratch / "ffmpeg.zip"

    try:
        digest = hashlib.sha256()
        try:
            with urllib.request.urlopen(DOWNLOAD_URL, timeout=30) as response:
                total = int(response.headers.get("Content-Length") or 0)
                loaded = 0
                with open(archive, "wb") as target:
                    while True:
                        if cancelled and cancelled():
                            raise DownloadCancelled()
                        chunk = response.read(262144)
                        if not chunk:
                            break
                        target.write(chunk)
                        digest.update(chunk)
                        loaded += len(chunk)
                        if progress and total:
                            progress(min(int(loaded * 100 / total), 100))
        except DownloadCancelled:
            raise
        except OSError as error:
            raise DownloadFailed(str(error)) from error

        # Ohne veroeffentlichte Pruefsumme wird nicht entpackt - lieber
        # abbrechen als ein Programm ausfuehren, dessen Herkunft ungeprueft ist.
        if not expected:
            raise DownloadFailed("checksum_unavailable")
        if digest.hexdigest().lower() != expected:
            raise DownloadFailed("checksum_mismatch")

        target_dir = install_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(archive) as bundle:
                for wanted in _NEEDED:
                    member = next(
                        (m for m in bundle.namelist()
                         if m.lower().endswith("/bin/" + wanted)), None)
                    if member is None:
                        raise DownloadFailed("incomplete_archive")
                    with bundle.open(member) as source, \
                            open(target_dir / wanted, "wb") as destination:
                        shutil.copyfileobj(source, destination)
        except (zipfile.BadZipFile, OSError) as error:
            raise DownloadFailed(str(error)) from error

        binaries = installed_binaries()
        if not binaries or not _runs(binaries[0]):
            raise DownloadFailed("not_executable")
        return binaries

    finally:
        shutil.rmtree(scratch, ignore_errors=True)
