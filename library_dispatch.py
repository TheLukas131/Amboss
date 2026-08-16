"""Entscheidet, welche Medienordner schon während eines Laufs verschoben werden dürfen.

Hintergrund: Ohne das passiert das Verschieben in die Mediathek erst, wenn der
gesamte Stapel durchgerendert ist. Bei fünf Stunden Rechenzeit steht das
Netzlaufwerk fünf Stunden still und arbeitet danach am Stück - obwohl der erste
Film schon nach zwanzig Minuten fertig ist.

Der naheliegende Ansatz "Datei fertig, also hoch damit" wäre allerdings falsch.
Verschoben werden nicht einzelne Dateien, sondern **Serienordner** als Ganzes
(siehe NASUploadWorker). Wandert ein Ordner los, während weitere Folgen
derselben Serie noch rendern, dann

- wird er bei aktivem "lokal löschen" entfernt, während der Konverter noch
  hineinschreibt, und
- schlägt die Vollständigkeitsprüfung des Uploads fehl, weil er die Dateien zu
  Beginn zählt und am Ende vergleicht.

Deshalb die Regel: ein Ordner ist erst dann frei, wenn **keine offene Datei mehr
auf ihn zielt**. Weil die gesamte Warteschlange nach dem Scan feststeht, gilt das
auch bei bunt gemischter Reihenfolge - Serie A, Serie B, wieder Serie A.
"""

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from models import FileStatus, VideoFile

# Zustände, bei denen für diese Datei nichts mehr passiert.
_ABGESCHLOSSEN = {FileStatus.FERTIG, FileStatus.FEHLER, FileStatus.UEBERSPRUNGEN}


def media_folder_of(video: VideoFile, output_base: Path) -> Optional[Path]:
    """Der Ordner, den der Upload als eine Einheit behandelt.

    Das ist die zweite Ebene unterhalb des Zielordners: unter der Kategorie
    (`Anime`, `Filme`, ...) liegt je Serie bzw. Film ein Ordner, und genau der
    wandert als Ganzes. Liegt die Datei nicht unterhalb des Zielordners - etwa
    weil das Umbenennen aus ist und sie direkt dort landet - gibt es keine
    solche Einheit und damit nichts vorzuziehen."""
    if not video.target_path:
        return None
    try:
        rest = video.target_path.resolve().relative_to(output_base.resolve())
    except (OSError, ValueError):
        return None
    # rest = <Kategorie>/<Serie>/<Staffel>/<Datei> oder <Kategorie>/<Film>/<Datei>
    if len(rest.parts) < 3:
        return None
    return output_base / rest.parts[0] / rest.parts[1]


def pending_folders(videos: Iterable[VideoFile], output_base: Path) -> Set[Path]:
    """Ordner, auf die noch mindestens eine unerledigte Datei zielt."""
    offen = set()
    for video in videos:
        if video.status in _ABGESCHLOSSEN:
            continue
        ordner = media_folder_of(video, output_base)
        if ordner is not None:
            offen.add(ordner)
    return offen


def ready_folders(videos: Iterable[VideoFile], output_base: Path,
                  already_dispatched: Optional[Set[Path]] = None) -> List[Path]:
    """Ordner, die jetzt verschoben werden dürfen.

    Ein Ordner ist frei, wenn alle drei Bedingungen gelten:

    1. Keine offene Datei zielt mehr auf ihn.
    2. Mindestens eine Datei ist dort erfolgreich gelandet - sonst gäbe es
       nichts zu verschieben.
    3. Keine Datei für ihn ist fehlgeschlagen. Ein Ordner mit einer
       misslungenen Folge ist unvollständig; den vorzuziehen hiesse, eine
       lückenhafte Staffel in die Mediathek zu legen, während der Nutzer noch
       gar nichts davon weiss. Solche Ordner bleiben liegen und gehen beim
       regulären Upload am Ende mit - dort sieht man das Gesamtbild.

    `already_dispatched` verhindert, dass derselbe Ordner zweimal losgeschickt
    wird, wenn nach ihm noch weitere Dateien fertig werden."""
    videos = list(videos)
    offen = pending_folders(videos, output_base)
    bereits = already_dispatched or set()

    fertig: Dict[Path, bool] = {}
    fehlerhaft: Set[Path] = set()

    for video in videos:
        ordner = media_folder_of(video, output_base)
        if ordner is None:
            continue
        if video.status == FileStatus.FERTIG:
            fertig[ordner] = True
        elif video.status == FileStatus.FEHLER:
            fehlerhaft.add(ordner)

    frei = [
        ordner for ordner in sorted(fertig)
        if ordner not in offen
        and ordner not in fehlerhaft
        and ordner not in bereits
    ]
    return frei
