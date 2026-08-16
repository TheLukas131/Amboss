"""Markiert, dass in einem Quellordner gerade eine Konvertierung läuft.

Warum überhaupt: Beim Start eines Laufs wandern die Quelldateien nach
`_InProgress`, und dieser Ordner wird beim Scannen mitgelesen. Das ist Absicht -
nach einem Absturz liegen die Dateien dort und müssen wiedergefunden werden.
Öffnet man Amboss aber ein zweites Mal und scannt, während der erste noch
arbeitet, greift der zweite Lauf nach denselben Dateien.

`_InProgress` deshalb pauschal auszunehmen wäre die falsche Lösung: dann wären
sowohl die nach einem Absturz liegengebliebenen als auch die gescheiterten
Dateien dauerhaft unsichtbar.

Stattdessen hinterlässt ein laufender Vorgang hier eine Markierung mit seiner
Prozessnummer und einem Zeitstempel. Ein Scan überspringt `_InProgress` nur,
solange diese Markierung frisch ist und zu einem anderen, tatsächlich noch
laufenden Prozess gehört. Nach einem Absturz veraltet sie und der Ordner wird
wieder gelesen - genau das gewünschte Verhalten.
"""

import json
import os
import time
from pathlib import Path
from typing import Optional

from models import INPROGRESS_FOLDER_NAME

LOCK_NAME = ".amboss-running"

# Ab welchem Alter eine Markierung als verwaist gilt. Grosszügig bemessen: sie
# wird im Sekundentakt aufgefrischt, ein reguläres Programm hält das mühelos.
# Zu knapp wäre schlimmer als zu weit - dann griffe ein zweiter Lauf doch zu.
STALE_AFTER_SECONDS = 120


def lock_path(source_root: Path) -> Path:
    return source_root / INPROGRESS_FOLDER_NAME / LOCK_NAME


def acquire(source_root: Path) -> bool:
    """Setzt bzw. frischt die Markierung für den eigenen Prozess auf."""
    pfad = lock_path(source_root)
    try:
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text(json.dumps({"pid": os.getpid(), "time": time.time()}),
                        encoding="utf-8")
        return True
    except OSError:
        return False


def release(source_root: Path) -> None:
    """Entfernt die eigene Markierung. Fremde bleiben unangetastet."""
    pfad = lock_path(source_root)
    try:
        if not pfad.is_file():
            return
        daten = json.loads(pfad.read_text(encoding="utf-8"))
        if daten.get("pid") == os.getpid():
            pfad.unlink()
    except (OSError, ValueError):
        pass


# Windows meldet diesen Wert als Beendigungscode, solange ein Prozess läuft.
_STILL_ACTIVE = 259


def _process_running(pid: int) -> bool:
    """Ob dieser Prozess noch läuft. Im Zweifel ja - lieber einmal zu
    vorsichtig als zwei Läufe auf denselben Dateien.

    Ein geöffneter Zugriff allein genügt als Nachweis nicht: Windows hält eine
    Prozessnummer gültig, solange irgendjemand noch einen Zugriff darauf offen
    hat - etwa das Elternprogramm, das den Beendigungscode noch nicht abgeholt
    hat. Ein längst beendeter Prozess gälte dann weiter als aktiv. Deshalb wird
    zusätzlich der Beendigungscode abgefragt."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True          # nicht feststellbar -> vorsichtshalber ja
            return code.value == _STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    except (OSError, AttributeError):
        return True


def held_by_other(source_root: Path) -> Optional[int]:
    """Prozessnummer eines anderen, noch laufenden Vorgangs - sonst None.

    None heisst: `_InProgress` darf gelesen werden. Das gilt auch für die eigene
    Markierung, denn der eigene Lauf soll seine Dateien wiederfinden."""
    pfad = lock_path(source_root)
    try:
        if not pfad.is_file():
            return None
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    pid = daten.get("pid")
    if pid == os.getpid():
        return None
    if time.time() - float(daten.get("time", 0)) > STALE_AFTER_SECONDS:
        return None          # verwaist, etwa nach einem Absturz
    if not _process_running(pid):
        return None
    return pid
