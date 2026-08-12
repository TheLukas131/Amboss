"""Auswahl der Kategorien und ihrer Zielordner.

Wird an zwei Stellen gebraucht - beim erstmaligen Einrichten und später in den
Einstellungen -, deshalb als eigenständiges Widget.

Eine Kategorie gilt als vorhanden, wenn sie angehakt ist UND ein Zielordner
eingetragen wurde. Das Häkchen ist dabei nur die sichtbare Form dessen, was
intern ohnehin gilt: kein Ordner, keine Kategorie. Ohne Häkchen wäre der Zustand
"Feld leer gelassen" von "Kategorie gibt es bei mir nicht" nicht zu unterscheiden.
"""

from pathlib import Path
from typing import Callable, Dict, Optional

from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, CheckBox, LineEdit, PushButton

from i18n import tr
from models import NAS_CATEGORIES

CATEGORY_HINTS = {
    "Anime": "Serien im Anime-Stil",
    "Anime Filme": "Filme im Anime-Stil - weglassen, wenn nicht getrennt geführt",
    "Filme": "Spielfilme",
    "Serien": "Realserien",
}

# Gebräuchliche Ordnernamen je Kategorie, für die automatische Zuordnung.
FOLDER_ALIASES = {
    "Anime": ["anime", "animes", "anime series", "anime serien"],
    "Anime Filme": ["anime filme", "anime movies", "animefilme", "anime films"],
    "Filme": ["filme", "movies", "film", "spielfilme", "kinofilme"],
    "Serien": ["serien", "tv shows", "shows", "tv", "series", "tvshows", "tv-serien"],
}


class CategoryFolderEditor(QWidget):
    """Pro Kategorie eine Zeile: Häkchen, Zielordner, Durchsuchen."""

    def __init__(self, on_changed: Optional[Callable[[], None]] = None, parent=None):
        super().__init__(parent)
        self._on_changed = on_changed or (lambda: None)
        self._checks: Dict[str, CheckBox] = {}
        self._fields: Dict[str, LineEdit] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        for category in NAS_CATEGORIES:
            layout.addLayout(self._build_row(category))

    def _build_row(self, category: str) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(3)

        row = QHBoxLayout()
        row.setSpacing(8)

        check = CheckBox(tr(category))
        check.setMinimumWidth(150)
        check.toggled.connect(lambda on, c=category: self._on_toggled(c, on))
        row.addWidget(check)

        field = LineEdit()
        field.setPlaceholderText(tr("Zielordner wählen..."))
        field.setEnabled(False)
        field.editingFinished.connect(self._on_changed)
        row.addWidget(field, 1)

        browse = PushButton(tr("Durchsuchen"))
        browse.setEnabled(False)
        browse.clicked.connect(lambda _c=False, c=category: self._browse(c))
        row.addWidget(browse)

        col.addLayout(row)
        hint = CaptionLabel(tr(CATEGORY_HINTS.get(category, "")))
        hint.setContentsMargins(158, 0, 0, 0)
        col.addWidget(hint)

        self._checks[category] = check
        self._fields[category] = field
        check._browse_button = browse  # zum Mit-Ausgrauen
        return col

    def _on_toggled(self, category: str, enabled: bool):
        self._fields[category].setEnabled(enabled)
        self._checks[category]._browse_button.setEnabled(enabled)
        if not enabled:
            self._fields[category].clear()
        self._on_changed()

    def _browse(self, category: str):
        current = self._fields[category].text().strip()
        folder = QFileDialog.getExistingDirectory(
            self, tr("Zielordner für {category}").format(category=tr(category)), current)
        if folder:
            self._fields[category].setText(folder.replace("/", "\\"))
            self._on_changed()

    # =========================================================================
    # Werte
    # =========================================================================

    def values(self) -> Dict[str, str]:
        """Kategorie -> Zielordner. Nicht angehakte Kategorien liefern einen
        leeren Eintrag; genau daran erkennt der Rest der Anwendung, dass es sie
        nicht gibt."""
        return {
            category: (self._fields[category].text().strip() if self._checks[category].isChecked() else "")
            for category in NAS_CATEGORIES
        }

    def set_values(self, folders: Dict[str, str]):
        for category in NAS_CATEGORIES:
            path = ((folders or {}).get(category) or "").strip()
            self._checks[category].setChecked(bool(path))
            self._fields[category].setText(path)
            self._fields[category].setEnabled(bool(path))
            self._checks[category]._browse_button.setEnabled(bool(path))

    def active_count(self) -> int:
        return sum(1 for v in self.values().values() if v)

    def incomplete(self) -> list:
        """Kategorien, die angehakt sind, aber keinen Ordner haben.

        Dieser Zustand ist nicht dasselbe wie "nicht benutzt": der Nutzer hat
        gesagt, dass es die Kategorie gibt, nur das Wohin fehlt noch. Ohne
        Rueckmeldung wuerde sie stillschweigend unter den Tisch fallen."""
        return [c for c, check in self._checks.items()
                if check.isChecked() and not self._fields[c].text().strip()]

    def detect_from_folder(self, root: str) -> Dict[str, str]:
        """Ordnet Unterordner eines Medienverzeichnisses den Kategorien zu und
        trägt sie ein. Gibt die Treffer zurück."""
        found: Dict[str, str] = {}
        try:
            existing = {p.name.lower(): p for p in Path(root).iterdir() if p.is_dir()}
        except OSError:
            return found

        for category, names in FOLDER_ALIASES.items():
            for name in names:
                if name in existing:
                    found[category] = str(existing[name]).replace("/", "\\")
                    break

        if found:
            merged = self.values()
            merged.update(found)
            self.set_values(merged)
            self._on_changed()
        return found
