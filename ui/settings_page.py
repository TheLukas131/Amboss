"""Einstellungsseite: Design, Sprache und die Zielordner je Kategorie.

Die Kategorien sind bewusst nicht fest verdrahtet. Ist eine nicht angehakt, gilt
sie als nicht vorhanden und alles Erkannte wird auf die nächstpassende gefaltet
(siehe models.fold_to_enabled). Damit funktioniert die Anwendung genauso für
jemanden, der nur "Movies" und "TV" führt, wie für eine nach Anime getrennte
Sammlung.

Die Kategoriezeilen selbst stecken in ui/category_editor.py, weil sie auch im
Einrichtungsdialog beim ersten Start gebraucht werden.
"""

from typing import Callable, Dict

from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout
from qfluentwidgets import (
    BodyLabel, CaptionLabel, CardWidget, ComboBox, PushButton, StrongBodyLabel, TitleLabel,
)

from i18n import tr
from ui.brand_widgets import AV1_TRADEMARK_NOTE
from ui.category_editor import CategoryFolderEditor
from ui.widgets import ScrollablePage, enforce_control_heights

LANGUAGE_OPTIONS = [
    ("auto", "Automatisch (Systemsprache)"),
    ("de", "Deutsch"),
    ("en", "English"),
]


class SettingsPage(ScrollablePage):
    """Alles, was man einmal einstellt und dann in Ruhe lässt."""

    def __init__(self, theme_toggle_builder: Callable[[], QHBoxLayout],
                 on_changed: Callable[[], None], parent=None):
        super().__init__("settingsPage", parent)
        self._on_changed = on_changed
        self._build(theme_toggle_builder)
        enforce_control_heights(self)

    def _build(self, theme_toggle_builder: Callable[[], QHBoxLayout]):
        outer = self.content_layout

        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title_col.addWidget(TitleLabel(tr("Einstellungen")))
        title_col.addWidget(CaptionLabel(tr("Design, Sprache und wohin die fertigen Dateien gehören.")))
        outer.addLayout(title_col)

        # --- Darstellung ---
        appearance = self._card(outer, tr("Darstellung"))
        theme_row = QHBoxLayout()
        theme_row.addWidget(BodyLabel(tr("Design")))
        theme_row.addStretch()
        theme_row.addLayout(theme_toggle_builder())
        appearance.addLayout(theme_row)

        language_row = QHBoxLayout()
        language_row.addWidget(BodyLabel(tr("Sprache")))
        language_row.addStretch()
        self.language_combo = ComboBox()
        self.language_combo.setMinimumWidth(260)
        for value, label in LANGUAGE_OPTIONS:
            self.language_combo.addItem(tr(label), userData=value)
        self.language_combo.currentIndexChanged.connect(lambda _i: self._on_changed())
        language_row.addWidget(self.language_combo)
        appearance.addLayout(language_row)

        self.language_hint = CaptionLabel("")
        self.language_hint.setVisible(False)
        appearance.addWidget(self.language_hint)

        # --- Kategorien ---
        categories = self._card(outer, tr("Mediathek"))
        info = CaptionLabel(tr(
            "Hake an, was du führst, und wähle den zugehörigen Ordner. Was du weglässt, "
            "gibt es für Amboss nicht - entsprechende Dateien werden dann der "
            "nächstpassenden Kategorie zugeordnet. Ohne jeden Ordner wird nur konvertiert "
            "und nichts verschoben; auch das ist in Ordnung."
        ))
        info.setWordWrap(True)
        categories.addWidget(info)

        self.editor = CategoryFolderEditor(on_changed=self._on_editor_changed)
        categories.addWidget(self.editor)

        detect_row = QHBoxLayout()
        detect_row.addStretch()
        self.detect_btn = PushButton(tr("Aus einem Medienordner erkennen"))
        self.detect_btn.setToolTip(tr(
            "Wähle den Ordner, in dem deine Mediathek liegt. Vorhandene "
            "Unterordner werden den passenden Kategorien zugeordnet."
        ))
        self.detect_btn.clicked.connect(self._detect_from_library)
        detect_row.addWidget(self.detect_btn)
        categories.addLayout(detect_row)

        self.category_status = CaptionLabel("")
        self.category_status.setWordWrap(True)
        categories.addWidget(self.category_status)

        # Markenhinweis: AV1 ist eine eingetragene Marke, die Nennung im
        # Programm gehoert zur korrekten Zuordnung.
        notice = CaptionLabel(tr(AV1_TRADEMARK_NOTE))
        notice.setWordWrap(True)
        outer.addWidget(notice)

        outer.addStretch()

    def _card(self, parent_layout, title: str) -> QVBoxLayout:
        card = CardWidget()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        layout.addWidget(StrongBodyLabel(title))
        parent_layout.addWidget(card)
        return layout

    # =========================================================================
    # Aktionen
    # =========================================================================

    def _on_editor_changed(self):
        self._refresh_status()
        self._on_changed()

    def _refresh_status(self):
        missing = self.editor.incomplete()
        if missing:
            self.category_status.setText(tr("Bitte einen Ordner wählen für: {list}").format(
                list=", ".join(tr(c) for c in missing)))
            return
        count = self.editor.active_count()
        if count == 1:
            text = tr('1 Kategorie eingerichtet.')
        elif count:
            text = tr('{count} Kategorien eingerichtet.').format(count=count)
        else:
            text = tr('Keine Kategorie eingerichtet - Amboss konvertiert dann nur und verschiebt nichts.')
        self.category_status.setText(text)

    def _detect_from_library(self):
        root = QFileDialog.getExistingDirectory(self, tr("Medienordner auswählen"))
        if not root:
            return
        if not self.editor.detect_from_folder(root):
            self.category_status.setText(
                tr("Keine bekannten Ordnernamen gefunden - bitte von Hand auswählen."))

    # =========================================================================
    # Werte lesen/schreiben
    # =========================================================================

    def incomplete(self) -> list:
        return self.editor.incomplete()

    def category_folders(self) -> Dict[str, str]:
        return self.editor.values()

    def set_category_folders(self, folders: Dict[str, str]):
        self.editor.set_values(folders)
        self._refresh_status()

    def language(self) -> str:
        return self.language_combo.currentData() or "auto"

    def set_language(self, value: str):
        index = self.language_combo.findData(value)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)

    def show_restart_hint(self):
        self.language_hint.setText(
            tr("Die Sprache wird beim nächsten Start der Anwendung übernommen."))
        self.language_hint.setVisible(True)
