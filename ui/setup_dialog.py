"""Einmalige Einrichtung beim allerersten Start.

Ohne diesen Schritt startet die Anwendung mit vier leeren Zielordnern, und man
sieht ihr nicht an, dass das Einsortieren deshalb nicht funktioniert - es fällt
erst auf, wenn nach einer fertigen Konvertierung nichts verschoben wird. Der
Dialog fragt einmal ab, was tatsächlich vorhanden ist.

Alles hier Eingestellte ist später unter Einstellungen änderbar; der Dialog
erscheint nur, solange noch keine Konfiguration existiert.
"""

from typing import Dict

from PyQt5.QtWidgets import QFileDialog, QHBoxLayout
from qfluentwidgets import (
    BodyLabel, CaptionLabel, ComboBox, PushButton, StrongBodyLabel, TitleLabel,
)

from i18n import tr
from ui.dialog_base import FittedMessageBox
from ui.category_editor import CategoryFolderEditor

LANGUAGE_OPTIONS = [
    ("auto", "Automatisch (Systemsprache)"),
    ("de", "Deutsch"),
    ("en", "English"),
]


class SetupDialog(FittedMessageBox):
    """Fragt Sprache, Design und die vorhandenen Kategorien ab."""

    def __init__(self, theme_toggle_builder, parent=None):
        super().__init__(parent)
        self.widget.setMinimumSize(720, 560)
        self._build(theme_toggle_builder)

    def _build(self, theme_toggle_builder):
        self.viewLayout.addWidget(TitleLabel(tr("Willkommen bei Amboss")))
        intro = BodyLabel(tr(
            "Einmalige Einrichtung. Alles lässt sich später unter Einstellungen ändern."
        ))
        intro.setWordWrap(True)
        self.viewLayout.addWidget(intro)

        appearance = QHBoxLayout()
        appearance.setSpacing(12)
        appearance.addWidget(BodyLabel(tr("Sprache")))
        self.language_combo = ComboBox()
        self.language_combo.setMinimumWidth(230)
        for value, label in LANGUAGE_OPTIONS:
            self.language_combo.addItem(tr(label), userData=value)
        appearance.addWidget(self.language_combo)
        appearance.addSpacing(20)
        appearance.addWidget(BodyLabel(tr("Design")))
        appearance.addLayout(theme_toggle_builder())
        appearance.addStretch()
        self.viewLayout.addLayout(appearance)

        self.viewLayout.addWidget(StrongBodyLabel(tr("Was hast du in deiner Mediathek?")))
        explain = CaptionLabel(tr(
            "Hake an, was du führst, und wähle den zugehörigen Ordner. Was du weglässt, "
            "gibt es für Amboss nicht - entsprechende Dateien werden dann der "
            "nächstpassenden Kategorie zugeordnet. Ohne jeden Ordner wird nur konvertiert "
            "und nichts verschoben; auch das ist in Ordnung."
        ))
        explain.setWordWrap(True)
        self.viewLayout.addWidget(explain)

        self.editor = CategoryFolderEditor(on_changed=self._update_summary)
        self.viewLayout.addWidget(self.editor)

        detect_row = QHBoxLayout()
        self.detect_btn = PushButton(tr("Aus einem Medienordner erkennen"))
        self.detect_btn.setToolTip(tr(
            "Wähle den Ordner, in dem deine Mediathek liegt. Vorhandene "
            "Unterordner werden den passenden Kategorien zugeordnet."
        ))
        self.detect_btn.clicked.connect(self._detect)
        detect_row.addWidget(self.detect_btn)
        detect_row.addStretch()
        self.viewLayout.addLayout(detect_row)

        self.summary = CaptionLabel("")
        self.summary.setWordWrap(True)
        self.viewLayout.addWidget(self.summary)

        self.yesButton.setText(tr("Los geht's"))
        self.hideCancelButton()
        self._update_summary()

    def _detect(self):
        root = QFileDialog.getExistingDirectory(self, tr("Medienordner auswählen"))
        if not root:
            return
        found = self.editor.detect_from_folder(root)
        if not found:
            self.summary.setText(tr("Keine bekannten Ordnernamen gefunden - bitte von Hand auswählen."))

    def _update_summary(self):
        count = self.editor.active_count()
        if count == 1:
            text = tr('1 Kategorie eingerichtet.')
        elif count:
            text = tr('{count} Kategorien eingerichtet.').format(count=count)
        else:
            text = tr('Keine Kategorie eingerichtet - Amboss konvertiert dann nur und verschiebt nichts.')
        self.summary.setText(text)

    def validate(self) -> bool:
        """Wird vor dem Schliessen aufgerufen - blockt, solange eine angehakte
        Kategorie noch keinen Ordner hat."""
        missing = self.editor.incomplete()
        if missing:
            self.summary.setText(tr("Bitte einen Ordner wählen für: {list}").format(
                list=", ".join(tr(c) for c in missing)))
            return False
        return True

    # =========================================================================
    # Ergebnis
    # =========================================================================

    def category_folders(self) -> Dict[str, str]:
        return self.editor.values()

    def language(self) -> str:
        return self.language_combo.currentData() or "auto"
