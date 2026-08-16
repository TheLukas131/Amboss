"""Verschiebt Quelldateien beim Start der Konvertierung in einen `_InProgress`-
Unterordner der Quelle. Dadurch bleibt der eigentliche Quellordner frei für neue
Downloads, während im Hintergrund gerendert wird - der Downloadordner und die
Warteschlange geraten sich so nicht in die Quere.

Läuft explizit erst beim Klick auf 'Konvertierung starten', nicht beim Scannen -
ein Scan allein (auch gefolgt vom Schließen der App) fasst keine Dateien an."""

import shutil
from pathlib import Path
from typing import List

from models import INPROGRESS_FOLDER_NAME, FileStatus, VideoFile


def move_videos_to_inprogress(videos: List[VideoFile], source_root: Path) -> List[str]:
    """Verschiebt jede noch zu konvertierende Datei nach `<source_root>/_InProgress/...`
    (relative Ordnerstruktur bleibt erhalten) und aktualisiert `video.source_path`.
    Bereits übersprungene Dateien (schon konvertiert) werden nicht angefasst."""
    log_lines: List[str] = []
    inprogress_root = (source_root / INPROGRESS_FOLDER_NAME).resolve()

    for video in videos:
        if video.status == FileStatus.UEBERSPRUNGEN:
            continue

        old_path = video.source_path.resolve()

        try:
            old_path.relative_to(inprogress_root)
            continue  # bereits im _InProgress-Ordner (z.B. nach App-Neustart)
        except ValueError:
            pass

        try:
            rel = old_path.relative_to(source_root.resolve())
        except ValueError:
            continue  # Datei liegt nicht unter der Quelle - nicht anfassen

        new_path = inprogress_root / rel
        if new_path.exists():
            log_lines.append(
                f"WARNING: [{old_path.name}] is already in {INPROGRESS_FOLDER_NAME} - skipped"
            )
            continue

        new_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(old_path), str(new_path))
        except OSError as e:
            log_lines.append(f"WARNING: [{old_path.name}] could not be moved to {INPROGRESS_FOLDER_NAME}: {e}")
            continue

        video.source_path = new_path
        log_lines.append(f"[{old_path.name}] -> {INPROGRESS_FOLDER_NAME}/")

    return log_lines


def delete_redundant_duplicates(paths: List[Path]) -> List[str]:
    """Löscht die beim Scannen aussortierten Doppel-Downloads.

    Wird bewusst erst beim Start der Konvertierung aufgerufen, nicht schon beim
    Scannen - ein Scan allein darf keine Datei anfassen. Gelöscht wird nur, was
    duplicate_detector als redundant erkannt hat: gleicher Name im selben Ordner,
    und die behaltene Datei ist gleich groß oder größer."""
    log_lines: List[str] = []
    for path in paths:
        try:
            if not path.exists():
                continue
            size = path.stat().st_size
            path.unlink()
            log_lines.append(f"Deleted duplicate download: '{path.name}' ({size:,} bytes)")
        except OSError as e:
            log_lines.append(f"WARNING: duplicate download '{path.name}' could not be deleted: {e}")
    return log_lines


def prune_empty_inprogress_dirs(source_root: Path) -> None:
    """Entfernt leer gewordene Ordner unterhalb von `_InProgress` (und den Ordner
    selbst, wenn nichts mehr drin ist).

    Nötig, weil mit "Quelle nach Konvertierung löschen" nur die Dateien
    verschwinden - die Ordnerstruktur bliebe sonst als leeres Gerippe zurück und
    würde bei jedem Blick in den Downloadordner Arbeit vortäuschen."""
    inprogress_root = source_root / INPROGRESS_FOLDER_NAME
    if not inprogress_root.is_dir():
        return

    # Von unten nach oben, damit ein Ordner erst geprüft wird, nachdem seine
    # Unterordner ggf. schon entfernt wurden.
    for directory in sorted(
        (p for p in inprogress_root.rglob("*") if p.is_dir()),
        key=lambda p: len(p.parts), reverse=True,
    ):
        try:
            directory.rmdir()
        except OSError:
            pass  # nicht leer - bleibt bestehen

    try:
        inprogress_root.rmdir()
    except OSError:
        pass
