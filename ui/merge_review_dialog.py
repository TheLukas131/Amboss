"""Dialog zur Bestätigung von erkannten Ordner-Zusammenführungen.

Wird NACH Abschluss einer Konvertierung gezeigt (nie währenddessen) und listet
jeden gefundenen Präfix-Namens-Kandidaten einzeln mit Ja/Nein auf.

Erbt von MessageBoxBase statt einem nackten QDialog - nur so bekommt der Dialog
den zum aktuellen Theme passenden Hintergrund (sonst wirken die Fluent-Widgets
im Dunkelmodus wie ausgegraut, weil sie auf dem hellen QDialog-Standard-
Hintergrund landen)."""

from typing import List

from PyQt5.QtWidgets import QHBoxLayout, QScrollArea, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CardWidget, PushButton, TitleLabel

from merge_detector import MergeCandidate, merge_folders
from i18n import tr
from ui.dialog_base import FittedMessageBox


class MergeReviewDialog(FittedMessageBox):
    def __init__(self, candidates: List[MergeCandidate], parent=None):
        super().__init__(parent)
        self.candidates = candidates
        self.widget.setMinimumSize(620, 420)
        self._build_ui()

    def _build_ui(self):
        self.viewLayout.addWidget(TitleLabel(tr("Mögliche Namens-Duplikate")))

        info = BodyLabel(tr(
            "Es wurden Ordnernamen gefunden, bei denen einer exakt der Anfang eines anderen ist - "
            "ein typisches Zeichen für einen beim Download abgeschnittenen Namen (z.B. durch das "
            "Windows-Zeichenlimit). Wähle pro Vorschlag, ob zusammengeführt werden soll. Die bereits "
            "konvertierten Dateien sind davon unabhängig - dies betrifft nur die Ordnerstruktur."
        ))
        info.setWordWrap(True)
        self.viewLayout.addWidget(info)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(10)

        for candidate in self.candidates:
            container_layout.addWidget(self._build_candidate_row(candidate))
        container_layout.addStretch()

        scroll.setWidget(container)
        self.viewLayout.addWidget(scroll, 1)

        self.yesButton.setText(tr("Schließen"))
        self.hideCancelButton()

    def _build_candidate_row(self, candidate: MergeCandidate) -> CardWidget:
        card = CardWidget()
        row = QVBoxLayout(card)
        row.setContentsMargins(16, 14, 16, 14)
        row.setSpacing(8)

        label = BodyLabel(tr(
            "'{shorter}' ({shorter_count} Dateien) und '{longer}' ({longer_count} Dateien) scheinen "
            "dieselbe Serie zu sein.\nZusammenführen zu '{longer}'?"
        ).format(shorter=candidate.shorter.name, shorter_count=candidate.shorter_file_count,
                 longer=candidate.longer.name, longer_count=candidate.longer_file_count))
        label.setWordWrap(True)
        row.addWidget(label)

        btn_row = QHBoxLayout()
        yes_btn = PushButton(tr("Ja, zusammenführen"))
        no_btn = PushButton(tr("Nein"))
        btn_row.addWidget(yes_btn)
        btn_row.addWidget(no_btn)
        btn_row.addStretch()
        row.addLayout(btn_row)

        def do_merge():
            try:
                merge_folders(candidate)
                label.setText(tr("Zusammengeführt zu '{name}'").format(name=candidate.longer.name))
            except OSError as e:
                label.setText(tr("Fehler beim Zusammenführen: {error}").format(error=e))
            yes_btn.setEnabled(False)
            no_btn.setEnabled(False)

        def dismiss():
            label.setText(label.text() + "\n" + tr("(Nicht zusammengeführt)"))
            yes_btn.setEnabled(False)
            no_btn.setEnabled(False)

        yes_btn.clicked.connect(do_merge)
        no_btn.clicked.connect(dismiss)

        return card
