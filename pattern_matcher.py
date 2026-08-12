"""Erkennt Serien-, Anime- und Film-Namen in Dateinamen und klassifiziert sie.

Zwei Release-Konventionen kommen in der Praxis vor:
- Anime (deutscher Dub-Release): "Episode 1 Staffel 1 von Demons Ascension.mp4"
- Serie: "Show Name S01E02 ...mp4"
  Das S/E-Muster allein reicht als Signal; alles dahinter (Quellenkürzel,
  Qualitätsangaben und Ähnliches) wird ignoriert, da nur der Teil vor
  "S<Zahl>E<Zahl>" als Name erfasst wird.
Alles andere ohne Episoden-Muster wird als Film behandelt; Filme mit einem
Anime-typischen Schlüsselwort im Namen gelten als Anime-Film.
"""

import re
from pathlib import Path

from duplicate_detector import strip_duplicate_suffix
from models import ANIME_KEYWORDS, MediaType, VideoFile


class PatternMatcher:
    """Erkennt Medientyp und Serien-/Episoden-Informationen in Dateinamen."""

    ANIME_PATTERN = re.compile(
        r'Episode\s*\(?(\d+)\)?\s*Staffel\s*\(?(\d+)\)?\s*von\s*(.+?)\.mp4$',
        re.IGNORECASE
    )

    SERIE_PATTERN = re.compile(
        r'^(.+?)\s*S(\d+)E(\d+)',
        re.IGNORECASE
    )

    @classmethod
    def analyze(cls, filepath: Path) -> VideoFile:
        """Analysiert eine Datei und erkennt ihren Medientyp."""
        filename = filepath.name
        video = VideoFile(source_path=filepath)

        match = cls.ANIME_PATTERN.search(filename)
        if match:
            video.media_type = MediaType.ANIME
            video.episode = int(match.group(1))
            video.season = int(match.group(2))
            video.series_name = cls._clean_name(match.group(3))
            return video

        match = cls.SERIE_PATTERN.search(filename)
        if match:
            video.media_type = MediaType.SERIEN
            video.series_name = cls._clean_name(match.group(1))
            video.season = int(match.group(2))
            video.episode = int(match.group(3))
            return video

        name_without_ext = filepath.stem
        if cls._looks_like_movie(name_without_ext):
            cleaned = cls._clean_name(name_without_ext)
            video.media_type = MediaType.ANIME_FILME if cls._is_anime_name(cleaned) else MediaType.FILME
            video.movie_name = cleaned
        else:
            video.media_type = MediaType.UNBEKANNT
            video.movie_name = name_without_ext

        return video

    @classmethod
    def _is_anime_name(cls, name: str) -> bool:
        name_lower = name.lower()
        return any(keyword in name_lower for keyword in ANIME_KEYWORDS)

    @classmethod
    def _clean_name(cls, name: str) -> str:
        """Bereinigt einen Namen von unerwünschten Zeichen und einer eventuellen
        Mehrfach-Download-Markierung wie "(1)" (siehe duplicate_detector.py)."""
        name = name.strip().strip('.')
        name = re.sub(r'\s+', ' ', name)
        name = re.sub(r'[<>:"/\\|?*]', '', name)
        name = strip_duplicate_suffix(name)
        return name

    @classmethod
    def _looks_like_movie(cls, name: str) -> bool:
        """Prüft ob ein Name wie ein Filmtitel aussieht (nicht nur Zahlen/Codes)."""
        clean = re.sub(r'[\d\s\-_\.\[\]\(\)]', '', name)
        return len(clean) > 2
