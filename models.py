"""Datenmodelle, Enums und Konstanten."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

APP_NAME = "Amboss"
APP_TAGLINE = "Konvertiert Videos nach AV1, H.265 & H.264 über NVIDIA NVENC"
APP_VERSION = "1.3.2"

DEFAULT_CQ = 37
DEFAULT_PRESET = "p5"
DEFAULT_PARALLEL_TASKS = 3
DEFAULT_OUTPUT_FOLDER = "Converted"
INPROGRESS_FOLDER_NAME = "_InProgress"
# Quellen, deren Konvertierung fehlschlug, landen hier - getrennt von denen, die
# noch anstehen. Nach einem Lauf steht in diesem Ordner genau das, was
# Aufmerksamkeit braucht.
#
# Englisch wie alle anderen von der Anwendung angelegten Ordner ("Converted",
# "_InProgress", "_Unknown_Format"): ein Ordnername ist kein Oberflächentext,
# er wandert mit der Datei und wird auch von Nutzern gesehen, die die
# Anwendung auf Englisch bedienen.
FAILED_FOLDER_NAME = "_Failed"
DEFAULT_CODEC = "av1_nvenc"
# Bewusst kein voreingestellter Netzwerkpfad: der Zielordner wird beim ersten
# Start in der Oberfläche gewählt, und aus dessen Unterordnern leitet die App
# ab, welche Kategorien die Mediathek überhaupt kennt.

PRESETS = ["p1", "p2", "p3", "p4", "p5", "p6", "p7"]
PRESET_LABELS = {
    "p1": "p1 - Sehr schnell (Schlechtere Kompression)",
    "p2": "p2 - Schnell",
    "p3": "p3 - Schnell",
    "p4": "p4 - Ausgewogen",
    "p5": "p5 - Ausgewogen (Standard)",
    "p6": "p6 - Langsamer",
    "p7": "p7 - Langsam (Beste Kompression)",
}

# Alle Codecs laufen über NVENC (GPU-Hardware-Encoding).
#
# Reihenfolge nach Nutzen: AV1 komprimiert am besten, braucht aber eine Karte
# ab der RTX-4000-Reihe. H.265 ist der Mittelweg für Geräte ohne AV1, H.264
# läuft praktisch überall.
CODEC_LABELS = {
    "av1_nvenc": "AV1 (NVENC, GPU) - Standard",
    "hevc_nvenc": "H.265 / HEVC (NVENC, GPU)",
    "h264_nvenc": "H.264 (NVENC, GPU)",
}

# H.265 in MP4 braucht die Container-Kennung 'hvc1'. FFmpeg schreibt sonst
# 'hev1', und Apple-Geräte (QuickTime, Safari, iOS) verweigern die Wiedergabe -
# die Datei wirkt dort defekt, obwohl sie einwandfrei ist. In MKV spielt die
# Kennung keine Rolle.
HEVC_MP4_TAG = "hvc1"

# Obergrenze der Qualitätsskala je Encoder. AV1 reicht bis 63, H.265 und H.264
# nur bis 51 - derselbe CQ-Wert liegt also je nach Codec an einer anderen Stelle
# der Skala. Der Regler bleibt für alle bei höchstens 51, damit nie ein Wert
# entsteht, den ein Encoder ablehnt; angezeigt wird die Grenze aber, sonst
# wechselt beim Codecwechsel unbemerkt die Bedeutung der Zahl.
CQ_MAXIMUM = {"av1_nvenc": 63, "hevc_nvenc": 51, "h264_nvenc": 51}


def cq_maximum_for(codec: str) -> int:
    return CQ_MAXIMUM.get(codec, 51)

# Eingangsformate, die beim Scannen gefunden werden. FFmpeg liest weit mehr,
# aber diese decken ab, was als Video-Veröffentlichung tatsächlich vorkommt -
# und je weiter die Liste, desto eher greift der Scan versehentlich nach
# Dateien, die niemand konvertieren wollte.
VIDEO_EXTENSIONS = (".mp4", ".mkv", ".avi", ".ts", ".mov", ".m4v", ".wmv", ".flv", ".webm", ".mpg", ".mpeg", ".m2ts")

# Ausgabe-Container.
#
# MP4 bleibt die Vorgabe: es läuft auf Fernsehern, Handys und in Browsern am
# zuverlässigsten. MKV kann dafür mehr - verlustfreie Tonspuren wie TrueHD, die
# MP4 nicht aufnimmt, und Bitmap-Untertitel (PGS/VobSub), die beim Weg nach MP4
# verworfen werden müssen.
DEFAULT_CONTAINER = "mp4"
CONTAINERS = ["mp4", "mkv"]
CONTAINER_LABELS = {
    "mp4": "MP4 - überall abspielbar (Standard)",
    "mkv": "MKV - behält verlustfreien Ton und Bild-Untertitel",
}

# Namensbestandteile, die eine Filmdatei ohne S/E-Muster als Anime-Film erkennen lassen
ANIME_KEYWORDS = ["anime", "ova", "ona", "shonen", "seinen", "shojo", "isekai"]


def get_cq_description(cq_value: int) -> str:
    """Gibt eine verständliche Beschreibung für den CQ-Wert zurück."""
    if cq_value <= 25:
        return "Sehr hohe Qualität"
    elif cq_value <= 35:
        return "Hohe Qualität"
    elif cq_value <= 40:
        return "Ausgewogen"
    elif cq_value <= 45:
        return "Kompakt"
    return "Maximale Kompression"


class FileStatus(Enum):
    WARTEND = "Wartend"
    VERARBEITET = "Verarbeitet"
    FERTIG = "Fertig"
    FEHLER = "Fehler"
    UEBERSPRUNGEN = "Übersprungen"
    PAUSIERT = "Pausiert"


class NASUploadStatus(Enum):
    BEREIT = "Bereit"
    WIRD_VERSCHOBEN = "Wird verschoben..."
    FERTIG = "Fertig"
    FEHLER = "Fehler"
    UEBERSPRUNGEN = "Übersprungen"


class MediaType(Enum):
    """Medientyp einer Datei - wird einmal beim Scannen erkannt und danach
    sowohl für die Zielpfad-Erzeugung als auch für den NAS-Upload verwendet."""
    ANIME = "Anime"
    ANIME_FILME = "Anime Filme"
    FILME = "Filme"
    SERIEN = "Serien"
    UNBEKANNT = "Unbekannt"


# Kategorien, die auch als Zielordner in der Mediathek existieren
NAS_CATEGORIES = [MediaType.ANIME.value, MediaType.ANIME_FILME.value, MediaType.FILME.value, MediaType.SERIEN.value]

# Nicht jeder trennt seine Mediathek so fein. Ist eine Kategorie abgeschaltet,
# wird das Erkennungsergebnis auf die nächstpassende aktive Kategorie gefaltet:
# Anime zu Serien, Anime-Film zu Film, und falls auch die fehlt, jeweils
# umgekehrt. Erkannt wird also immer gleich, nur die Einsortierung folgt dem,
# was der Nutzer tatsächlich benutzt.
_FOLD_ORDER = {
    MediaType.ANIME: [MediaType.ANIME, MediaType.SERIEN, MediaType.FILME, MediaType.ANIME_FILME],
    MediaType.ANIME_FILME: [MediaType.ANIME_FILME, MediaType.FILME, MediaType.ANIME, MediaType.SERIEN],
    MediaType.FILME: [MediaType.FILME, MediaType.ANIME_FILME, MediaType.SERIEN, MediaType.ANIME],
    MediaType.SERIEN: [MediaType.SERIEN, MediaType.ANIME, MediaType.FILME, MediaType.ANIME_FILME],
}


def fold_to_enabled(media_type: MediaType, enabled: list) -> MediaType:
    """Bildet einen erkannten Medientyp auf die nächstbeste aktivierte Kategorie ab.

    `enabled` ist eine Liste von Kategorienamen (die .value der MediaType-Werte).
    Ist nichts aktiviert oder der Typ unbekannt, bleibt es beim Original."""
    if media_type == MediaType.UNBEKANNT or not enabled:
        return media_type
    if media_type.value in enabled:
        return media_type
    for candidate in _FOLD_ORDER.get(media_type, []):
        if candidate.value in enabled:
            return candidate
    return media_type

# Für "Getrennte Presets": Anime (Zeichentrick) komprimiert oft spürbar anders
# als Realfilm, daher zwei Buckets statt vier - jeder MediaType fällt in genau einen.
PRESET_BUCKETS = ["anime", "realfilm"]
PRESET_BUCKET_LABELS = {"anime": "Anime", "realfilm": "Serie/Film"}
_ANIME_MEDIA_TYPES = (MediaType.ANIME, MediaType.ANIME_FILME)


def preset_bucket_for(media_type: MediaType) -> str:
    """Ordnet einen MediaType einem der beiden Preset-Buckets zu.
    UNBEKANNT fällt mangels besserer Information auf 'realfilm' zurück."""
    return "anime" if media_type in _ANIME_MEDIA_TYPES else "realfilm"


@dataclass
class VideoMetadata:
    """Metadaten einer Videodatei (vor/nach der Konvertierung)."""
    video_codec: str = ""
    audio_codec: str = ""
    resolution: str = ""
    video_bitrate: str = ""
    audio_bitrate: str = ""
    duration: str = ""
    duration_seconds: float = 0.0  # numerischer Wert für ETA-Berechnungen, duration ist nur "HH:MM:SS"
    title: str = ""
    show_name: str = ""
    season: str = ""
    episode: str = ""

    # --- Für die Verlustvorschau vor dem Start (siehe format_warnings.py) ---
    #
    # Diese Angaben kosten nichts extra: get_video_metadata ruft ffprobe schon
    # mit -show_streams auf und hat sie längst in der Hand, hat sie bisher aber
    # verworfen. Ohne sie liesse sich vor dem Lauf nicht sagen, was die gewählte
    # Kombination aus Codec und Container kostet.
    pixel_format: str = ""          # z.B. "yuv420p10le"
    bit_depth: int = 0              # 0 = unbekannt
    color_transfer: str = ""        # "smpte2084" = HDR10, "arib-std-b67" = HLG
    dolby_vision: bool = False
    # Alle Tonspuren, nicht nur die erste - eine Datei kann Deutsch in AC-3 und
    # das Original in TrueHD führen, und nur die zweite sprengt MP4.
    audio_codecs: list = field(default_factory=list)
    audio_profiles: list = field(default_factory=list)   # gleiche Reihenfolge
    subtitle_codecs: list = field(default_factory=list)

    def is_hdr(self) -> bool:
        """HDR10 (PQ) oder HLG. Beides braucht mehr als 8 Bit."""
        return self.color_transfer in ("smpte2084", "arib-std-b67")


@dataclass
class NASUploadItem:
    """Repräsentation eines Mediums für NAS-Upload."""
    folder_path: Path
    name: str
    media_type: MediaType = MediaType.UNBEKANNT
    target_category: str = "Serien"
    status: NASUploadStatus = NASUploadStatus.BEREIT
    total_size: int = 0
    has_season_folders: bool = False
    error_message: str = ""

    def __post_init__(self):
        if self.folder_path.exists():
            self.total_size = sum(
                f.stat().st_size for f in self.folder_path.rglob("*") if f.is_file()
            )


@dataclass
class VideoFile:
    """Repräsentation einer zu konvertierenden Videodatei."""
    source_path: Path
    media_type: MediaType = MediaType.UNBEKANNT
    series_name: Optional[str] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    movie_name: Optional[str] = None
    target_path: Optional[Path] = None
    status: FileStatus = FileStatus.WARTEND
    progress: int = 0
    original_size: int = 0
    new_size: int = 0
    error_message: str = ""
    source_metadata: Optional[VideoMetadata] = None
    target_metadata: Optional[VideoMetadata] = None
    conversion_start_time: Optional[float] = None
    conversion_end_time: Optional[float] = None

    # Abweichung von der globalen Einstellung, nur für diese Datei.
    #
    # Wird gesetzt, wenn der Nutzer in der Verlustvorschau vor dem Start
    # zustimmt, betroffene Dateien umzustellen (siehe format_warnings.py). Leer
    # heisst "folge der Einstellung" - wer die Vorschau nie sieht, merkt von
    # diesen Feldern nichts.
    #
    # Bewusst je Datei und nicht global: hat eine Staffel drei Folgen mit
    # Bild-Untertiteln, sollen nur die drei nach MKV wandern und nicht die ganze
    # Auswahl. Bei Serien wird die Umstellung allerdings auf die ganze Staffel
    # ausgedehnt, damit ein Staffelordner nicht halb MP4 und halb MKV wird.
    codec_override: Optional[str] = None
    container_override: Optional[str] = None

    def __post_init__(self):
        if self.source_path.exists():
            self.original_size = self.source_path.stat().st_size
