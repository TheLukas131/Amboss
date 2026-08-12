"""Bestätigungsdialog für erkannte Medientypen, kurz bevor die Konvertierung
startet - nur wenn "Nach Abschluss automatisch auf NAS verschieben" aktiv ist.

Die Anime/Serie/Film-Erkennung läuft rein über den Dateinamen (siehe
pattern_matcher.py) und kann daneben liegen, z.B. ein Anime-Film ohne eines der
bekannten Schlüsselwörter im Namen wird als normaler Film erkannt. Ohne diesen
Dialog würde so eine Fehlklassifizierung erst auffallen, wenn die Datei beim
automatischen Upload lautlos im falschen Zielordner landet.

Erbt von MessageBoxBase statt einem nackten QDialog - nur so bekommt der Dialog
den zum aktuellen Theme passenden Hintergrund (siehe auch merge_review_dialog.py
und shutdown_countdown_dialog.py, gleicher Grund)."""

from typing import Dict, List, Tuple

from PyQt5.QtGui import QFontMetrics
from PyQt5.QtWidgets import QAbstractItemView, QHeaderView, QTableWidgetItem
from qfluentwidgets import BodyLabel, ComboBox, TableWidget, TitleLabel

from models import NAS_CATEGORIES, MediaType, VideoFile
from i18n import tr
from ui.dialog_base import FittedMessageBox


def group_videos_by_title(videos: List[VideoFile]) -> Dict[Tuple[str, MediaType], List[VideoFile]]:
    """Fasst Dateien zu je einem Eintrag pro Titel zusammen - 12 Folgen derselben
    Staffel sind eine Entscheidung, nicht zwölf.

    Der Schlüssel enthält bewusst auch den Medientyp: gleichnamige Einträge mit
    unterschiedlich erkanntem Typ (etwa ein Film und eine Serie desselben Namens)
    dürfen nicht stillschweigend zusammenfallen. Die Einfügereihenfolge bleibt
    erhalten, damit die Liste der Scan-Reihenfolge folgt."""
    groups: Dict[Tuple[str, MediaType], List[VideoFile]] = {}
    for video in videos:
        title = video.series_name or video.movie_name or video.source_path.stem
        groups.setdefault((title, video.media_type), []).append(video)
    return groups


class MediaTypeReviewDialog(FittedMessageBox):
    """Zeigt pro Titel (nicht pro Datei) die erkannte Kategorie in einer
    editierbaren Tabelle. Bei Bestätigung wird die gewählte Kategorie auf alle
    Dateien des jeweiligen Titels übertragen - PathGenerator muss die Zielpfade
    danach neu berechnen."""

    def __init__(self, videos: List[VideoFile], parent=None):
        super().__init__(parent)
        self.videos = videos
        self._groups = group_videos_by_title(videos)
        self._combos: List[ComboBox] = []
        self.widget.setMinimumSize(680, 480)
        self._build_ui()

    def _build_ui(self):
        self.viewLayout.addWidget(TitleLabel(tr("Automatisches Einsortieren ist aktiv")))
        info = BodyLabel(
            tr("Nach der Konvertierung werden diese Dateien in die Mediathek verschoben - "
               "die Kategorie bestimmt den Zielordner. Bitte kurz prüfen, ob alles stimmt "
               "(z.B. Anime-Filme werden manchmal als normale Filme erkannt).\n"
               "Die Auswahl gilt jeweils für alle Folgen des Titels.")
        )
        info.setWordWrap(True)
        self.viewLayout.addWidget(info)

        table = TableWidget()
        table.setBorderVisible(True)
        table.setBorderRadius(8)
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels([tr("Titel"), tr("Dateien"), tr("Kategorie")])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.verticalHeader().setDefaultSectionSize(36)
        table.verticalHeader().setVisible(False)
        table.setRowCount(len(self._groups))

        for row, ((title, media_type), group) in enumerate(self._groups.items()):
            table.setItem(row, 0, QTableWidgetItem(title))
            count = len(group)
            table.setItem(row, 1, QTableWidgetItem(
                tr("1 Datei") if count == 1 else tr("{count} Dateien").format(count=count)))

            combo = ComboBox()
            for _c in NAS_CATEGORIES:
                combo.addItem(tr(_c), userData=_c)
            idx = combo.findData(media_type.value)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            table.setCellWidget(row, 2, combo)
            self._combos.append(combo)

        table.resizeColumnToContents(1)
        # Die Kategorie-Spalte an den längsten Eintrag anpassen. resizeColumnToContents
        # hilft hier nicht: Qt bemisst dabei nur die Zellen-Einträge, nicht die per
        # setCellWidget eingesetzten Auswahlfelder - die Spalte bliebe zu schmal und
        # "Animated movies" stünde abgeschnitten da.
        metrics = QFontMetrics(table.font())
        widest = max((metrics.width(tr(name)) for name in NAS_CATEGORIES), default=0)
        table.setColumnWidth(2, widest + 68)  # Aufklapp-Pfeil, Innenabstand, Rahmen
        self.viewLayout.addWidget(table, 1)

        self.yesButton.setText(tr("Bestätigen und starten"))
        self.cancelButton.setText(tr("Abbrechen"))

    def validate(self) -> bool:
        """Wird von MessageBoxBase vor dem eigentlichen accept() aufgerufen -
        genau der richtige Zeitpunkt, um die Korrekturen zu übernehmen."""
        for group, combo in zip(self._groups.values(), self._combos):
            media_type = MediaType(combo.currentData())
            for video in group:
                video.media_type = media_type
        return True
