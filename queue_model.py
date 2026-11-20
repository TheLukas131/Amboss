"""Was die Warteschlange anzeigt - ohne Oberfläche, damit es sich prüfen lässt.

Die Tabelle selbst (ui/queue_table.py) zeichnet nur. Welche Zeilen es gibt, was
in ihnen steht und welche gerade sichtbar sind, entscheidet sich hier.

Drei Dinge ändern sich gegenüber der flachen Liste von früher:

*Folgen einer Staffel stehen unter einer gemeinsamen Zeile.* Eine Staffel mit
24 Folgen waren 24 gleich aussehende Zeilen, zwischen denen der eine Film
unterging. Jetzt ist es eine Zeile mit Gesamtfortschritt, die sich aufklappen
lässt.

*Das Ziel steht relativ zum Zielordner.* Der volle Pfad begann in jeder Zeile
mit demselben Stück und brach deshalb um; der Teil, der sich unterscheidet,
stand am Ende und oft schon in der zweiten Zeile.

*Eine laufende Datei zeigt Zahlen.* Bilder pro Sekunde und Restzeit statt nur
eines Balkens, und nach dem Abschluss die Größe vorher und nachher.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from models import FileStatus, MediaType, VideoFile

_FERTIG = (FileStatus.FERTIG, FileStatus.UEBERSPRUNGEN)
_SERIEN = (MediaType.ANIME, MediaType.SERIEN)

# Ab dieser Länge der Warteschlange starten Staffeln zugeklappt. Darunter passt
# ohnehin alles auf den Bildschirm, und eine Zeile mehr zu sehen ist dann
# nützlicher als eine gesparte.
COLLAPSE_ABOVE = 12

FILTER_KEYS = ("all", "waiting", "processing", "done", "error")


def format_size(size_bytes: int) -> str:
    if size_bytes == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    size = float(size_bytes)
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    return f"{size:.2f} {units[unit_index]}"


def format_size_short(size_bytes: int) -> str:
    """Wie format_size, aber auf drei Stellen: '2.6 GB', '640 MB'.

    Für die Tabelle, in der zwei Größen nebeneinander in eine Spalte müssen.
    Die zweite Nachkommastelle unterscheidet dort nichts, was jemand wissen
    will, kostet aber die Breite, an der der Text sonst abgeschnitten wird."""
    if size_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    size = float(size_bytes)
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    return f"{size:.0f} {units[unit_index]}" if size >= 100 else f"{size:.1f} {units[unit_index]}"


def format_duration(seconds: float) -> str:
    """'03:12' unter einer Stunde, sonst '1:03:12'."""
    seconds = max(int(seconds), 0)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def matches_filter(status: FileStatus, key: str) -> bool:
    if key == "waiting":
        return status == FileStatus.WARTEND
    if key == "processing":
        return status == FileStatus.VERARBEITET
    if key == "done":
        return status in _FERTIG
    if key == "error":
        return status == FileStatus.FEHLER
    return True


def status_counts(videos: List[VideoFile]) -> Dict[str, int]:
    """Wie viele Dateien jeder Filter zeigen würde."""
    return {key: sum(1 for v in videos if matches_filter(v.status, key))
            for key in FILTER_KEYS}


def relative_target(target: Optional[Path], output_base: Optional[Path]) -> str:
    """Der Zielpfad ohne den Teil, der in jeder Zeile gleich ist.

    Liegt das Ziel nicht unter dem Zielordner (anders geschrieben, oder der
    Ordner wurde nach dem Scan geändert), bleibt der volle Pfad stehen - ein zu
    langer Text ist besser als ein falscher."""
    if not target:
        return "-"
    if output_base is not None:
        try:
            return str(target.relative_to(output_base))
        except ValueError:
            pass
    return str(target)


def size_change(original: int, new: int) -> str:
    """'2.6 GB → 640 MB (−75 %)'. Ohne Ergebnis nur die Ausgangsgröße."""
    if new <= 0 or original <= 0:
        return format_size_short(original)
    change = (new - original) / original * 100
    # Echtes Minuszeichen: ein Bindestrich vor einer Zahl liest sich wie ein
    # Gedankenstrich.
    sign = "−" if change < 0 else "+"
    return (f"{format_size_short(original)} → {format_size_short(new)} "
            f"({sign}{abs(change):.0f} %)")


def remaining_seconds(video: VideoFile) -> Optional[float]:
    """Restzeit einer laufenden Datei, aus dem Tempo, das ffmpeg selbst meldet."""
    if video.status != FileStatus.VERARBEITET or video.encode_speed <= 0:
        return None
    duration = video.source_metadata.duration_seconds if video.source_metadata else 0
    if not duration:
        return None
    return duration * (1 - video.progress / 100) / video.encode_speed


@dataclass
class Group:
    """Eine Staffel: mehrere Folgen unter einer gemeinsamen Zeile."""

    key: Tuple
    name: str
    season: Optional[int]
    media_type: MediaType
    indices: List[int] = field(default_factory=list)


def group_key(video: VideoFile) -> Optional[Tuple]:
    """Wozu eine Datei gehört - None für alles, was allein steht (Filme)."""
    if video.media_type not in _SERIEN or not video.series_name:
        return None
    return (video.media_type, video.series_name.lower(), video.season)


@dataclass
class Row:
    """Eine Zeile der Tabelle: entweder eine Staffel oder eine Datei."""

    group: Optional[Group] = None      # gesetzt bei einer Staffel-Zeile
    index: Optional[int] = None        # gesetzt bei einer Datei-Zeile
    parent: Optional[Group] = None     # die Staffel, unter der die Datei steht

    @property
    def is_group(self) -> bool:
        return self.group is not None


def build_rows(videos: List[VideoFile]) -> List[Row]:
    """Ordnet die Warteschlange in Zeilen.

    Eine Staffel-Zeile gibt es erst ab zwei Folgen - eine einzelne Folge unter
    eine eigene Überschrift zu stellen, verdoppelt nur die Zeile. Staffeln
    stehen dort, wo ihre erste Folge in der Liste steht, die Folgen darunter
    in ihrer Reihenfolge."""
    groups: Dict[Tuple, Group] = {}
    for index, video in enumerate(videos):
        key = group_key(video)
        if key is None:
            continue
        if key not in groups:
            groups[key] = Group(key, video.series_name, video.season, video.media_type)
        groups[key].indices.append(index)

    rows: List[Row] = []
    placed = set()
    for index, video in enumerate(videos):
        key = group_key(video)
        group = groups.get(key) if key is not None else None
        if group is None or len(group.indices) < 2:
            rows.append(Row(index=index))
            continue
        if key in placed:
            continue
        placed.add(key)
        rows.append(Row(group=group))
        ordered = sorted(group.indices,
                         key=lambda i: (videos[i].episode is None, videos[i].episode or 0, i))
        rows.extend(Row(index=i, parent=group) for i in ordered)
    return rows


@dataclass
class GroupSummary:
    total: int
    done: int
    running: int
    failed: int
    progress: int
    original_size: int
    new_size: int          # 0, solange nicht alle Folgen fertig sind


def summarize(group: Group, videos: List[VideoFile]) -> GroupSummary:
    members = [videos[i] for i in group.indices if i < len(videos)]
    total = len(members)
    done = sum(1 for v in members if v.status in _FERTIG)
    progress = (sum(100 if v.status in _FERTIG else v.progress for v in members) // total
                if total else 0)
    converted = [v for v in members if v.new_size > 0]
    # Vorher gegen nachher erst, wenn beides dieselben Dateien meint - sonst
    # stünde die ganze Staffel gegen die drei Folgen, die schon fertig sind.
    complete = total > 0 and len(converted) == total
    return GroupSummary(
        total=total,
        done=done,
        running=sum(1 for v in members if v.status == FileStatus.VERARBEITET),
        failed=sum(1 for v in members if v.status == FileStatus.FEHLER),
        progress=progress,
        original_size=sum(v.original_size for v in members),
        new_size=sum(v.new_size for v in converted) if complete else 0,
    )
