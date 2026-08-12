"""Erkennung von Ordner-Duplikaten, die durch beim Download abgeschnittene
Dateinamen entstanden sind (z.B. "Demons Ascensio" statt "Demons Ascension").

Anime-Dateinamen tragen den Serien-Namen ganz am Ende ("Episode X Staffel Y von
{Name}.mp4"). Wird der Gesamtpfad beim Download zu lang, schneidet Windows/der
Downloader den Namen ab - und weil die Ziffernanzahl der Episodennummer (9 vs.
10) die Gesamtlänge verschiebt, können zwei Episoden derselben Serie
unterschiedlich stark abgeschnitten werden. Das erzeugt sonst zwei getrennte
Ordner statt einem.

Die Erkennung läuft bewusst NICHT während der Konvertierung (die soll nie
warten), sondern danach als Scan der bereits auf der Platte liegenden
Show-Ordner pro Kategorie.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class MergeCandidate:
    shorter: Path
    longer: Path
    shorter_file_count: int
    longer_file_count: int


def _count_files(folder: Path) -> int:
    return sum(1 for f in folder.rglob("*") if f.is_file())


def find_truncation_candidates(category_dir: Path) -> List[MergeCandidate]:
    """Sucht in einem Kategorie-Ordner (z.B. Converted/Anime) nach Show-Ordnern,
    deren Name exaktes Präfix eines anderen Show-Ordnernamens ist."""
    if not category_dir.is_dir():
        return []

    show_folders = sorted(
        (f for f in category_dir.iterdir() if f.is_dir() and not f.name.startswith(('_', '.'))),
        key=lambda f: len(f.name),
    )

    candidates: List[MergeCandidate] = []
    matched = set()
    for i, shorter in enumerate(show_folders):
        if shorter.name in matched:
            continue
        for longer in show_folders[i + 1:]:
            if longer.name == shorter.name:
                continue
            if longer.name.startswith(shorter.name):
                candidates.append(MergeCandidate(
                    shorter=shorter,
                    longer=longer,
                    shorter_file_count=_count_files(shorter),
                    longer_file_count=_count_files(longer),
                ))
                matched.add(shorter.name)
                break  # nur die naheliegendste (kürzeste passende) Übereinstimmung nehmen
    return candidates


def merge_folders(candidate: MergeCandidate) -> None:
    """Verschiebt den Inhalt des kürzeren Ordners in den längeren (kanonischen)
    Ordner und entfernt den nun leeren kürzeren Ordner."""
    for item in candidate.shorter.iterdir():
        dest = candidate.longer / item.name
        if item.is_dir():
            if dest.exists():
                _merge_directory(item, dest)
            else:
                shutil.move(str(item), str(dest))
        else:
            dest = _unique_path(dest)
            shutil.move(str(item), str(dest))
    candidate.shorter.rmdir()


def _merge_directory(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        dest = target / item.name
        if item.is_dir():
            _merge_directory(item, dest)
        else:
            dest = _unique_path(dest)
            shutil.move(str(item), str(dest))
    source.rmdir()


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    counter = 2
    candidate = parent / f"{stem} ({counter}){suffix}"
    while candidate.exists():
        counter += 1
        candidate = parent / f"{stem} ({counter}){suffix}"
    return candidate
