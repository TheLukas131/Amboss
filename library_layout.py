"""Übernimmt die Ordner-Konventionen aus der vorhandenen Mediathek.

Hintergrund: Jede fest eingebaute Bezeichnung für Staffel-Ordner ist zwangsläufig
eine bestimmte Sprache - "Staffel 2" ist deutsch, "Season 2" englisch, und für
japanische oder russische Sammlungen passt beides nicht. Statt eine Sprache zu
verordnen, liest dieses Modul ab, wie der Nutzer seine Mediathek bereits benannt
hat, und schreibt neue Ordner genauso.

Gleiches gilt für die Kategorie-Ebene: der Zwischenordner heißt so wie der
Zielordner, in den später verschoben wird. Damit ist die Ablage eine 1:1-Kopie
der vorhandenen Struktur und nirgends steht ein von der App erfundener Name.
"""

import re
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, Optional

# Ein Staffelordner ist "irgendein Text, dann eine Zahl" - z.B. "Staffel 2",
# "Season 02", "Saison 2", "S2" oder schlicht "2". Der Textteil ist die
# Konvention, die übernommen wird.
_SEASON_DIR = re.compile(r"^(?P<prefix>\D*?)\s*(?P<number>\d{1,3})$")

# Fällt die Erkennung aus (leere Mediathek), wird nur die Zahl verwendet. Das ist
# die einzige Variante, die in keiner Sprache falsch ist, und die gängigen
# Medienserver erkennen rein numerische Staffelordner.
NUMERIC_ONLY = "{number}"


def parse_season_convention(name: str) -> Optional[Dict[str, object]]:
    """Zerlegt einen Staffel-Ordnernamen in Präfix, Trennzeichen und Stellenzahl."""
    match = _SEASON_DIR.match(name.strip())
    if not match:
        return None
    raw_prefix = match.group("prefix")
    number = match.group("number")
    separator = " " if raw_prefix and name.strip()[len(raw_prefix)] == " " else ""
    return {"prefix": raw_prefix, "separator": separator, "digits": len(number)}


def convention_to_pattern(convention: Dict[str, object]) -> str:
    """Baut aus einer erkannten Konvention eine Vorlage wie 'Staffel {number}'."""
    prefix = convention["prefix"]
    separator = convention["separator"]
    digits = convention["digits"]
    placeholder = "{number:0%dd}" % digits if digits > 1 else "{number}"
    return f"{prefix}{separator}{placeholder}"


def detect_season_pattern(library_folders: Iterable[str]) -> Optional[str]:
    """Ermittelt die in der Mediathek vorherrschende Staffel-Benennung.

    Sieht in jedem Kategorie-Ordner eine Ebene tief in die Serien-Ordner und
    zählt, welche Konvention dort am häufigsten vorkommt. Gibt None zurück, wenn
    sich nichts finden lässt - dann entscheidet der Aufrufer."""
    counter: Counter = Counter()
    for folder in library_folders:
        if not folder:
            continue
        root = Path(folder)
        if not root.is_dir():
            continue
        try:
            shows = [p for p in root.iterdir() if p.is_dir()]
        except OSError:
            continue
        for show in shows[:60]:  # eine Stichprobe reicht, Netzlaufwerke sind langsam
            try:
                seasons = [p for p in show.iterdir() if p.is_dir()]
            except OSError:
                continue
            for season in seasons:
                convention = parse_season_convention(season.name)
                if convention:
                    counter[convention_to_pattern(convention)] += 1

    return counter.most_common(1)[0][0] if counter else None


def season_folder_name(pattern: str, season: int) -> str:
    """Wendet eine Vorlage auf eine Staffelnummer an."""
    try:
        return (pattern or NUMERIC_ONLY).format(number=season)
    except (KeyError, IndexError, ValueError):
        return str(season)


def staging_folder_name(category: str, category_folders: Dict[str, str]) -> str:
    """Name des Zwischenordners für eine Kategorie.

    Nimmt den Namen des eingestellten Zielordners - dann heißt die lokale Ablage
    genauso wie das Ziel und es taucht kein von der App erfundener Begriff auf.
    Ohne eingestellten Zielordner bleibt eine neutrale Kennung."""
    configured = (category_folders or {}).get(category, "").strip()
    if configured:
        name = Path(configured).name
        if name:
            return name
    return CATEGORY_SLUGS.get(category, category)


# Neutrale Rückfallkennungen, solange für eine Kategorie kein Zielordner
# eingestellt ist. Bewusst kleingeschrieben und ohne Umlaute - das sind
# technische Kennungen, keine Beschriftungen.
CATEGORY_SLUGS = {
    "Anime": "anime",
    "Anime Filme": "anime-movies",
    "Filme": "movies",
    "Serien": "series",
}


def category_for_staging_folder(name: str, category_folders: Dict[str, str]) -> Optional[str]:
    """Umkehrung von staging_folder_name: findet zu einem Ordnernamen die Kategorie."""
    lowered = name.strip().lower()
    for category, folder in (category_folders or {}).items():
        if folder and Path(folder).name.lower() == lowered:
            return category
    for category, slug in CATEGORY_SLUGS.items():
        if slug == lowered or category.lower() == lowered:
            return category
    return None
