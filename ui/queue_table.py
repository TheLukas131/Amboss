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
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QAbstractItemView, QHeaderView, QTableWidgetItem, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    CaptionLabel, FluentIcon, ProgressBar, TableWidget, TransparentToolButton,
)
from qfluentwidgets.common.font import getFont

from i18n import tr
from models import FileStatus, VideoFile
from queue_model import (
    COLLAPSE_ABOVE, Group, Row, build_rows, format_duration,
    matches_filter, relative_target, remaining_seconds, size_change, summarize,
)
from ui import theme

COL_NAME, COL_TYPE, COL_STATUS, COL_PROGRESS, COL_SIZE, COL_TARGET, COL_REMOVE = range(7)

# Unter dieser Breite verschwindet die Ziel-Spalte: sie ist die einzige, deren
# Inhalt auch anderswo steht (im Tooltip des Dateinamens), und ohne sie bleibt
# dem Namen genug Platz.
_HIDE_TARGET_BELOW = 860

_STATUS_COLOR = {
    FileStatus.WARTEND: "neutral", FileStatus.VERARBEITET: "accent",
    FileStatus.FERTIG: "success", FileStatus.FEHLER: "error",
    FileStatus.UEBERSPRUNGEN: "neutral", FileStatus.PAUSIERT: "warning",
}


