"""Erkennt Dateien, die durch mehrfaches Herunterladen derselben Quelle entstanden
sind (z.B. "Fruits Basket.mp4" und "Fruits Basket (1).mp4" im selben Ordner -
typisches Muster, wenn Browser/Downloader bei einem Namenskonflikt automatisch
eine "(N)" anhängen). Von so einer Gruppe wird nur die größte Datei behalten -
eine kleinere Variante ist so gut wie immer ein abgebrochener/korrupter
Download-Versuch, keine eigenständige zweite Episode/Film.

Bewusst nur 1-3-stellige Klammer-Zahlen ("(1)", "(12)") - eine 4-stellige Zahl
wie "(2020)" ist mit hoher Wahrscheinlichkeit ein Erscheinungsjahr im Titel und
soll nicht angefasst werden.
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple

_DUP_SUFFIX_RE = re.compile(r'^(.*?)\s*\((\d{1,3})\)$')


def strip_duplicate_suffix(stem: str) -> str:
    """Entfernt eine abschließende "(N)"-Downloadmarkierung aus einem Dateinamen
    (ohne Endung), falls vorhanden - sonst unverändert."""
    match = _DUP_SUFFIX_RE.match(stem.strip())
    return match.group(1).strip() if match else stem


def _canonical_key(path: Path) -> str:
    base = strip_duplicate_suffix(path.stem).lower()
    return f"{path.parent}/{base}{path.suffix.lower()}"


def _has_duplicate_suffix(path: Path) -> bool:
    return strip_duplicate_suffix(path.stem) != path.stem


def filter_duplicate_downloads(files: List[Path]) -> Tuple[List[Path], List[str], List[Path]]:
    """Gruppiert Dateien nach demselben Basisnamen (mit/ohne "(N)"-Suffix) im
    selben Ordner. Aus jeder Gruppe mit mehr als einer Datei wird nur eine behalten.

    Gibt (behaltene Dateien, Log-Zeilen, aussortierte Dateien) zurück. Die
    aussortierten werden hier NICHT gelöscht - das passiert erst beim Start der
    Konvertierung (siehe inprogress_mover.delete_redundant_duplicates), damit ein
    reiner Scan niemals Dateien anfasst."""
    groups: Dict[str, List[Path]] = {}
    for f in files:
        groups.setdefault(_canonical_key(f), []).append(f)

    kept: List[Path] = []
    log_lines: List[str] = []
    redundant: List[Path] = []

    for group in groups.values():
        if len(group) == 1:
            kept.append(group[0])
            continue

        sized = [(f, f.stat().st_size) for f in group]
        # Größte gewinnt. Bei exakt gleicher Größe - also derselbe Download
        # zweimal - gewinnt die Datei OHNE "(N)"-Markierung; sonst entschied die
        # alphabetische Reihenfolge, und die stellt " (1)" vor ".mp4".
        largest, largest_size = max(
            sized, key=lambda item: (item[1], not _has_duplicate_suffix(item[0]))
        )
        kept.append(largest)

        for f, size in sized:
            if f == largest:
                continue
            redundant.append(f)
            vergleich = "ist größer" if largest_size > size else "ist gleich groß"
            log_lines.append(
                f"Duplicate found: '{f.name}' ({size:,} bytes) - "
                f"'{largest.name}' ({largest_size:,} bytes) {vergleich} and will be used instead"
            )

    return kept, log_lines, redundant
