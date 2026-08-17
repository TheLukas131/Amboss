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

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout
from qfluentwidgets import (
    BodyLabel, CaptionLabel, CardWidget, CheckBox, ComboBox, PushButton,
    StrongBodyLabel, TitleLabel,
)

from i18n import tr
from models import APP_NAME, APP_VERSION
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

    # Der Nutzer hat "Jetzt nach Updates suchen" gedrückt. Die Prüfung selbst
    # gehört ins Hauptfenster, das den Thread und den Dialog verwaltet.
    check_now_requested = pyqtSignal()

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

        about = self._card(outer, tr("Über Amboss"))
        version_row = QHBoxLayout()
        version_row.addWidget(BodyLabel(f"{APP_NAME} {APP_VERSION}"))
        version_row.addStretch()
        self.changelog_btn = PushButton(tr("Änderungsverlauf"))
        self.changelog_btn.clicked.connect(self._show_changelog)
        version_row.addWidget(self.changelog_btn)
        about.addLayout(version_row)

        # --- Updates ---
        #
        # Die Prüfung ist eine Nachfrage, kein Download: Amboss holt nie selbst
        # eine neue Fassung und tauscht sich nicht aus. Der Hinweis darunter
        # sagt genau das - und was dabei übertragen wird, nämlich nichts außer
        # der Anfrage.
        update_row = QHBoxLayout()
        self.update_check_box = CheckBox(tr("Beim Start nach neuen Versionen suchen"))
        self.update_check_box.stateChanged.connect(lambda _s: self._on_changed())
        update_row.addWidget(self.update_check_box)
        update_row.addStretch()
        self.update_now_btn = PushButton(tr("Jetzt suchen"))
        self.update_now_btn.clicked.connect(self.check_now_requested.emit)
        update_row.addWidget(self.update_now_btn)
        about.addLayout(update_row)

        update_hint = CaptionLabel(tr(
            "Fragt bei GitHub nach der neuesten Version. Heruntergeladen wird "
            "nichts - gemeldet wird nur, dass es etwas Neues gibt, mit einem "
            "Verweis auf die Projektseite. Übertragen wird dabei nichts außer "
            "der Anfrage selbst."
        ))
        update_hint.setWordWrap(True)
        about.addWidget(update_hint)

        self.update_status = CaptionLabel("")
        self.update_status.setWordWrap(True)
        self.update_status.setVisible(False)
        about.addWidget(self.update_status)

        # Markenhinweis: AV1 ist eine eingetragene Marke, die Nennung im
        # Programm gehoert zur korrekten Zuordnung.
        notice = CaptionLabel(tr(AV1_TRADEMARK_NOTE))
        notice.setWordWrap(True)
        about.addWidget(notice)

        outer.addStretch()

    def _show_changelog(self):
        from ui.changelog_dialog import ChangelogDialog
        ChangelogDialog(self.window()).exec()

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

    def check_for_updates(self) -> bool:
        return self.update_check_box.isChecked()

    def set_check_for_updates(self, value: bool):
        self.update_check_box.setChecked(bool(value))

    def set_update_status(self, text: str, busy: bool = False):
        """Ergebnis der manuellen Prüfung unter den Schalter schreiben."""
        self.update_now_btn.setEnabled(not busy)
        self.update_status.setText(text)
        self.update_status.setVisible(bool(text))

    def show_restart_hint(self):
        self.language_hint.setText(
            tr("Die Sprache wird beim nächsten Start der Anwendung übernommen."))
        self.language_hint.setVisible(True)
