"""Meldung, wenn es eine neuere Fassung von Amboss gibt.

Der Dialog laedt nichts herunter. Er nennt die neue Versionsnummer, zeigt was
sich geaendert hat und oeffnet auf Wunsch die Projektseite im Browser - von
dort holt sich der Nutzer die Datei selbst, wann und wohin er moechte.

Gezeigt wird nicht nur die neueste Fassung, sondern jede seit der laufenden:
wer von 1.2.3 auf 1.4.0 springt, hat 1.2.4 und 1.3.0 nie gesehen, und die
Frage "lohnt sich der Wechsel" beantwortet sich erst aus allem zusammen. Bei
mehreren Eintraegen wird die Liste scrollbar; der Knopf fuehrt immer zur
neuesten Fassung.

Die Pruefung selbst laeuft in einem eigenen Thread. Beim Start haengt sonst
das Fenster an einer Netzwerkanfrage, und ausgerechnet auf einem Rechner ohne
Internet waere die Wartezeit am laengsten.
"""

import re

from PyQt5.QtCore import Qt, QThread, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel, CaptionLabel, CheckBox, SingleDirectionScrollArea,
    StrongBodyLabel, SubtitleLabel, TitleLabel,
)

import update_check
from i18n import tr
from ui.dialog_base import FittedMessageBox

# Je Fassung nicht mehr als so viele Zeilen. Die Veroeffentlichungsnotizen sind
# kurz gehalten, aber ein Ausreisser soll den Dialog nicht sprengen.
_MAX_ZEILEN_JE_VERSION = 20


class UpdateCheckThread(QThread):
    """Fragt im Hintergrund nach neueren Fassungen.

    Meldet sich nur, wenn es etwas zu melden gibt - kein Netz, kein Server,
    keine neue Version laufen allesamt still aus. `finished_check` kommt
    dagegen immer und traegt das Ergebnis (oder None), damit die manuelle
    Suche auch "alles aktuell" anzeigen kann."""

    found = pyqtSignal(object)           # update_check.UpdateInfo
    finished_check = pyqtSignal(object)  # update_check.UpdateInfo oder None

    def __init__(self, current_version: str, skipped_version: str = "", parent=None):
        super().__init__(parent)
        self._current = current_version
        self._skipped = skipped_version

    def run(self):
        info = update_check.find_update(self._current, self._skipped)
        if info is not None:
            self.found.emit(info)
        self.finished_check.emit(info)


def open_releases_page(release=None) -> bool:
    """Oeffnet die Seite der neuesten Fassung im Standardbrowser."""
    url = getattr(release, "page_url", "") or update_check.RELEASES_PAGE
    return bool(QDesktopServices.openUrl(QUrl(url)))


def _ohne_auszeichnung(zeile: str) -> str:
    """Nimmt die Markdown-Zeichen heraus, die als Text nur stoeren wuerden."""
    zeile = re.sub(r"\*\*(.+?)\*\*", r"\1", zeile)          # Fettung
    zeile = re.sub(r"`(.+?)`", r"\1", zeile)                # Code
    zeile = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", zeile)     # Verweise
    return zeile


def _notizen_zeilen(notes: str):
    """Zerlegt die Veroeffentlichungsnotizen in (Art, Text)-Paare.

    Art ist "rubrik" fuer eine Ueberschrift und "punkt" fuer alles andere -
    mehr Struktur haben die Notizen nicht, und mehr braucht die Anzeige auch
    nicht.

    Eine Rubrik ist entweder eine Markdown-Ueberschrift oder eine Zeile, die
    ausschliesslich aus fettem Text besteht: GitHub-Veroeffentlichungen
    schreiben ihre Abschnitte meist als **Fixed** statt als ### Fixed, und
    ohne diesen Fall stuende die Gliederung als gewoehnlicher Text zwischen den
    Punkten.

    Zeilen, die nur ein Verweis sind ("[Full changelog](...)"), fallen weg -
    im Dialog waere davon bloss ein Wort ohne Ziel uebrig, und der Weg zur
    Projektseite steht ohnehin auf dem Knopf darunter."""
    zeilen = []
    for zeile in notes.splitlines():
        zeile = zeile.strip()
        if not zeile or re.fullmatch(r"\[.+?\]\(.+?\)[.:]?", zeile):
            continue

        rubrik = re.fullmatch(r"\*\*(.+?)\*\*:?", zeile)
        if rubrik:
            zeilen.append(("rubrik", rubrik.group(1).strip().rstrip(":").strip()))
        elif zeile.startswith("#"):
            zeilen.append(("rubrik", _ohne_auszeichnung(zeile.lstrip("#").strip())))
        elif zeile.startswith(("- ", "* ")):
            zeilen.append(("punkt", "•  " + _ohne_auszeichnung(zeile[2:].strip())))
        else:
            zeilen.append(("punkt", _ohne_auszeichnung(zeile)))

        if len(zeilen) >= _MAX_ZEILEN_JE_VERSION:
            zeilen.append(("punkt", tr("... weiteres auf der Projektseite")))
            break
    return zeilen


