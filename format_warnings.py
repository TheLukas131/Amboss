"""Was die gewählte Kombination aus Codec und Container kostet - vor dem Start.

Amboss löscht Quelldateien, sobald die Ausgabe geprüft ist. Damit ist der
gefährlichste Fehler nicht der Absturz, sondern der stille Verlust: eine Datei,
die durchläuft, die Prüfung besteht und trotzdem schlechter ist als das Original,
das danach verschwindet. Laufzeit und Streamzahl stimmen dann nämlich - nur die
Bildqualität nicht, und das sieht man erst beim Anschauen.

Bisher stand das nur in der README. Dieses Modul beantwortet die Frage vor dem
Lauf: was geht bei diesen Dateien mit dieser Einstellung verloren, und was wäre
die passende Einstellung?

Bewusst ohne Qt und ohne Dateizugriff: die Regeln arbeiten auf den Metadaten,
die beim Scannen ohnehin gelesen wurden (siehe VideoMetadata), und lassen sich
damit einzeln prüfen. Die Anzeige steckt in ui/format_warning_dialog.py.

Auch bewusst **ohne Übersetzung**: die Texte stehen hier als deutsche
Originale, übersetzt wird erst bei der Anzeige. Andernfalls klebt die Sprache
am Befund, in der sie beim Auswerten gerade eingestellt war - was auffiel, als
ein Test die Sprache nach dem Auswerten umstellte und die Texte deutsch blieben.
In der Anwendung steht die Sprache zwar beim Start fest, aber eine Regel, die
Anzeigetexte festschreibt, ist trotzdem an der falschen Stelle übersetzt.
"""

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from ffmpeg_processor import chroma_fallback
from models import MediaType, VideoFile

# Untertitel, die als Bild vorliegen. MP4 kann sie nicht aufnehmen; Amboss
# überspringt sie, damit der Encode überhaupt gelingt - sie fehlen danach.
BITMAP_SUBTITLES = {"hdmv_pgs_subtitle", "dvd_subtitle", "dvbsub",
                    "dvb_subtitle", "xsub"}

# Untertitel mit Positionierung. Nach MP4 werden sie zu mov_text, womit die
# Platzierung getypter Schilder verlorengeht - der Text bleibt.
POSITIONED_SUBTITLES = {"ass", "ssa"}

# Tonspuren, die FFmpeg nicht in eine MP4 schreibt. Der Lauf scheitert dann,
# statt die Spur stillschweigend zu verlieren.
LOSSLESS_AUDIO = {"truehd", "mlp"}
LOSSLESS_DTS_PROFILES = ("dts-hd ma", "dts-hd master")

# Encoder-Grenzen der NVENC-Hardware. Kein Preset ändert daran etwas.
MAX_BIT_DEPTH = {"av1_nvenc": 10, "hevc_nvenc": 10, "h264_nvenc": 8}

SEVERITY_FAILS = "fails"            # der Lauf bricht ab
SEVERITY_LOSES = "loses"            # läuft durch, Ergebnis ist schlechter
SEVERITY_UNAVOIDABLE = "unavoidable"  # Verlust ohne Abhilfe, nur zur Kenntnis


@dataclass
class Finding:
    """Ein Befund über eine Gruppe von Dateien.

    `problem` und `remedy` sind deutsche Originaltexte ohne Zahlen - übersetzt
    und mit Anzahlen versehen werden sie erst in der Anzeige."""
    key: str                    # stabile Kennung, auch für "nicht mehr fragen"
    severity: str
    problem: str
    videos: List[VideoFile] = field(default_factory=list)
    remedy: str = ""            # leer = keine Abhilfe möglich
    remedy_codec: Optional[str] = None
    remedy_container: Optional[str] = None

    @property
    def has_remedy(self) -> bool:
        return bool(self.remedy_codec or self.remedy_container)


