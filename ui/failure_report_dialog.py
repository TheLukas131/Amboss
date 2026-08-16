"""Bericht über die Dateien, die ein Lauf nicht konvertieren konnte.

Der bisherige Hinweis nannte nur die Dateinamen und verwies aufs Protokoll -
dort muss man dann zwischen hunderten Zeilen suchen, warum ausgerechnet Folge 22
gescheitert ist. Hier steht je Datei der Grund und wo sie jetzt liegt, damit man
sie ohne Umweg findet.
"""

from typing import List

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel, CaptionLabel, SingleDirectionScrollArea, StrongBodyLabel, TitleLabel,
)

from i18n import tr
from models import VideoFile
from ui.dialog_base import FittedMessageBox


class FailureReportDialog(FittedMessageBox):
    """Zeigt je gescheiterter Datei den Grund und den aktuellen Ablageort."""

    def __init__(self, failed: List[VideoFile], succeeded: int, parent=None):
        super().__init__(parent)
        self.widget.setMinimumSize(760, 560)
        self._build(failed, succeeded)

    def _build(self, failed: List[VideoFile], succeeded: int):
        self.viewLayout.addWidget(TitleLabel(tr("Nicht konvertierte Dateien")))

        einleitung = BodyLabel(tr(
            "{failed} von {total} Dateien konnten nicht konvertiert werden. "
            "Die übrigen {done} sind fertig und wurden weiterverarbeitet.\n\n"
            "Die betroffenen Quelldateien wurden zur Seite gelegt - die übrigen "
            "sind gelöscht, sofern das eingestellt war. Ein erneuter Scan findet "
            "damit nur noch die hier aufgeführten."
        ).format(failed=len(failed), total=len(failed) + succeeded, done=succeeded))
        einleitung.setWordWrap(True)
        self.viewLayout.addWidget(einleitung)

        bereich = SingleDirectionScrollArea(orient=Qt.Vertical)
        bereich.setWidgetResizable(True)
        bereich.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        inhalt = QWidget()
        inhalt.setStyleSheet("QWidget { background: transparent; }")
        layout = QVBoxLayout(inhalt)
        layout.setContentsMargins(0, 4, 12, 0)
        layout.setSpacing(4)

        for video in failed:
            if layout.count():
                abstand = QWidget()
                abstand.setFixedHeight(10)
                layout.addWidget(abstand)

            name = StrongBodyLabel(video.source_path.name)
            name.setWordWrap(True)
            layout.addWidget(name)

            grund = BodyLabel(video.error_message or tr("Unbekannter Fehler"))
            grund.setWordWrap(True)
            layout.addWidget(grund)

            ort = CaptionLabel(tr("Liegt jetzt: {path}").format(path=video.source_path.parent))
            ort.setWordWrap(True)
            layout.addWidget(ort)

        layout.addStretch()
        bereich.setWidget(inhalt)
        self.viewLayout.addWidget(bereich, 1)

        self.yesButton.setText(tr("Schließen"))
        self.cancelButton.setVisible(False)
