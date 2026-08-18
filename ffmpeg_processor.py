"""FFmpeg/FFprobe Integration: Befehle bauen, Metadaten lesen, Encoder prüfen."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from models import HEVC_MP4_TAG, MediaType, VideoFile, VideoMetadata

_CREATIONFLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


# Untertitel-Codecs, die sich verlustfrei nach MP4 (mov_text) überführen lassen.
# Bitmap-Formate wie hdmv_pgs_subtitle oder dvd_subtitle können das NICHT - ein
# Versuch würde den kompletten Encode mit einem Fehler abbrechen, deshalb werden
# sie übersprungen statt gemappt.
_TEXT_SUBTITLE_CODECS = {"subrip", "srt", "ass", "ssa", "mov_text", "webvtt", "text"}


# Quell-Pixelformate, die av1_nvenc nicht annimmt, mit dem jeweils passenden
# Ersatz.
#
# Der Encoder lehnt alles ab, was nicht 4:2:0 ist, und meldet dabei
# "No capable devices found" - eine Meldung, die nach fehlender oder defekter
# Grafikkarte klingt und nicht nach einem Formatproblem. Bis hierher scheiterte
# eine solche Datei einfach.
#
# Umgerechnet wird ausschliesslich die Chroma-Unterabtastung, die Bittiefe
# bleibt: ein pauschales '-pix_fmt yuv420p' wuerde eine 10-Bit- oder HDR-Quelle
# auf 8 Bit herunterziehen und damit genau das Banding erzeugen, das man bei HDR
# als Erstes sieht. Ueber 10 Bit kann AV1 via NVENC nicht, 12- und 16-Bit-Quellen
# landen deshalb bei 10 Bit - immer noch mehr, als jedes Abspielgeraet ausgibt.
#
# Bewusst eine Aufzaehlung statt einer Namensanalyse: ffmpeg kennt weit ueber
# hundert Pixelformate, und ein Muster, das sich verschaetzt, wuerde entweder
# unnoetig umrechnen (stiller Qualitaetsverlust) oder den Fall verpassen. Was
# hier nicht steht, wird nicht angetastet - dann scheitert die Datei wie bisher,
# und ein sichtbarer Fehler ist besser als ein heimlich schlechteres Bild.
CHROMA_FALLBACK = {
    # 4:4:4, 8 Bit
    "yuv444p": "yuv420p",
    "yuvj444p": "yuv420p",
    "gbrp": "yuv420p",
    # 4:4:4, 10 Bit und mehr
    "yuv444p10le": "yuv420p10le",
    "yuv444p10be": "yuv420p10le",
    "yuv444p12le": "yuv420p10le",
    "yuv444p12be": "yuv420p10le",
    "yuv444p16le": "yuv420p10le",
    "yuv444p16be": "yuv420p10le",
    "gbrp10le": "yuv420p10le",
    "gbrp12le": "yuv420p10le",
    # 4:2:2 - derselbe Fall, dieselbe irrefuehrende Meldung
    "yuv422p": "yuv420p",
    "yuvj422p": "yuv420p",
    "yuv422p10le": "yuv420p10le",
    "yuv422p10be": "yuv420p10le",
    "yuv422p12le": "yuv420p10le",
    "p210le": "yuv420p10le",
    # 4:4:0 - selten, aber ebenso kein 4:2:0
    "yuv440p": "yuv420p",
    "yuvj440p": "yuv420p",
}

# Encoder, fuer die das ueberhaupt gilt.
#
# hevc_nvenc nimmt 4:4:4 an - gemessen an derselben Datei auf derselben Karte,
# die als AV1 abgelehnt und als H.265 durchlief. h264_nvenc beherrscht das
# 4:4:4-Profil ebenfalls. Fuer die wird deshalb nichts angetastet: eine
# Umrechnung, die niemand braucht, ist reiner Verlust.
_NEEDS_420 = ("av1_nvenc",)


def _bittiefe(stream: dict) -> int:
    """Bittiefe einer Videospur. 0, wenn nicht zu ermitteln.

    ffprobe meldet sie nicht immer: `bits_per_raw_sample` fehlt bei manchen
    Containern. Dann wird sie aus dem Pixelformat gelesen - dort steht sie im
    Namen (`yuv420p10le`), und ohne Zahl sind es 8."""
    for schluessel in ("bits_per_raw_sample", "bits_per_sample"):
        wert = stream.get(schluessel)
        try:
            tiefe = int(wert)
        except (TypeError, ValueError):
            continue
        if tiefe > 0:
            return tiefe

    pix_fmt = (stream.get("pix_fmt") or "").lower()
    if not pix_fmt:
        return 0
    for tiefe in (16, 14, 12, 10, 9):
        if str(tiefe) in pix_fmt:
            return tiefe
    return 8


def _hat_dolby_vision(stream: dict) -> bool:
    """Ob die Spur eine Dolby-Vision-Kennung traegt.

    Erkannt wird der Konfigurationsblock, den ffprobe als Zusatzdaten ausgibt.
    Bestenfalls-Erkennung: fehlt der Block, heisst das nicht zwingend, dass kein
    Dolby Vision vorliegt - aber falsch positiv wird es dadurch nicht."""
    for zusatz in stream.get("side_data_list") or []:
        if not isinstance(zusatz, dict):
            continue
        text = " ".join(str(w) for w in zusatz.values()).lower()
        if "dolby vision" in text or "dovi" in text:
            return True
    return "dolby vision" in (stream.get("profile") or "").lower()


def chroma_fallback(pixel_format: str, codec: str) -> Optional[str]:
    """Das Pixelformat, auf das umgerechnet werden muss - oder None.

    None heisst "nichts tun", und zwar in drei Faellen: der Encoder kommt mit
    dem Format zurecht, die Quelle ist ohnehin 4:2:0, oder das Format ist
    unbekannt. Der letzte Fall ist Absicht, siehe CHROMA_FALLBACK."""
    if codec not in _NEEDS_420:
        return None
    return CHROMA_FALLBACK.get((pixel_format or "").strip().lower())


class FFmpegProcessor:
    """Handhabt die FFmpeg/FFprobe-Aufrufe."""

    def __init__(self):
        self.ffmpeg_path = self._find_binary("ffmpeg")
        self.ffprobe_path = self._find_binary("ffprobe")
        self._encoder_cache: Optional[str] = None

    @staticmethod
    def _find_binary(name: str) -> str:
        """Sucht eine ffmpeg/ffprobe-Binary im PATH oder im Programmordner."""
        for cmd in (name, f"{name}.exe"):
            try:
                result = subprocess.run(
                    [cmd, "-version"], capture_output=True, timeout=5,
                    creationflags=_CREATIONFLAGS,
                )
                if result.returncode == 0:
                    return cmd
            except (subprocess.SubprocessError, FileNotFoundError, OSError):
                continue

        app_dir = Path(__file__).parent
        for subdir in ("", name, f"{name}/bin"):
            candidate = app_dir / subdir / f"{name}.exe"
            if candidate.exists():
                return str(candidate)

        return name

    def is_available(self) -> bool:
        """Prüft, ob die ffmpeg-Binary tatsächlich aufrufbar ist."""
        try:
            result = subprocess.run(
                [self.ffmpeg_path, "-version"], capture_output=True, timeout=5,
                creationflags=_CREATIONFLAGS,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            return False

    def check_encoder_available(self, encoder: str) -> bool:
        """Prüft, ob ein bestimmter Encoder (z.B. av1_nvenc oder h264_nvenc) verfügbar ist.

        Die Encoder-Liste ändert sich zur Laufzeit nicht, wird also nur einmal pro
        Programmstart abgefragt - vorher lief bei jedem Codec-Wechsel in der UI ein
        eigener ffmpeg-Aufruf mit bis zu 10 s Timeout."""
        if self._encoder_cache is None:
            try:
                result = subprocess.run(
                    [self.ffmpeg_path, "-encoders"], capture_output=True, text=True,
                    timeout=10, creationflags=_CREATIONFLAGS,
                )
                self._encoder_cache = result.stdout
            except (subprocess.SubprocessError, OSError):
                return False
        return encoder in self._encoder_cache

    def get_text_subtitle_indices(self, filepath: Path) -> List[int]:
        """Gibt die Positionen der textbasierten Untertitelspuren zurück (gezählt
        nur unter den Untertitelspuren, passend zur ffmpeg-Syntax '0:s:N').

        Bitmap-Untertitel werden bewusst weggelassen - siehe _TEXT_SUBTITLE_CODECS."""
        try:
            result = subprocess.run([
                self.ffprobe_path, "-v", "error",
                "-select_streams", "s",
                "-show_entries", "stream=codec_name",
                "-of", "json", str(filepath),
            ], capture_output=True, text=True, timeout=30, creationflags=_CREATIONFLAGS)
            if result.returncode != 0:
                return []
            streams = json.loads(result.stdout).get("streams", [])
        except (subprocess.SubprocessError, ValueError, json.JSONDecodeError, OSError):
            return []

        return [
            i for i, stream in enumerate(streams)
            if (stream.get("codec_name") or "").lower() in _TEXT_SUBTITLE_CODECS
        ]

    def get_duration(self, filepath: Path) -> float:
        """Ermittelt die Dauer einer Videodatei in Sekunden."""
        try:
            result = subprocess.run([
                self.ffprobe_path, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(filepath),
            ], capture_output=True, text=True, timeout=30, creationflags=_CREATIONFLAGS)
            return float(result.stdout.strip())
        except (subprocess.SubprocessError, ValueError, OSError):
            return 0.0

    def count_streams(self, filepath: Path) -> Dict[str, int]:
        """Zählt Video-, Audio- und Untertitelspuren einer Datei.

        Dient dem Abgleich zwischen Quelle und Ergebnis: eine Konvertierung, die
        eine zweite Tonspur verliert, erzeugt trotzdem eine abspielbare Datei
        richtiger Länge. Ohne diesen Vergleich fiele so etwas erst auf, wenn die
        Quelldatei längst gelöscht ist."""
        counts = {"video": 0, "audio": 0, "subtitle": 0}
        try:
            result = subprocess.run([
                self.ffprobe_path, "-v", "error",
                "-show_entries", "stream=index,codec_type",
                "-of", "json", str(filepath),
            ], capture_output=True, text=True, timeout=30, creationflags=_CREATIONFLAGS)
            streams = json.loads(result.stdout).get("streams", [])
        except (subprocess.SubprocessError, ValueError, json.JSONDecodeError, OSError):
            return counts

        # Nach Index eindeutig machen: MPEG-TS führt jeden Stream sowohl global
        # als auch unter seinem Programm auf, ffprobe gibt ihn dann zweimal aus.
        # Ungeprüft gezählt ergäbe eine .ts-Datei mit zwei Tonspuren derer vier -
        # und die Vollständigkeitsprüfung würde jede .ts-Konvertierung verwerfen.
        gesehen = set()
        for stream in streams:
            index = stream.get("index")
            if index in gesehen:
                continue
            gesehen.add(index)
            kind = stream.get("codec_type")
            if kind in counts:
                counts[kind] += 1
        return counts

    def pixel_format(self, filepath: Path) -> str:
        """Pixelformat der ersten Videospur, etwa 'yuv420p'.

        Leer, wenn es nicht zu ermitteln ist - dann wird auch nichts umgerechnet
        (siehe chroma_fallback)."""
        try:
            result = subprocess.run([
                self.ffprobe_path, "-v", "error",
                # Nur die primaere Videospur; ein eingebettetes Cover-Bild haette
                # ein eigenes Format und ist hier ohne Belang.
                "-select_streams", "v:0",
                "-show_entries", "stream=pix_fmt",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(filepath),
            ], capture_output=True, text=True, timeout=30, creationflags=_CREATIONFLAGS)
            zeilen = [z.strip() for z in result.stdout.splitlines() if z.strip()]
            return zeilen[0] if zeilen else ""
        except (subprocess.SubprocessError, OSError):
            return ""

    def get_video_metadata(self, filepath: Path) -> VideoMetadata:
        """Ermittelt detaillierte Metadaten einer Videodatei mit FFprobe."""
        metadata = VideoMetadata()
        try:
            result = subprocess.run([
                self.ffprobe_path, "-v", "quiet",
                "-print_format", "json",
                "-show_format", "-show_streams",
                str(filepath),
            ], capture_output=True, text=True, timeout=30, creationflags=_CREATIONFLAGS)

            if result.returncode != 0:
                return metadata

            data = json.loads(result.stdout)
            fmt = data.get("format", {})
            duration_secs = float(fmt.get("duration", 0))
            hours = int(duration_secs // 3600)
            minutes = int((duration_secs % 3600) // 60)
            seconds = int(duration_secs % 60)
            metadata.duration = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            metadata.duration_seconds = duration_secs

            tags = fmt.get("tags", {})
            metadata.title = tags.get("title", tags.get("TITLE", ""))
            metadata.show_name = tags.get("show", tags.get("SHOW", ""))
            metadata.season = tags.get("season_number", tags.get("SEASON_NUMBER", ""))
            metadata.episode = tags.get("episode_sort", tags.get("episode_id", tags.get("EPISODE_SORT", "")))

            erste_videospur = True
            for stream in data.get("streams", []):
                codec_type = stream.get("codec_type", "")
                if codec_type == "video":
                    if not erste_videospur:
                        # Eingebettete Cover-Bilder (mjpeg) sind formal
                        # Videospuren; sie dürfen die Angaben der echten nicht
                        # überschreiben.
                        continue
                    erste_videospur = False

                    metadata.video_codec = stream.get("codec_name", "Unbekannt")
                    width = stream.get("width", 0)
                    height = stream.get("height", 0)
                    metadata.resolution = f"{width}x{height}"

                    metadata.pixel_format = stream.get("pix_fmt", "") or ""
                    metadata.color_transfer = stream.get("color_transfer", "") or ""
                    metadata.bit_depth = _bittiefe(stream)
                    metadata.dolby_vision = _hat_dolby_vision(stream)

                    bit_rate = stream.get("bit_rate", "")
                    if bit_rate:
                        metadata.video_bitrate = f"{int(bit_rate) / 1_000_000:.2f} Mbps"
                    else:
                        total_br = fmt.get("bit_rate", "")
                        if total_br:
                            metadata.video_bitrate = f"~{int(total_br) / 1_000_000:.2f} Mbps (gesamt)"

                elif codec_type == "audio":
                    metadata.audio_codecs.append(stream.get("codec_name", "") or "")
                    metadata.audio_profiles.append(stream.get("profile", "") or "")
                    if not metadata.audio_codec:
                        metadata.audio_codec = stream.get("codec_name", "Unbekannt")
                        audio_br = stream.get("bit_rate", "")
                        if audio_br:
                            metadata.audio_bitrate = f"{int(audio_br) / 1000:.0f} kbps"

                elif codec_type == "subtitle":
                    metadata.subtitle_codecs.append(stream.get("codec_name", "") or "")

        except (subprocess.SubprocessError, ValueError, json.JSONDecodeError, OSError):
            pass

        return metadata

    def build_command(self, video: VideoFile, cq: int, preset: str,
                       normalize_audio: bool, codec: str, output_path: Path,
                       text_subtitle_indices: Optional[List[int]] = None,
                       source_pixel_format: Optional[str] = None) -> List[str]:
        """Erstellt den FFmpeg-Befehl.

        NVENC verwendet '-cq' für Constant Quality (nicht '-crf') und '-preset'
        mit Werten p1-p7 - das gilt für av1_nvenc genauso wie für h264_nvenc.
        Der Zielpfad wird explizit übergeben statt video.target_path zu lesen,
        damit während des Encodings in eine temporäre Datei geschrieben werden
        kann (siehe ConversionWorker).

        Die -map-Angaben sind wichtig: ohne sie wählt ffmpeg pro Streamtyp nur
        EINEN Stream aus. Bei Anime mit deutscher UND japanischer Tonspur wäre die
        zweite Spur (und jeder Untertitel) beim Konvertieren stillschweigend
        verschwunden - fatal, wenn die Quelldatei danach gelöscht oder aufs NAS
        verschoben wird.

        Der Zielcontainer ergibt sich aus der Endung von `output_path` und
        bestimmt, was überhaupt hineinpasst - siehe die Verzweigungen unten.

        `source_pixel_format` wird, wenn nicht übergeben, selbst ermittelt - aber
        nur für Encoder, die es überhaupt betrifft (siehe CHROMA_FALLBACK). Der
        Aufrufer gibt es mit, wenn er den Wert schon kennt oder protokollieren
        will, was umgerechnet wird.
        """
        is_mkv = output_path.suffix.lower() == ".mkv"

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", str(video.source_path),
            # Nur den primären Videostream - '0:v' würde eingebettete Cover-Bilder
            # (mjpeg) als weiteren "Videostream" mitnehmen.
            "-map", "0:v:0",
            # Alle Tonspuren; '?' verhindert einen Fehler bei Dateien ganz ohne Ton.
            "-map", "0:a?",
        ]

        if is_mkv:
            # MKV nimmt jede Untertitelart auf, auch Bitmap-Formate wie PGS und
            # VobSub, die bei MP4 übersprungen werden müssen. Deshalb hier alle
            # Spuren statt nur der textbasierten.
            cmd.extend(["-map", "0:s?"])
        else:
            for sub_index in (text_subtitle_indices or []):
                cmd.extend(["-map", f"0:s:{sub_index}?"])

        cmd.extend([
            "-c:v", codec,
            "-cq", str(cq),
            "-preset", preset,
        ])

        # 4:4:4- und 4:2:2-Quellen nimmt av1_nvenc nicht an. Nur in diesem Fall
        # wird die Chroma-Unterabtastung umgerechnet, die Bittiefe bleibt.
        if codec in _NEEDS_420:
            if source_pixel_format is None:
                source_pixel_format = self.pixel_format(video.source_path)
            ersatz = chroma_fallback(source_pixel_format, codec)
            if ersatz:
                cmd.extend(["-pix_fmt", ersatz])

        if codec == "hevc_nvenc" and not is_mkv:
            # Ohne diese Kennung schreibt ffmpeg 'hev1', und Apple-Geräte
            # spielen H.265 aus einer MP4 dann nicht ab - siehe HEVC_MP4_TAG.
            cmd.extend(["-tag:v", HEVC_MP4_TAG])

        if is_mkv:
            # Unverändert übernehmen: MKV braucht keine Umwandlung, damit bleiben
            # ASS-Positionierung und Bitmap-Untertitel erhalten. '?' schadet
            # nicht, wenn gar keine Untertitel da sind.
            cmd.extend(["-c:s", "copy"])
            # TrueHD und DTS-HD MA passen in MKV ohne Weiteres; FFmpeg stuft die
            # Kombination anders als bei MP4 nicht als experimentell ein.
        elif text_subtitle_indices:
            # MP4 kennt für Untertitel nur mov_text - dabei geht die
            # ASS-Positionierung verloren, Bitmap-Formate gar nicht erst mit.
            cmd.extend(["-c:s", "mov_text"])

        if normalize_audio:
            cmd.extend([
                "-af", "loudnorm=I=-23:LRA=7:TP=-2",
                "-c:a", "aac",
                "-b:a", "192k",
            ])
        else:
            cmd.extend(["-c:a", "copy"])

        if video.media_type in (MediaType.ANIME, MediaType.SERIEN):
            title = f"{video.series_name} S{video.season:02d}E{video.episode:02d}"
            cmd.extend([
                "-metadata", f"title={title}",
                "-metadata", f"show={video.series_name}",
                "-metadata", f"season_number={video.season}",
                "-metadata", f"episode_sort={video.episode}",
            ])
        elif video.media_type in (MediaType.FILME, MediaType.ANIME_FILME):
            cmd.extend(["-metadata", f"title={video.movie_name}"])

        cmd.append(str(output_path))
        return cmd
