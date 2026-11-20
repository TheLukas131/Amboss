"""Die Tabelle der Warteschlange.

Zeichnet, was queue_model.py vorgibt: Staffeln als aufklappbare Zeilen, darunter
ihre Folgen, dazwischen alles, was allein steht.

Wichtig für alle, die von aussen zugreifen: eine Tabellenzeile ist **nicht**
mehr der Index der Datei in der Warteschlange. Früher stand Datei 7 in Zeile 7;
mit Staffel-Zeilen dazwischen stimmt das nicht mehr. Angesprochen wird eine
Datei deshalb über refresh_video(index), nie über eine Zeilennummer.
"""

from pathlib import Path
from typing import Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QFontMetrics
from PyQt5.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QTableWidgetItem, QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel, CaptionLabel, FluentIcon, ProgressBar, TableWidget,
    TransparentToolButton,
)
from qfluentwidgets.common.font import getFont

from i18n import tr
from models import FileStatus, VideoFile
from queue_model import (
    COLLAPSE_ABOVE, Group, Row, build_rows, format_duration,
    matches_filter, relative_target, remaining_seconds, size_change, summarize,
)
from ui import theme

COL_NAME, COL_PROGRESS, COL_SIZE, COL_REMOVE = range(4)

_STATUS_COLOR = {
    FileStatus.WARTEND: "neutral", FileStatus.VERARBEITET: "accent",
    FileStatus.FERTIG: "success", FileStatus.FEHLER: "error",
    FileStatus.UEBERSPRUNGEN: "neutral", FileStatus.PAUSIERT: "warning",
}


class _ProgressCell(QWidget):
    """Zustand einer Zeile in einer einzigen Zelle.

    Läuft die Datei, steht hier ein Balken mit Prozent und Restzeit. Läuft sie
    nicht, steht das Wort: Wartend, Fertig, Fehler. Vorher waren das zwei
    Spalten nebeneinander - das Wort "Verarbeitet" neben einem Balken, der
    dasselbe sagt, und ein leerer Balken neben dem Wort "Wartend"."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(3)
        layout.addStretch()
        self.status = BodyLabel("")
        self.status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status)
        self.bar = ProgressBar()
        self.bar.setVisible(False)
        layout.addWidget(self.bar)
        self.caption = CaptionLabel("")
        self.caption.setAlignment(Qt.AlignCenter)
        self.caption.setVisible(False)
        layout.addWidget(self.caption)
        layout.addStretch()
        self._farbe = None

    def text(self) -> str:
        """Was die Zelle gerade sagt - das Wort oder die Zeile unter dem Balken."""
        return self.caption.text() if self.bar.isVisibleTo(self) else self.status.text()

    def show_status(self, text: str, farbe: str):
        self.bar.setVisible(False)
        self.caption.setVisible(False)
        self.status.setVisible(True)
        if self.status.text() != text:
            self.status.setText(text)
        if self._farbe != farbe:
            self._farbe = farbe
            hell, dunkel = theme.semantic_pair(farbe)
            self.status.setTextColor(QColor(hell), QColor(dunkel))

    def show_progress(self, value: int, caption: str):
        self.status.setVisible(False)
        self.bar.setVisible(True)
        self.caption.setVisible(True)
        if self.bar.value() != value:
            self.bar.setValue(value)
        if self.caption.text() != caption:
            self.caption.setText(caption)


class _RemoveCell(QWidget):
    """Hält den Entfernen-Knopf einer Zeile.

    Der Knopf steckt in einem eigenen Behälter, weil er nur erscheinen soll,
    wenn die Maus über der Zeile steht: eine Zelle zeigt die Tabelle bei jedem
    Verschieben von selbst wieder an, ihren Inhalt nicht."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.button = TransparentToolButton(FluentIcon.CLOSE)
        self.button.setToolTip(tr("Aus der Warteschlange entfernen"))
        self.button.setFixedSize(28, 28)
        self.button.setVisible(False)
        layout.addWidget(self.button, 0, Qt.AlignCenter)


