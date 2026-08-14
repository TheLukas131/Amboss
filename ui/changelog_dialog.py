"""Zeigt die Versionsgeschichte im Programm selbst.

Die CHANGELOG.md liegt der Anwendung bei und wird hier gelesen statt
nachgebaut - so gibt es genau eine Quelle, und was auf der Projektseite steht,
steht auch im Programm.

Bewusst kein vollständiger Markdown-Darsteller: die Datei folgt einem festen
Aufbau (## Version, ### Rubrik, - Punkt), und den in lesbare Abschnitte zu
übersetzen ist ein Dutzend Zeilen. Eine Bibliothek dafür einzubinden wäre für
diesen einen Dialog nicht angemessen.
"""

import re

from PyQt5.QtCore import Qt
from qfluentwidgets import (
    BodyLabel, CaptionLabel, SingleDirectionScrollArea, StrongBodyLabel,
    SubtitleLabel, TitleLabel,
)
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from i18n import tr
from resources import resource_path
from ui.dialog_base import FittedMessageBox


def _read_changelog() -> str:
    for name in ("CHANGELOG.md", "changelog.md"):
        pfad = resource_path(name)
        try:
            if pfad.is_file():
                return pfad.read_text(encoding="utf-8")
        except OSError:
            continue
    return ""


class ChangelogDialog(FittedMessageBox):
    """Versionsgeschichte, gelesen aus der mitgelieferten CHANGELOG.md."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.widget.setMinimumSize(720, 620)
        self._build()

    def _build(self):
        self.viewLayout.addWidget(TitleLabel(tr("Änderungsverlauf")))

        text = _read_changelog()
        if not text:
            self.viewLayout.addWidget(BodyLabel(
                tr("Der Änderungsverlauf konnte nicht gelesen werden.")))
            self.yesButton.setText(tr("Schließen"))
            self.cancelButton.setVisible(False)
            return

        bereich = SingleDirectionScrollArea(orient=Qt.Vertical)
        bereich.setWidgetResizable(True)
        bereich.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        inhalt = QWidget()
        inhalt.setStyleSheet("QWidget { background: transparent; }")
        layout = QVBoxLayout(inhalt)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(6)

        self._render(text, layout)
        layout.addStretch()

        bereich.setWidget(inhalt)
        self.viewLayout.addWidget(bereich, 1)

        self.yesButton.setText(tr("Schließen"))
        self.cancelButton.setVisible(False)

    @staticmethod
    def _render(text: str, layout: QVBoxLayout):
        """Übersetzt die Markdown-Struktur in Beschriftungen.

        Die Kopfzeilen der Datei (Titel, Hinweis auf das Format) werden
        übersprungen - im Dialog interessiert nur, was sich geändert hat."""
        begonnen = False
        for zeile in text.splitlines():
            zeile = zeile.rstrip()

            if zeile.startswith("## "):
                begonnen = True
                # "## [1.1.0] — 2026-08-12" -> "1.1.0 — 2026-08-12"
                überschrift = zeile[3:].replace("[", "").replace("]", "")
                if layout.count():
                    abstand = QWidget()
                    abstand.setFixedHeight(14)
                    layout.addWidget(abstand)
                layout.addWidget(SubtitleLabel(überschrift))
                continue

            if not begonnen:
                continue

            if zeile.startswith("### "):
                layout.addWidget(StrongBodyLabel(zeile[4:]))
            elif zeile.startswith("- "):
                punkt = BodyLabel("•  " + _entferne_auszeichnung(zeile[2:]))
                punkt.setWordWrap(True)
                layout.addWidget(punkt)
            elif zeile.startswith("  ") and zeile.strip():
                # Fortsetzungszeile eines Punktes - an den vorherigen anhängen
                vorheriger = layout.itemAt(layout.count() - 1)
                widget = vorheriger.widget() if vorheriger else None
                if isinstance(widget, BodyLabel):
                    widget.setText(widget.text() + " " + _entferne_auszeichnung(zeile.strip()))
            elif zeile.strip():
                absatz = CaptionLabel(_entferne_auszeichnung(zeile.strip()))
                absatz.setWordWrap(True)
                layout.addWidget(absatz)


def _entferne_auszeichnung(text: str) -> str:
    """Nimmt Markdown-Auszeichnungen heraus, die als Zeichen stören würden."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)   # Fettung
    text = re.sub(r"`(.+?)`", r"\1", text)          # Code
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", text)  # Verweise
    return text
