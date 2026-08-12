"""Protokollierung unbehandelter Ausnahmen und harter Abstürze.

Hintergrund: PyQt5 ruft qFatal() auf, sobald eine Python-Ausnahme aus einem Slot
oder einer reimplementierten virtuellen Methode entkommt. qFatal() ruft abort(),
der Prozess verschwindet also schlagartig mit Ausnahmecode 0xc0000409 - ohne
Meldung, ohne Traceback, und da die exe ohne Konsole gebaut ist auch ohne jede
sichtbare Spur. Genau so sahen die gemeldeten "random Abstürze" aus.

Ein eigener sys.excepthook durchbricht das: die Ausnahme wird protokolliert und
die Anwendung läuft weiter, statt kommentarlos zu sterben. Zusätzlich schreibt
faulthandler echte Abstürze (Zugriffsverletzungen in Qt/sip) mit nativem Stack
in dieselbe Datei - die entstehen unterhalb von Python und lassen sich nicht
abfangen, aber wenigstens dokumentieren.
"""

import faulthandler
import logging
import os
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

LOG_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "Amboss"
APP_LOG_PATH = LOG_DIR / "app.log"
CRASH_LOG_PATH = LOG_DIR / "crash.log"

# Beide Dateien werden bei Überschreitung schlicht neu angelegt - eine echte
# Rotation lohnt für ein Diagnoseprotokoll nicht.
MAX_LOG_BYTES = 5_000_000

logger = logging.getLogger(__name__)

_error_callback: Optional[Callable[[str, str], None]] = None
_crash_file = None  # offen halten, solange die App läuft - faulthandler schreibt hinein


def set_error_callback(callback: Optional[Callable[[str, str], None]]) -> None:
    """Registriert eine Funktion (kurztext, volltext), mit der die Oberfläche auf
    einen abgefangenen Fehler hinweisen kann. Fehlt sie, wird nur protokolliert."""
    global _error_callback
    _error_callback = callback


def _trim_if_huge(path: Path) -> None:
    try:
        if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
            path.unlink()
    except OSError:
        pass


def _write_crash_entry(header: str, text: str) -> None:
    try:
        with open(CRASH_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} | {header} =====\n{text}\n")
    except OSError:
        pass


def _handle(exc_type, exc_value, exc_tb, source: str) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return

    text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    summary = "".join(traceback.format_exception_only(exc_type, exc_value)).strip()

    logger.error("Unbehandelte Ausnahme (%s):\n%s", source, text)
    _write_crash_entry(source, text)

    if _error_callback is not None:
        try:
            _error_callback(summary, text)
        except Exception:  # noqa: BLE001 - eine kaputte Meldung darf nichts weiter auslösen
            pass


def install() -> None:
    """Richtet Dateiprotokoll, excepthook und faulthandler ein. Früh in main()
    aufrufen, noch vor dem Erzeugen der QApplication."""
    global _crash_file

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        return  # ohne Verzeichnis kein Protokoll - aber auch kein Grund abzubrechen

    _trim_if_huge(APP_LOG_PATH)
    _trim_if_huge(CRASH_LOG_PATH)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    try:
        handler = logging.FileHandler(APP_LOG_PATH, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s"))
        root.addHandler(handler)
    except OSError:
        pass

    sys.excepthook = lambda t, v, tb: _handle(t, v, tb, "Hauptthread/Qt-Slot")

    # Ausnahmen in normalen Python-Threads (z.B. im ThreadPool beim Scannen)
    if hasattr(threading, "excepthook"):
        threading.excepthook = lambda args: _handle(
            args.exc_type, args.exc_value, args.exc_traceback, f"Thread {args.thread.name}"
        )

    try:
        _crash_file = open(CRASH_LOG_PATH, "a", encoding="utf-8")
        faulthandler.enable(file=_crash_file, all_threads=True)
    except (OSError, ValueError):
        pass

    logger.info("=== Start | Absturzprotokoll: %s ===", CRASH_LOG_PATH)