class _ProgressCell(QWidget):
    """Balken, darunter bei laufenden Dateien Tempo und Restzeit."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(3)
        layout.addStretch()
        self.bar = ProgressBar()
        layout.addWidget(self.bar)
        self.caption = CaptionLabel("")
        self.caption.setAlignment(Qt.AlignCenter)
        self.caption.setVisible(False)
        layout.addWidget(self.caption)
        layout.addStretch()

    def show_progress(self, value: int, caption: str = ""):
        if self.bar.value() != value:
            self.bar.setValue(value)
        if self.caption.text() != caption:
            self.caption.setText(caption)
            self.caption.setVisible(bool(caption))


class QueueTable(TableWidget):
    """Warteschlange mit Staffel-Zeilen, relativen Zielen und Live-Zahlen."""

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

        self.setBorderVisible(True)
        self.setBorderRadius(8)
        self.setColumnCount(7)
        self.setHorizontalHeaderLabels([
            tr("Dateiname"), tr("Typ"), tr("Status"), tr("Fortschritt"),
            tr("Größe"), tr("Ziel"), "",
        ])
        header = self.horizontalHeader()
        # Name und Ziel teilen sich, was die festen Spalten übrig lassen - der
        # Name bekommt den grösseren Teil (siehe resizeEvent). QHeaderView kennt
        # nur "alle dehnbaren gleich breit", und das gab dem Ziel so viel Platz
        # wie dem Namen, obwohl es inzwischen der kürzere Text ist.
        for spalte in range(7):
            header.setSectionResizeMode(spalte, QHeaderView.Fixed)
        self.setColumnWidth(COL_TYPE, 96)
        self.setColumnWidth(COL_STATUS, 108)
        self.setColumnWidth(COL_PROGRESS, 150)
        self.setColumnWidth(COL_SIZE, 196)
        self.setColumnWidth(COL_REMOVE, 44)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # Eine Zeile je Datei - der Zielpfad bricht nicht mehr um.
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideMiddle)
        self.verticalHeader().setDefaultSectionSize(44)
        self.verticalHeader().setVisible(False)
        self.setMinimumHeight(240)

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
        """Zeichnet eine Datei nach - Status, Fortschritt, Größe - und die
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
        self._removal_enabled = enabled
        for r in self._row_of_index.values():
            widget = self.cellWidget(r, COL_REMOVE)
            if widget is not None:
                widget.setEnabled(enabled)

    def row_of(self, index: int) -> Optional[int]:
        """Tabellenzeile einer Datei - für Tests und Diagnose."""
        return self._row_of_index.get(index)

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

        self._item(r, COL_TYPE, centered=True).setText(tr(video.media_type.value))
        self._item(r, COL_STATUS, centered=True)
        self.setCellWidget(r, COL_PROGRESS, _ProgressCell())
        self._item(r, COL_SIZE, centered=True)

        target = self._item(r, COL_TARGET)
        if row.parent and video.target_path:
            # Der Ordner steht schon in der Staffel-Zeile darüber.
            target.setText(video.target_path.name)
        else:
            target.setText(relative_target(video.target_path, self._output_base))
        target.setToolTip(str(video.target_path) if video.target_path else "")
        name.setToolTip(f"{video.source_path}\n→ {video.target_path}"
                        if video.target_path else str(video.source_path))

        remove_btn = TransparentToolButton(FluentIcon.CLOSE)
        remove_btn.setToolTip(tr("Aus der Warteschlange entfernen"))
        remove_btn.setFixedSize(28, 28)
        remove_btn.setEnabled(self._removal_enabled)
        remove_btn.clicked.connect(lambda _c=False, v=video: self.remove_requested.emit(v))
        self.setCellWidget(r, COL_REMOVE, remove_btn)

        self._update_file_row(r, video)

    def _update_file_row(self, r: int, video: VideoFile):
        colors = theme.semantic_colors()

        status = self.item(r, COL_STATUS)
        if status is not None:
            status.setText(tr(video.status.value))
            status.setForeground(QColor(colors[_STATUS_COLOR.get(video.status, "neutral")]))
            status.setToolTip(video.error_message if video.status == FileStatus.FEHLER else "")

        cell = self.cellWidget(r, COL_PROGRESS)
        if isinstance(cell, _ProgressCell):
            cell.show_progress(video.progress, self._speed_text(video))

        size = self.item(r, COL_SIZE)
        if size is not None:
            size.setText(size_change(video.original_size, video.new_size))
            if video.new_size > 0 and video.original_size > 0:
                kleiner = video.new_size < video.original_size
                size.setForeground(QColor(colors["success" if kleiner else "error"]))

    @staticmethod
    def _speed_text(video: VideoFile) -> str:
        if video.status != FileStatus.VERARBEITET or video.encode_fps <= 0:
            return ""
        text = f"{video.encode_fps:.0f} fps"
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
        name.setToolTip(tr("Klicken, um die Folgen ein- oder auszublenden"))

        self._item(r, COL_TYPE, centered=True).setText(tr(group.media_type.value))
        self._item(r, COL_STATUS, centered=True)
        self.setCellWidget(r, COL_PROGRESS, _ProgressCell())
        self._item(r, COL_SIZE, centered=True)

        target = self._item(r, COL_TARGET)
        first = self._videos[group.indices[0]].target_path if group.indices else None
        if first is not None:
            target.setText(relative_target(first.parent, self._output_base))
            target.setToolTip(str(first.parent))
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

        status = self.item(r, COL_STATUS)
        if status is not None:
            status.setText(tr("{done}/{total} fertig").format(done=summary.done, total=summary.total))
            if summary.failed:
                farbe = "error"
                status.setToolTip(tr("{count} fehlgeschlagen").format(count=summary.failed))
            else:
                status.setToolTip("")
                farbe = ("accent" if summary.running
                         else "success" if summary.done == summary.total else "neutral")
            status.setForeground(QColor(colors[farbe]))

        cell = self.cellWidget(r, COL_PROGRESS)
        if isinstance(cell, _ProgressCell):
            laufend = (tr("{count} laufen").format(count=summary.running)
                       if summary.running else "")
            cell.show_progress(summary.progress, laufend)

        size = self.item(r, COL_SIZE)
        if size is not None:
            size.setText(size_change(summary.original_size, summary.new_size))
            if summary.new_size > 0:
                kleiner = summary.new_size < summary.original_size
                size.setForeground(QColor(colors["success" if kleiner else "error"]))

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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        breite = self.viewport().width()
        ohne_ziel = breite < _HIDE_TARGET_BELOW
        self.setColumnHidden(COL_TARGET, ohne_ziel)
        fest = sum(self.columnWidth(spalte) for spalte in
                   (COL_TYPE, COL_STATUS, COL_PROGRESS, COL_SIZE, COL_REMOVE))
        frei = max(breite - fest, 240)
        if ohne_ziel:
            self.setColumnWidth(COL_NAME, frei)
        else:
            self.setColumnWidth(COL_NAME, int(frei * 0.58))
            self.setColumnWidth(COL_TARGET, frei - int(frei * 0.58))
