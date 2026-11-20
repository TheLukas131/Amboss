"""Was erledigt wurde - als Zeile im Fenster, die stehen bleibt.

Vorher sagte Amboss das Ende eines Laufs nur auf zwei flüchtigen Wegen: über
die Windows-Benachrichtigung und über eine Einblendung im Fenster, die nach
vier Sekunden wieder verschwand. Ein Lauf endet typischerweise, während niemand
hinsieht - wer danach zum Rechner kam und die Benachrichtigung nicht mehr
vorfand, hatte nur noch das Protokoll.

Die Meldung bleibt deshalb stehen, bis man sie schliesst oder einen neuen Lauf
startet, und sie nennt die Uhrzeit: "fertig" ist erst dann eine Auskunft, wenn
man weiss, seit wann.
"""

from datetime import datetime
from typing import List, NamedTuple

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    CaptionLabel, CardWidget, FluentIcon, IconWidget, InfoBarIcon, StrongBodyLabel,
    TransparentToolButton,
)

from i18n import tr

# Mehr als das passt nicht sinnvoll in eine Meldung: ein Lauf erzeugt höchstens
# zwei (Konvertierung, Verschieben), und ältere gehören ins Protokoll.
MAX_ENTRIES = 3


class Entry(NamedTuple):
    time: str
    title: str
    message: str
    warning: bool


def make_entry(title: str, message: str, warning: bool = False) -> Entry:
    return Entry(datetime.now().strftime("%H:%M"), title, " ".join(message.split()), warning)


class ResultBanner(CardWidget):
    """Zeigt die letzten Ergebnisse. Unsichtbar, solange es keine gibt."""

    dismissed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(16, 10, 10, 10)
        outer.setSpacing(8)
        self._rows = QVBoxLayout()
        self._rows.setSpacing(6)
        outer.addLayout(self._rows, 1)
        close_btn = TransparentToolButton(FluentIcon.CLOSE)
        close_btn.setFixedSize(26, 26)
        close_btn.setToolTip(tr("Meldung schließen"))
        close_btn.clicked.connect(self.dismissed.emit)
        outer.addWidget(close_btn, 0, Qt.AlignTop)
        self._entries: List[Entry] = []
        self.setVisible(False)

    def entries(self) -> List[Entry]:
        return list(self._entries)

    def set_entries(self, entries: List[Entry]):
        self._entries = list(entries)
        while self._rows.count():
            item = self._rows.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for entry in self._entries:
            self._rows.addWidget(self._row(entry))
        self.setVisible(bool(self._entries))

    @staticmethod
    def _row(entry: Entry) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        icon = IconWidget(InfoBarIcon.WARNING if entry.warning else InfoBarIcon.SUCCESS)
        icon.setFixedSize(16, 16)
        layout.addWidget(icon, 0, Qt.AlignTop)
        title = StrongBodyLabel(entry.title)
        layout.addWidget(title, 0, Qt.AlignTop)
        text = CaptionLabel(f"{entry.time} · {entry.message}" if entry.message else entry.time)
        text.setWordWrap(True)
        # Als Text, nicht als HTML: in der Meldung stehen Dateinamen.
        text.setTextFormat(Qt.PlainText)
        layout.addWidget(text, 1)
        return row