def _lossless_audio(video: VideoFile) -> bool:
    meta = video.source_metadata
    if meta is None:
        return False
    for codec, profil in zip(meta.audio_codecs, meta.audio_profiles):
        if (codec or "").lower() in LOSSLESS_AUDIO:
            return True
        if (codec or "").lower() == "dts":
            niedrig = (profil or "").lower()
            if any(p in niedrig for p in LOSSLESS_DTS_PROFILES):
                return True
    return False


def _has_subtitle(video: VideoFile, codecs: set) -> bool:
    meta = video.source_metadata
    if meta is None:
        return False
    return any((c or "").lower() in codecs for c in meta.subtitle_codecs)


def _bit_depth(video: VideoFile) -> int:
    meta = video.source_metadata
    return meta.bit_depth if meta else 0


def _is_hdr(video: VideoFile) -> bool:
    meta = video.source_metadata
    return bool(meta and meta.is_hdr())


def find_losses(videos: List[VideoFile],
                codec_for: Callable[[VideoFile], str],
                container: str) -> List[Finding]:
    """Sammelt, was bei diesen Dateien mit dieser Einstellung verloren geht.

    `codec_for` liefert den Codec je Datei - bei getrennten Presets ist er nicht
    für alle derselbe. `container` ist die globale Auswahl ("mp4"/"mkv").

    Die Reihenfolge der Befunde ist die der Schwere: erst was den Lauf abbricht,
    dann was das Ergebnis verschlechtert, zuletzt was ohnehin nicht zu ändern
    ist."""
    ist_mp4 = (container or "mp4").lower() != "mkv"
    befunde: List[Finding] = []

    def ergaenzen(key, severity, pruefung, problem, remedy="",
                  remedy_codec=None, remedy_container=None):
        betroffen = [v for v in videos if pruefung(v)]
        if not betroffen:
            return
        befunde.append(Finding(
            key=key, severity=severity, problem=problem, videos=betroffen,
            remedy=remedy, remedy_codec=remedy_codec,
            remedy_container=remedy_container,
        ))

    # --- Was den Lauf abbricht -------------------------------------------
    if ist_mp4:
        ergaenzen(
            "lossless_audio_mp4", SEVERITY_FAILS,
            _lossless_audio,
            "Verlustfreie Tonspur (TrueHD oder DTS-HD MA). MP4 nimmt sie "
            "nicht auf - die Konvertierung bricht ab.",
            "Auf MKV umstellen, dann bleibt die Spur unverändert erhalten.",
            remedy_container="mkv",
        )

    # --- Was durchläuft, aber schlechter wird ----------------------------
    if ist_mp4:
        ergaenzen(
            "bitmap_subs_mp4", SEVERITY_LOSES,
            lambda v: _has_subtitle(v, BITMAP_SUBTITLES),
            "Bild-Untertitel (PGS oder VobSub). MP4 kann sie nicht "
            "speichern, sie werden verworfen.",
            "Auf MKV umstellen, dann bleiben sie erhalten.",
            remedy_container="mkv",
        )
        ergaenzen(
            "positioned_subs_mp4", SEVERITY_LOSES,
            lambda v: _has_subtitle(v, POSITIONED_SUBTITLES),
            "ASS-Untertitel. Nach MP4 werden sie zu mov_text - der Text "
            "bleibt, die Positionierung getypter Schilder geht verloren.",
            "Auf MKV umstellen, dann bleiben sie unverändert.",
            remedy_container="mkv",
        )

    ergaenzen(
        "bit_depth_h264", SEVERITY_LOSES,
        lambda v: (codec_for(v) == "h264_nvenc"
                   and (_bit_depth(v) > MAX_BIT_DEPTH["h264_nvenc"] or _is_hdr(v))),
        "Mehr als 8 Bit oder HDR. H.264 über NVENC kann nur 8 Bit - das "
        "Bild wird heruntergerechnet und verliert seinen HDR-Charakter.",
        "Auf H.265 umstellen, das 10 Bit beherrscht.",
        remedy_codec="hevc_nvenc",
    )

    ergaenzen(
        "chroma_av1", SEVERITY_LOSES,
        lambda v: bool(chroma_fallback(
            v.source_metadata.pixel_format if v.source_metadata else "",
            codec_for(v))),
        "Farbabtastung feiner als 4:2:0. AV1 über NVENC nimmt nur 4:2:0 an; "
        "die Farbauflösung wird reduziert. Die Bittiefe bleibt.",
        "Auf H.265 umstellen, das 4:4:4 direkt annimmt.",
        remedy_codec="hevc_nvenc",
    )

    # --- Verluste ohne Abhilfe -------------------------------------------
    ergaenzen(
        "bit_depth_over_10", SEVERITY_UNAVOIDABLE,
        lambda v: _bit_depth(v) > 10 and codec_for(v) != "h264_nvenc",
        "Mehr als 10 Bit. NVENC kodiert höchstens 10 Bit, mehr ist mit "
        "dieser Hardware nicht möglich - mehr gibt aber auch kein "
        "Abspielgerät aus.",
    )

    ergaenzen(
        "dolby_vision", SEVERITY_UNAVOIDABLE,
        lambda v: bool(v.source_metadata and v.source_metadata.dolby_vision),
        "Dolby Vision. Die Kennung übersteht keine Neukodierung über NVENC. "
        "Ist eine HDR10-Basis vorhanden, bleibt das Bild HDR.",
    )

    reihenfolge = {SEVERITY_FAILS: 0, SEVERITY_LOSES: 1, SEVERITY_UNAVOIDABLE: 2}
    befunde.sort(key=lambda b: (reihenfolge.get(b.severity, 9), -len(b.videos)))
    return befunde


