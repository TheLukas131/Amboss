"""Laden und Speichern der Anwendungseinstellungen als JSON-Konfigurationsdatei.

Die Config liegt in %APPDATA%\\Amboss\\config.json, damit sie ein
Update/Neuinstallation des Programms übersteht. Fehlt die Datei oder ist sie
beschädigt, greifen die hart codierten Standardwerte.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict

from models import (
    DEFAULT_CODEC, DEFAULT_CONTAINER, DEFAULT_CQ, DEFAULT_PARALLEL_TASKS,
    DEFAULT_PRESET, NAS_CATEGORIES,
)

_APPDATA = Path(os.environ.get("APPDATA", str(Path.home())))
CONFIG_DIR = _APPDATA / "Amboss"
CONFIG_PATH = CONFIG_DIR / "config.json"

# Ordner aus der Zeit, als die Anwendung noch "AV1 Video Converter" hieß.
# Wird beim ersten Start einmalig übernommen, damit vorhandene Einstellungen
# (Ordnerpfade, Qualität, NAS-Ziel) eine Umbenennung überleben.
_LEGACY_CONFIG_PATH = _APPDATA / "AV1VideoConverter" / "config.json"

DEFAULTS: Dict[str, Any] = {
    "theme": "system",
    "cq": DEFAULT_CQ,
    "preset": DEFAULT_PRESET,
    "parallel_tasks": DEFAULT_PARALLEL_TASKS,
    "codec": DEFAULT_CODEC,
    "container": DEFAULT_CONTAINER,
    # Aus der Mediathek abgelesene Staffel-Benennung. Kein Nutzer stellt das
    # ein - es wird gemerkt, weil das Ablesen über ein Netzlaufwerk mehrere
    # Sekunden kostet und immer dasselbe ergibt. Wird geleert, sobald sich die
    # Kategorie-Ordner ändern.
    "detected_season_pattern": "",
    "normalize_audio": False,
    "rename_enabled": True,
    "delete_source_after_convert": False,
    "delete_local_after_nas_move": False,
    "auto_nas_upload_after_convert": False,
    "source_folder": "",
    "target_folder": "",
    # Zielordner je Kategorie, jeweils ein vollständiger Pfad. Ein leerer Eintrag
    # bedeutet: diese Kategorie gibt es in meiner Mediathek nicht. Alles Erkannte
    # wird dann auf die nächstpassende vorhandene Kategorie gefaltet
    # (siehe models.fold_to_enabled) - wer keine Anime-Filme führt, bekommt auch
    # keinen Anime-Filme-Ordner untergeschoben.
    #
    # Absichtlich einzelne Pfade statt eines gemeinsamen Wurzelordners: die
    # Ordner heißen bei jedem anders ("Movies", "Filme", "Spielfilme") und liegen
    # nicht zwingend nebeneinander.
    "category_folders": {category: "" for category in NAS_CATEGORIES},
    "language": "auto",
    # Wie Staffel-Ordner benannt werden. Leer = aus der vorhandenen Mediathek
    # ablesen (siehe library_layout.py). Jede feste Vorgabe waere eine Sprache.
    "season_folder_pattern": "",
    # "Getrennte Presets": eigene CQ/Preset/Codec je Bucket (Anime vs. Realfilm)
    # statt einem globalen Wert für alles.
    "use_separate_presets": False,
    "cq_anime": DEFAULT_CQ,
    "preset_anime": DEFAULT_PRESET,
    "codec_anime": DEFAULT_CODEC,
    "cq_realfilm": DEFAULT_CQ,
    "preset_realfilm": DEFAULT_PRESET,
    "codec_realfilm": DEFAULT_CODEC,
    # Beim Start bei GitHub nachfragen, ob es eine neuere Fassung gibt. An,
    # weil eine Fehlerbehebung nur nützt, wenn sie ankommt - abschaltbar, weil
    # ein Programm, das ungefragt ins Netz greift, das mindestens erklären und
    # zulassen muss, dass man es unterbindet.
    "check_for_updates": True,
    # Fassung, die der Nutzer nicht mehr gemeldet bekommen möchte. Eine
    # bestimmte, nicht "alle künftigen": erscheint später eine neuere, wird die
    # wieder gemeldet.
    "skipped_version": "",
}

# Absichtlich NICHT in DEFAULTS/config.json: "PC nach Abschluss herunterfahren"
# ist bewusst nicht persistiert (siehe ui/main_window.py) - der Nutzer will nie
# riskieren, dass ein vergessen aktiver Haken nach einem App-Neustart unbemerkt
# den PC herunterfährt.


class SettingsManager:
    """Hält die aktuellen Einstellungen im Speicher und synchronisiert sie mit der Config-Datei."""

    def __init__(self):
        self._values: Dict[str, Any] = dict(DEFAULTS)
        # True, wenn beim Start noch gar keine Konfiguration existierte -
        # dann zeigt die Oberflaeche den Einrichtungsdialog.
        self.is_first_run = not CONFIG_PATH.exists() and not _LEGACY_CONFIG_PATH.exists()
        self.load()

    def load(self) -> None:
        path = CONFIG_PATH
        if not path.exists():
            if not _LEGACY_CONFIG_PATH.exists():
                return
            path = _LEGACY_CONFIG_PATH  # einmalige Übernahme aus dem alten Ordner

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._values.update({k: v for k, v in data.items() if k in DEFAULTS})
                self._migrate_nas_base_path(data)
        except (json.JSONDecodeError, OSError):
            pass  # Beschädigte/unlesbare Config -> Standardwerte behalten

    def _migrate_nas_base_path(self, data: Dict[str, Any]) -> None:
        """Übernimmt die frühere Einstellung eines einzelnen NAS-Wurzelordners.

        Damals hieß der Zielordner zwingend wie die Kategorie und lag direkt
        darunter. Existiert so ein Unterordner noch, wird er als Kategorieordner
        eingetragen - sonst müsste man alles von Hand neu setzen."""
        legacy_root = (data.get("nas_base_path") or "").strip()
        folders = self._values.get("category_folders") or {}
        if not legacy_root or any(folders.values()):
            return

        root = Path(legacy_root)
        migrated = {
            category: str(root / category)
            for category in DEFAULTS["category_folders"]
            if (root / category).is_dir()
        }
        if migrated:
            self._values["category_folders"] = {
                category: migrated.get(category, "")
                for category in DEFAULTS["category_folders"]
            }

    def save(self) -> None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self._values, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def get(self, key: str) -> Any:
        return self._values.get(key, DEFAULTS.get(key))

    def set(self, key: str, value: Any) -> None:
        self._values[key] = value

    def update(self, values: Dict[str, Any]) -> None:
        self._values.update({k: v for k, v in values.items() if k in DEFAULTS})