class UpdateDialog(FittedMessageBox):
    """Nennt die neuen Fassungen und fuehrt zur Projektseite - mehr nicht."""

    def __init__(self, info, current_version: str, parent=None):
        super().__init__(parent)
        self.info = info
        self.widget.setMinimumWidth(600)
        self._build(info, current_version)

    def _build(self, info, current_version: str):
        self.viewLayout.addWidget(TitleLabel(tr("Neue Version verfügbar")))

        anzahl = len(info.releases)
        if anzahl > 1:
            text = tr("Amboss {new} ist erschienen, installiert ist {current}. "
                      "Dazwischen liegen {count} Fassungen:")
            text = text.format(new=info.version, current=current_version, count=anzahl)
        else:
            text = tr("Amboss {new} ist erschienen. Installiert ist {current}.")
            text = text.format(new=info.version, current=current_version)
        kopf = BodyLabel(text)
        kopf.setWordWrap(True)
        self.viewLayout.addWidget(kopf)

        self._build_notizen(info)

        hinweis = CaptionLabel(tr(
            "Amboss lädt nichts von selbst herunter. Der Knopf öffnet die "
            "Projektseite im Browser; dort liegt die neueste Fassung zum "
            "Herunterladen."
        ))
        hinweis.setWordWrap(True)
        self.viewLayout.addWidget(hinweis)

        self.skip_check = CheckBox(
            tr("Nicht mehr an {version} erinnern").format(version=info.version))
        self.viewLayout.addWidget(self.skip_check)

        self.yesButton.setText(tr("Zur Download-Seite"))
        self.cancelButton.setText(tr("Später"))

    def _build_notizen(self, info):
        """Die Aenderungen je Fassung, neueste zuerst, in einer Scrollflaeche."""
        abschnitte = [(release, _notizen_zeilen(release.notes))
                      for release in info.releases]
        if not any(zeilen for _release, zeilen in abschnitte):
            return

        bereich = SingleDirectionScrollArea(orient=Qt.Vertical)
        bereich.setWidgetResizable(True)
        bereich.setMaximumHeight(300)
        bereich.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        inhalt = QWidget()
        inhalt.setStyleSheet("QWidget { background: transparent; }")
        layout = QVBoxLayout(inhalt)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(4)

        for release, zeilen in abschnitte:
            if layout.count():
                abstand = QWidget()
                abstand.setFixedHeight(12)
                layout.addWidget(abstand)
            layout.addWidget(SubtitleLabel(release.version))
            if not zeilen:
                # Eine Veroeffentlichung ohne Notizen gibt es; sie kommentarlos
                # wegzulassen waere schlechter, als sie leer zu zeigen - sonst
                # fehlt in der Liste eine Versionsnummer ohne Erklaerung.
                fehlt = CaptionLabel(tr("Keine Angaben zu dieser Fassung."))
                fehlt.setWordWrap(True)
                layout.addWidget(fehlt)
                continue
            for art, text in zeilen:
                label = StrongBodyLabel(text) if art == "rubrik" else BodyLabel(text)
                label.setWordWrap(True)
                layout.addWidget(label)

        layout.addStretch()
        bereich.setWidget(inhalt)
        self.viewLayout.addWidget(bereich, 1)

    def skip_requested(self) -> bool:
        return self.skip_check.isChecked()
