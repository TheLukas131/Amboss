"""Zugriff auf mitgelieferte Dateien (Icon, Logos).

Eigenes Modul, damit sowohl main.py als auch die Oberfläche darauf zugreifen
können, ohne sich gegenseitig zu importieren."""

import sys
from pathlib import Path


def resource_path(relative: str) -> Path:
    """Pfad zu einer mitgelieferten Ressource - im Entwicklungsbetrieb neben den
    Quelldateien, in der gepackten exe im PyInstaller-Verzeichnis (sys._MEIPASS)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base / relative
