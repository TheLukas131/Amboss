"""Generiert Zielpfade basierend auf erkanntem Medientyp.

Die erkannte MediaType-Kategorie wird direkt als oberste Zielordner-Ebene
verwendet (Converted/Anime/..., Converted/Serien/..., ...) - das entspricht
1:1 den Kategorien der Mediathek, sodass der Upload später nicht
erneut raten muss, ob ein Ordner Anime oder Serie ist.
"""

from pathlib import Path
from typing import List, Optional

from library_layout import NUMERIC_ONLY, season_folder_name, staging_folder_name
from models import MediaType, VideoFile

class PathGenerator:
    """Generiert Zielpfade basierend auf erkanntem Medientyp.

    Weder die Kategorie- noch die Staffel-Ebene tragen einen von der Anwendung
    erfundenen Namen: die Kategorie-Ebene heißt wie der eingestellte Zielordner,
    die Staffel-Ebene folgt der in der Mediathek vorgefundenen Schreibweise
    (siehe library_layout.py)."""

    @staticmethod
    def generate(video: VideoFile, output_base: Path, rename_enabled: bool,
                 category_folders: Optional[dict] = None,
                 season_pattern: str = NUMERIC_ONLY) -> Path:
        """Generiert den natürlichen Zielpfad für eine Videodatei (ohne Kollisionsprüfung)."""
        if not rename_enabled:
            return output_base / video.source_path.name

        category_folders = category_folders or {}

        if video.media_type in (MediaType.ANIME, MediaType.SERIEN):
            staging = staging_folder_name(video.media_type.value, category_folders)
            season = season_folder_name(season_pattern, video.season)
            filename = f"{video.series_name} S{video.season:02d}E{video.episode:02d}.mp4"
            return output_base / staging / video.series_name / season / filename

        if video.media_type in (MediaType.FILME, MediaType.ANIME_FILME):
            staging = staging_folder_name(video.media_type.value, category_folders)
            return output_base / staging / video.movie_name / f"{video.movie_name}.mp4"

        return output_base / "_Unknown_Format" / video.source_path.name

    @staticmethod
    def resolve_collisions(videos: List[VideoFile]) -> None:
        """Sorgt dafür, dass zwei unterschiedliche Quelldateien nie denselben Zielpfad
        erhalten (z.B. wenn zwei verschiedene Filme zufällig gleich benannt sind).
        Muss nach generate() für den kompletten Scan-Batch aufgerufen werden."""
        seen = {}
        for video in videos:
            target = video.target_path
            if target is None:
                continue
            if target not in seen:
                seen[target] = video
                continue

            # Kollision: gleicher Zielpfad, aber andere Quelldatei -> Suffix anhängen
            stem, suffix, parent = target.stem, target.suffix, target.parent
            counter = 2
            candidate = parent / f"{stem} ({counter}){suffix}"
            while candidate in seen or candidate.exists():
                counter += 1
                candidate = parent / f"{stem} ({counter}){suffix}"
            video.target_path = candidate
            seen[candidate] = video
