"""Das Ende eines Laufs als Meldung mitten im Fenster.

Die Zeile oben auf der Seite (ui/result_banner.py) hält fest, was erledigt
wurde. Wer aber nach Stunden zum Rechner zurückkommt, soll nicht erst eine
Zeile finden müssen: die Meldung steht deshalb zusätzlich als Dialog vor dem
Fenster und bleibt dort, bis man sie bestätigt. Die Zeile bleibt danach als
Nachweis stehen.

Gezeigt wird sie erst, wenn wirklich alles durch ist - nach dem Verschieben,
wenn eines eingestellt war, nicht schon nach der Konvertierung davor.
"""

from typing import List

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CaptionLabel, IconWidget, InfoBarIcon, StrongBodyLabel, TitleLabel

from i18n import tr
from ui.dialog_base import FittedMessageBox
from ui.result_banner import Entry


class ResultDialog(FittedMessageBox):
    """Nennt, was fertig wurde - je Vorgang eine Zeile mit Uhrzeit."""

    def __init__(self, entries: List[Entry], parent=None):
        super().__init__(parent)
        self.widget.setMinimumWidth(520)

        mit_fehlern = any(entry.warning for entry in entries)
        self.viewLayout.addWidget(TitleLabel(
            tr("Fertig - mit Hinweisen") if mit_fehlern else tr("Fertig")))

        for entry in entries:
            zeile = QWidget()
            layout = QHBoxLayout(zeile)
            layout.setContentsMargins(0, 6, 0, 0)
            layout.setSpacing(12)
            icon = IconWidget(InfoBarIcon.WARNING if entry.warning else InfoBarIcon.SUCCESS)
            icon.setFixedSize(20, 20)
            layout.addWidget(icon, 0, Qt.AlignTop)

            text = QVBoxLayout()
            text.setSpacing(2)
            text.addWidget(StrongBodyLabel(entry.title))
            if entry.message:
                meldung = BodyLabel(entry.message)
                meldung.setWordWrap(True)
                # Als Text, nicht als HTML: in der Meldung können Dateinamen stehen.
                meldung.setTextFormat(Qt.PlainText)
                text.addWidget(meldung)
            text.addWidget(CaptionLabel(entry.time))
            layout.addLayout(text, 1)
            self.viewLayout.addWidget(zeile)

        self.yesButton.setText(tr("OK"))
        self.cancelButton.setVisible(False)