class QueueTable(TableWidget):
    """Warteschlange mit Staffel-Zeilen und Live-Zahlen.

    Drei Spalten und ein Knopf: Datei, Zustand, Grösse. Typ und Ziel stehen
    nicht mehr in jeder Zeile - der Typ ergibt sich bei Serien aus der
    Staffel-Zeile, das Ziel einer Folge war fast derselbe Text wie ihr Name.
    Beides zeigen die Einzelheiten, die ein Klick auf die Zeile öffnet."""

    remove_requested = pyqtSignal(object)   # VideoFile
    video_selected = pyqtSignal(object)     # VideoFile

    def __init__(self, parent=None):
        super().__init__(parent)
        self._videos: List[VideoFile] = []
        self._output_base: Optional[Path] = None
        self._rows: List[Row] = []
        self._row_of_index: Dict[int, int] = {}
        self._row_of_group: Dict[tuple, int] = {}
        self._collapsed: set = set()
        self._known_groups: set = set()
        self._filter = "all"
        self._removal_enabled = True
        self._hover_row: Optional[int] = None

        self.setBorderVisible(True)
        self.setBorderRadius(8)
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels([tr("Dateiname"), tr("Fortschritt"), tr("Größe"), ""])
        header = self.horizontalHeader()
        header.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        for spalte in (COL_PROGRESS, COL_SIZE, COL_REMOVE):
            header.setSectionResizeMode(spalte, QHeaderView.Fixed)
        # So breit wie der längste Eintrag in der gewählten Sprache - eine
        # feste Zahl passte für die eine Sprache und schnitt in der anderen
        # mitten im Wort ab.
        masse = QFontMetrics(getFont(13))

        def breite_fuer(texte, mindestens):
            return max(mindestens, max(masse.horizontalAdvance(t) for t in texte) + 30)

        self.setColumnWidth(COL_PROGRESS, breite_fuer(
            [tr(s.value) for s in FileStatus]
            + ["88 % · " + tr("noch {time}").format(time="8:88:88"),
               "88 % · " + tr("{count} laufen").format(count=8),
               tr("{done}/{total} fertig").format(done=888, total=888)], 200))
        self.setColumnWidth(COL_SIZE, breite_fuer(["888.8 GB → 888.8 GB (−88 %)"], 180))
        self.setColumnWidth(COL_REMOVE, 44)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideMiddle)
        self.verticalHeader().setDefaultSectionSize(44)
        self.verticalHeader().setVisible(False)
        self.setMinimumHeight(200)

        self.setMouseTracking(True)
        self.cellEntered.connect(self._set_hover_row)
        self.cellClicked.connect(self._on_cell_clicked)

    # =========================================================================
    # Von aussen
    # =========================================================================

    def set_videos(self, videos: List[VideoFile], output_base: Optional[Path]):
        """Baut die Tabelle neu auf. Für Änderungen an der Liste selbst -
        einzelne Dateien frischt refresh_video auf."""
        self._videos = videos
        self._output_base = output_base
        self._rows = build_rows(videos)

        vorhanden = {row.group.key for row in self._rows if row.is_group}
        for key in vorhanden - self._known_groups:
            if len(videos) > COLLAPSE_ABOVE:
                self._collapsed.add(key)
        self._known_groups = vorhanden
        self._collapsed &= vorhanden

        self._row_of_index = {}
        self._row_of_group = {}
        self._hover_row = None
        self.clearSelection()
        self.setRowCount(len(self._rows))
        for r, row in enumerate(self._rows):
            if row.is_group:
                self._row_of_group[row.group.key] = r
                self._build_group_row(r, row.group)
            else:
                self._row_of_index[row.index] = r
                self._build_file_row(r, row)
        self._apply_visibility()

    def refresh_video(self, index: int):
        """Zeichnet eine Datei nach - Zustand, Fortschritt, Größe - und die
        Staffel, zu der sie gehört."""
        r = self._row_of_index.get(index)
        if r is None or not (0 <= index < len(self._videos)):
            return
        self._update_file_row(r, self._videos[index])
        parent = self._rows[r].parent
        if parent is not None:
            self._update_group_row(self._row_of_group[parent.key], parent)
        if self._filter != "all":
            self._apply_visibility()

    def set_filter(self, key: str):
        self._filter = key
        self._apply_visibility()

    def set_removal_enabled(self, enabled: bool):
        """Während eines Laufs lässt sich nichts entfernen - der Knopf
        erscheint dann gar nicht erst."""
        self._removal_enabled = enabled
        self._set_hover_row(self._hover_row)

    def row_of(self, index: int) -> Optional[int]:
        """Tabellenzeile einer Datei - für Tests und Diagnose."""
        return self._row_of_index.get(index)

    def state_text(self, r: int) -> str:
        """Was die Zustands-Zelle einer Zeile sagt - für Tests und Diagnose."""
        cell = self.cellWidget(r, COL_PROGRESS)
        return cell.text() if isinstance(cell, _ProgressCell) else ""

    # =========================================================================
    # Zeilen bauen
    # =========================================================================

    def _item(self, r: int, col: int, centered: bool = False) -> QTableWidgetItem:
        item = QTableWidgetItem()
        if centered:
            item.setTextAlignment(Qt.AlignCenter)
        self.setItem(r, col, item)
        return item

    def _build_file_row(self, r: int, row: Row):
        video = self._videos[row.index]
        name = self._item(r, COL_NAME)
        # Folgen stehen eingerückt unter ihrer Staffel.
        name.setText(("      " if row.parent else "") + video.source_path.name)
        name.setToolTip(
            f"{video.source_path}\n→ {relative_target(video.target_path, self._output_base)}"
            if video.target_path else str(video.source_path))

        self.setCellWidget(r, COL_PROGRESS, _ProgressCell())
        self._item(r, COL_SIZE, centered=True)

        remove = _RemoveCell()
        remove.button.clicked.connect(lambda _c=False, v=video: self.remove_requested.emit(v))
        self.setCellWidget(r, COL_REMOVE, remove)

        self._update_file_row(r, video)

    def _update_file_row(self, r: int, video: VideoFile):
        colors = theme.semantic_colors()

        cell = self.cellWidget(r, COL_PROGRESS)
        if isinstance(cell, _ProgressCell):
            if video.status == FileStatus.VERARBEITET:
                cell.show_progress(video.progress, self._speed_text(video))
            else:
                cell.show_status(tr(video.status.value),
                                 _STATUS_COLOR.get(video.status, "neutral"))
            cell.setToolTip(video.error_message if video.status == FileStatus.FEHLER else "")

        size = self.item(r, COL_SIZE)
        if size is not None:
            size.setText(size_change(video.original_size, video.new_size))
            if video.new_size > 0 and video.original_size > 0:
                kleiner = video.new_size < video.original_size
                size.setForeground(QColor(colors["success" if kleiner else "error"]))

    @staticmethod
    def _speed_text(video: VideoFile) -> str:
        """Unter dem Balken einer laufenden Datei: Prozent und Restzeit.

        Bewusst keine Bilder pro Sekunde. Die Zahl sagt nur etwas, wenn man
        weiss, wie viele Bilder der Film hat - und das weiss niemand. Wie weit
        und wie lange noch beantwortet die Frage, die man an eine laufende
        Datei tatsächlich hat."""
        if video.status != FileStatus.VERARBEITET:
            return ""
        text = f"{video.progress} %"
        rest = remaining_seconds(video)
        if rest is not None:
            text += " · " + tr("noch {time}").format(time=format_duration(rest))
        return text

    def _build_group_row(self, r: int, group: Group):
        name = self._item(r, COL_NAME)
        # Dieselbe Schrift wie die übrigen Zellen, nur kräftiger. item.font()
        # wäre die Vorgabe der Anwendung - eine andere Grösse als die, in der
        # die Tabelle zeichnet.
        name.setFont(getFont(13, QFont.DemiBold))
        first = self._videos[group.indices[0]].target_path if group.indices else None
        hinweis = tr("Klicken, um die Folgen ein- oder auszublenden")
        if first is not None:
            hinweis += f"\n→ {relative_target(first.parent, self._output_base)}"
        name.setToolTip(hinweis)

        self.setCellWidget(r, COL_PROGRESS, _ProgressCell())
        self._item(r, COL_SIZE, centered=True)
        self._item(r, COL_REMOVE)
        self.removeCellWidget(r, COL_REMOVE)

        self._update_group_row(r, group)

    def _update_group_row(self, r: int, group: Group):
        colors = theme.semantic_colors()
        summary = summarize(group, self._videos)

        name = self.item(r, COL_NAME)
        if name is not None:
            pfeil = "▸" if group.key in self._collapsed else "▾"
            titel = group.name
            if group.season is not None:
                titel += " · " + tr("Staffel {number}").format(number=group.season)
            name.setText(f"{pfeil}  {titel}")

        cell = self.cellWidget(r, COL_PROGRESS)
        if isinstance(cell, _ProgressCell):
            if summary.running:
                cell.show_progress(
                    summary.progress,
                    f"{summary.progress} % · " + tr("{count} laufen").format(count=summary.running))
            else:
                farbe = ("error" if summary.failed
                         else "success" if summary.done == summary.total else "neutral")
                cell.show_status(
                    tr("{done}/{total} fertig").format(done=summary.done, total=summary.total),
                    farbe)
            cell.setToolTip(tr("{count} fehlgeschlagen").format(count=summary.failed)
                            if summary.failed else "")

        size = self.item(r, COL_SIZE)
        if size is not None:
            size.setText(size_change(summary.original_size, summary.new_size))
            if summary.new_size > 0:
                kleiner = summary.new_size < summary.original_size
                size.setForeground(QColor(colors["success" if kleiner else "error"]))

    # =========================================================================
    # Entfernen-Knopf: nur in der Zeile unter der Maus
    # =========================================================================

    def _set_hover_row(self, r: Optional[int], _col: int = 0):
        """Zeigt den Entfernen-Knopf in genau einer Zeile.

        Ein X in jeder Zeile war eine Spalte voller Knöpfe, von denen man im
        Lauf keinen und sonst selten einen braucht."""
        for zeile in {self._hover_row, r}:
            if zeile is None:
                continue
            cell = self.cellWidget(zeile, COL_REMOVE)
            if isinstance(cell, _RemoveCell):
                cell.button.setVisible(zeile == r and self._removal_enabled)
        self._hover_row = r

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._set_hover_row(None)

    # =========================================================================
    # Sichtbarkeit: Filter und zugeklappte Staffeln
    # =========================================================================

    def _apply_visibility(self):
        sichtbare_folgen: Dict[tuple, int] = {}
        for r, row in enumerate(self._rows):
            if row.is_group:
                continue
            passt = matches_filter(self._videos[row.index].status, self._filter)
            if row.parent is not None:
                if passt:
                    sichtbare_folgen[row.parent.key] = sichtbare_folgen.get(row.parent.key, 0) + 1
                passt = passt and row.parent.key not in self._collapsed
            self.setRowHidden(r, not passt)

        # Eine Staffel, von der der Filter nichts übrig lässt, verschwindet ganz.
        for key, r in self._row_of_group.items():
            self.setRowHidden(r, sichtbare_folgen.get(key, 0) == 0)

    def _on_cell_clicked(self, r: int, _col: int):
        if not (0 <= r < len(self._rows)):
            return
        row = self._rows[r]
        if row.is_group:
            key = row.group.key
            if key in self._collapsed:
                self._collapsed.discard(key)
            else:
                self._collapsed.add(key)
            self._update_group_row(r, row.group)
            self._apply_visibility()
        elif 0 <= row.index < len(self._videos):
            self.video_selected.emit(self._videos[row.index])