def expand_to_seasons(betroffen: List[VideoFile],
                      alle: List[VideoFile]) -> List[VideoFile]:
    """Weitet eine Auswahl bei Serien auf die ganze Staffel aus.

    Hat eine Staffel mit 24 Folgen nur bei drei davon Bild-Untertitel, würde
    eine Umstellung allein dieser drei einen Staffelordner hinterlassen, der zur
    Hälfte MP4 und zur Hälfte MKV ist. Abspielen tut das jeder Mediaserver, aber
    ordentlich ist es nicht - und MKV kostet die übrigen 21 nichts.

    Filme bleiben einzeln: sie liegen jeder in seinem eigenen Ordner, da gibt es
    keine Einheit zu bewahren."""
    kennungen = {id(v) for v in betroffen}
    ausgeweitet = list(betroffen)

    staffeln = {
        (v.media_type, v.series_name, v.season)
        for v in betroffen
        if v.media_type in (MediaType.ANIME, MediaType.SERIEN) and v.series_name
    }
    if not staffeln:
        return ausgeweitet

    for video in alle:
        if id(video) in kennungen:
            continue
        if (video.media_type, video.series_name, video.season) in staffeln:
            ausgeweitet.append(video)
            kennungen.add(id(video))
    return ausgeweitet


def apply_finding(finding: Finding, alle: List[VideoFile]) -> List[VideoFile]:
    """Setzt die Abhilfe des Befunds auf den betroffenen Dateien.

    Gibt zurück, welche Dateien geändert wurden - der Aufrufer muss danach ihre
    Zielpfade neu berechnen, weil ein anderer Container eine andere Endung
    bedeutet."""
    if not finding.has_remedy:
        return []

    betroffen = expand_to_seasons(finding.videos, alle)
    for video in betroffen:
        if finding.remedy_codec:
            video.codec_override = finding.remedy_codec
        if finding.remedy_container:
            video.container_override = finding.remedy_container
    return betroffen


def dismissal_key(finding: Finding, container: str, codec: str) -> str:
    """Kennung für "diesen Hinweis nicht mehr zeigen".

    Enthält die Einstellung, auf die sich der Hinweis bezog: wer später einen
    anderen Codec oder Container wählt, bekommt ihn wieder - dann ist es eine
    andere Entscheidung."""
    return f"{finding.key}|{(container or '').lower()}|{(codec or '').lower()}"
