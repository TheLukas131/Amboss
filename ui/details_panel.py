"""Einzelheiten zu einer Datei, direkt unter der Warteschlange.

Vorher lagen sie auf einer eigenen Seite: dieselbe Liste noch einmal, dort
aufzuklappen. Wer wissen wollte, was aus einer Datei geworden ist, musste die
Seite wechseln und die Datei in der zweiten Liste wiederfinden. Jetzt genügt
ein Klick auf die Zeile.
"""

from typing import List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QVBoxLayout
from qfluentwidgets import (
    BodyLabel, CaptionLabel, FluentIcon, StrongBodyLabel, TransparentToolButton,
)

from i18n import tr
from models import VideoFile, VideoMetadata
from queue_model import format_duration, format_size, size_change
from ui import theme


def _joined(parts: List[str]) -> str:
    return " · ".join(p for p in parts if p) or "-"


def video_line(meta: Optional[VideoMetadata]) -> str:
    if meta is None:
        return "-"
    tiefe = f"{meta.bit_depth} bit" if meta.bit_depth else ""
    hdr = "HDR" if meta.is_hdr() else ""
    return _joined([meta.video_codec, meta.resolution, " ".join(p for p in (tiefe, hdr) if p),
                    meta.video_bitrate])


def audio_line(meta: Optional[VideoMetadata]) -> str:
    if meta is None:
        return "-"
    codecs = ", ".join(c for c in meta.audio_codecs if c) or meta.audio_codec
    return _joined([codecs, meta.audio_bitrate])


def subtitle_line(meta: Optional[VideoMetadata]) -> str:
    if meta is None:
        return "-"
    return ", ".join(c for c in meta.subtitle_codecs if c) or "-"


def tag_line(meta: Optional[VideoMetadata]) -> str:
    if meta is None:
        return "-"
    folge = ""
    if meta.season or meta.episode:
        folge = f"S{meta.season or '?'} E{meta.episode or '?'}"
    return _joined([meta.title, meta.show_name, folge])


class DetailsPanel(QFrame):
    """Vorher/Nachher einer Datei. Unsichtbar, solange keine gewählt ist."""

    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.video: Optional[VideoFile] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 6, 4, 0)
        outer.setSpacing(6)

        kopf = QHBoxLayout()
        kopf.setSpacing(12)
        self.title = StrongBodyLabel("")
        kopf.addWidget(self.title)
        self.note = CaptionLabel("")
        kopf.addWidget(self.note, 1)
        close_btn = TransparentToolButton(FluentIcon.CLOSE)
        close_btn.setFixedSize(26, 26)
        close_btn.setToolTip(tr("Einzelheiten schließen"))
        close_btn.clicked.connect(self.clear)
        kopf.addWidget(close_btn)
        outer.addLayout(kopf)

        # Zwei Blöcke nebeneinander statt sechs Zeilen untereinander: die
        # Einzelheiten sollen der Warteschlange darüber möglichst wenig Höhe
        # nehmen.
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(2)
        self._cells = {}
        bloecke = (
            (("video", "Video"), ("audio", "Audio"), ("subtitle", tr("Untertitel"))),
            (("duration", tr("Dauer")), ("size", tr("Größe")), ("tags", tr("Metadaten"))),
        )
        for block, zeilen in enumerate(bloecke):
            spalte = block * 3
            grid.setColumnStretch(spalte + 1, 3 if block == 0 else 2)
            grid.setColumnStretch(spalte + 2, 3 if block == 0 else 2)
            grid.addWidget(CaptionLabel(tr("Vorher")), 0, spalte + 1)
            grid.addWidget(CaptionLabel(tr("Nachher")), 0, spalte + 2)
            for zeile, (key, label) in enumerate(zeilen, start=1):
                grid.addWidget(CaptionLabel(label), zeile, spalte)
                vorher, nachher = BodyLabel("-"), BodyLabel("-")
                for zelle in (vorher, nachher):
                    zelle.setTextInteractionFlags(Qt.TextSelectableByMouse)
                grid.addWidget(vorher, zeile, spalte + 1)
                grid.addWidget(nachher, zeile, spalte + 2)
                self._cells[key] = (vorher, nachher)
        outer.addLayout(grid)

        self.error = CaptionLabel("")
        self.error.setWordWrap(True)
        # Als Text, nicht als HTML: die Meldung stammt aus der Ausgabe von
        # FFmpeg und kann spitze Klammern enthalten.
        self.error.setTextFormat(Qt.PlainText)
        self.error.setTextInteractionFlags(Qt.TextSelectableByMouse)
        hell, dunkel = theme.semantic_pair("error")
        self.error.setTextColor(QColor(hell), QColor(dunkel))
        self.error.setVisible(False)
        outer.addWidget(self.error)

        self.setVisible(False)

    def clear(self):
        # Am gemerkten Video festgemacht, nicht an isVisible(): das ist auch
        # dann False, wenn bloss das Fenster darüber (noch) nicht angezeigt wird.
        war_offen = self.video is not None
        self.video = None
        self.setVisible(False)
        if war_offen:
            self.closed.emit()

    def show_video(self, video: VideoFile, target_meta: Optional[VideoMetadata]):
        self.video = video
        source = video.source_metadata
        self.title.setText(video.source_path.name)

        def setze(key, vorher, nachher):
            self._cells[key][0].setText(vorher)
            self._cells[key][1].setText(nachher)

        setze("video", video_line(source), video_line(target_meta))
        setze("audio", audio_line(source), audio_line(target_meta))
        setze("subtitle", subtitle_line(source), subtitle_line(target_meta))
        setze("duration", (source.duration if source else "") or "-",
              (target_meta.duration if target_meta else "") or "-")
        setze("size", format_size(video.original_size),
              size_change(video.original_size, video.new_size).split(" → ", 1)[-1]
              if video.new_size > 0 else "-")
        setze("tags", tag_line(source), tag_line(target_meta))

        text = ""
        if video.new_size > 0 and video.conversion_start_time and video.conversion_end_time:
            dauer = video.conversion_end_time - video.conversion_start_time
            text = tr("Konvertiert in {time}").format(time=format_duration(dauer))
        self.error.setText(tr("Fehler: {reason}").format(reason=video.error_message)
                           if video.error_message else "")
        self.error.setVisible(bool(video.error_message))
        self.note.setText(text)
        self.setVisible(True)
