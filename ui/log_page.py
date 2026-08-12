"""Log-Ansicht mit Lazy-Loading/Pagination.

Ein langer Konvertierungslauf kann zehntausende Zeilen produzieren. Die alte
Implementierung hielt den kompletten Text in einem einzigen QTextEdit, das bei
jedem Öffnen des Tabs neu layouten musste - das führte zu spürbaren Einfrierern,
proportional zur Log-Größe.

Diese Version hält den vollständigen Verlauf nur als Python-Liste (billig) und
rendert standardmäßig nur die letzten LOG_PAGE_SIZE Zeilen in das Textfeld.
Beim Anzeigen der Seite wird immer nur ein frischer Tail gerendert (nie der
komplette Backlog); ein Button lädt bei Bedarf ältere Zeilen in 100er-Schritten
nach, mit Erhalt der Scroll-Position.
"""

from datetime import datetime
from pathlib import Path
from typing import List

from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import CardWidget, PlainTextEdit, PushButton, StrongBodyLabel
from i18n import tr
from ui.widgets import apply_surface_background

LOG_PAGE_SIZE = 100

# Obergrenze für den im Speicher gehaltenen Verlauf. FFmpeg liefert pro Datei
# hunderte "fps="-Zeilen; über einen langen Batch hinweg wuchs die Liste bisher
# unbegrenzt. Beim Überschreiten fällt der älteste Block weg.
MAX_LOG_LINES = 20_000
_TRIM_CHUNK = 2_000


class LogPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("logPage")
        apply_surface_background(self)

        self._log_lines: List[str] = []
        self._rendered_count = 0
        self._total_at_last_render = 0
        self._is_active = False

        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        card = CardWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.addWidget(StrongBodyLabel(tr("Protokoll")))
        header_row.addStretch()

        clear_btn = PushButton(tr("Leeren"))
        clear_btn.clicked.connect(self.clear)
        header_row.addWidget(clear_btn)

        save_btn = PushButton(tr("Speichern"))
        save_btn.clicked.connect(self._save_to_file)
        header_row.addWidget(save_btn)
        card_layout.addLayout(header_row)

        self.load_more_btn = PushButton("")
        self.load_more_btn.clicked.connect(self._load_older)
        self.load_more_btn.setVisible(False)
        card_layout.addWidget(self.load_more_btn)

        self.text_edit = PlainTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setLineWrapMode(PlainTextEdit.NoWrap)
        card_layout.addWidget(self.text_edit, 1)

        outer.addWidget(card, 1)

    # =========================================================================
    # Öffentliche API
    # =========================================================================

    def append(self, message: str):
        """Fügt eine neue Log-Zeile an (wird laufend während der Konvertierung aufgerufen)."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}"
        self._log_lines.append(line)

        if self._is_active:
            self._rendered_count += 1
            self._total_at_last_render += 1
            self.text_edit.appendPlainText(line)

        if len(self._log_lines) > MAX_LOG_LINES:
            self._trim_oldest()

    def _trim_oldest(self):
        """Wirft den ältesten Block weg und korrigiert die Zähler, damit das
        gerenderte Fenster und der "ältere laden"-Button konsistent bleiben."""
        del self._log_lines[:_TRIM_CHUNK]
        self._rendered_count = min(self._rendered_count, len(self._log_lines))
        self._total_at_last_render = max(0, self._total_at_last_render - _TRIM_CHUNK)

    def set_active(self, active: bool):
        """Von MainWindow aufgerufen, wenn diese Seite zur aktuell sichtbaren
        Navigationsseite wird bzw. das nicht mehr ist. qfluentwidgets' animierter
        Seitenwechsel liefert kein zuverlässiges QShowEvent, daher die explizite
        Ansteuerung statt sich auf isVisible()/showEvent() allein zu verlassen."""
        self._is_active = active
        if active:
            self.ensure_rendered()

    def clear(self):
        self._log_lines.clear()
        self._rendered_count = 0
        self._total_at_last_render = 0
        self.text_edit.clear()
        self.load_more_btn.setVisible(False)

    def full_text(self) -> str:
        return "\n".join(self._log_lines)

    # =========================================================================
    # Rendering / Pagination
    # =========================================================================

    def showEvent(self, event):
        super().showEvent(event)
        self.ensure_rendered()

    def ensure_rendered(self):
        """Rendert bei Bedarf einen frischen Tail. Wird sowohl von showEvent()
        als auch explizit von MainWindow beim Seitenwechsel aufgerufen, da
        qfluentwidgets' animierter StackedWidget-Seitenwechsel nicht immer
        zuverlässig ein synchrones QShowEvent auslöst."""
        if len(self._log_lines) != self._total_at_last_render:
            self._rendered_count = min(LOG_PAGE_SIZE, len(self._log_lines))
            self._render_window(preserve_scroll=False)

    def _load_older(self):
        total = len(self._log_lines)
        remaining = total - self._rendered_count
        if remaining <= 0:
            self.load_more_btn.setVisible(False)
            return
        self._rendered_count += min(LOG_PAGE_SIZE, remaining)
        self._render_window(preserve_scroll=True)

    def _render_window(self, preserve_scroll: bool):
        scrollbar = self.text_edit.verticalScrollBar()
        old_max = scrollbar.maximum()
        old_value = scrollbar.value()

        total = len(self._log_lines)
        start = max(0, total - self._rendered_count)
        self.text_edit.setPlainText("\n".join(self._log_lines[start:]))
        self._total_at_last_render = total

        remaining = start
        if remaining > 0:
            self.load_more_btn.setText(
                tr("{count} ältere Einträge laden ({remaining} weitere verfügbar)")
                .format(count=min(LOG_PAGE_SIZE, remaining), remaining=remaining)
            )
            self.load_more_btn.setVisible(True)
        else:
            self.load_more_btn.setVisible(False)

        if preserve_scroll:
            new_max = scrollbar.maximum()
            scrollbar.setValue(old_value + (new_max - old_max))
        else:
            scrollbar.setValue(scrollbar.maximum())

    def _save_to_file(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, tr("Log speichern"),
            f"amboss_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            tr("Textdateien (*.txt)"),
        )
        if filename:
            Path(filename).write_text(self.full_text(), encoding="utf-8")
