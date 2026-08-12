"""Theme-Zuordnung für die Anwendung.

Die eigentliche Hell/Dunkel/Mica-Darstellung übernimmt qfluentwidgets selbst
(setTheme/qconfig) - dieses Modul bildet nur unsere persistierte "theme"-Einstellung
(system/light/dark) auf qfluentwidgets' Theme-Enum ab und liefert ein paar
semantische Farben für Python-seitige QColor-Verwendung (Tabellen-Status-Text),
die außerhalb von Stylesheets liegt und sich daher nicht automatisch mitfärbt.
"""

import sys

from qfluentwidgets import Theme, isDarkTheme

THEME_OPTIONS = [("system", "System"), ("light", "Hell"), ("dark", "Dunkel")]

_LIGHT_SEMANTIC = {
    "success": "#0F7B0F",
    "error": "#C42B1C",
    "warning": "#9D5D00",
    "accent": "#0067C0",
    "neutral": "#5F5F5F",
}

_DARK_SEMANTIC = {
    "success": "#6CCB5F",
    "error": "#FF8B82",
    "warning": "#FCE100",
    "accent": "#60CDFF",
    "neutral": "#C5C5C5",
}

_QFLUENT_THEME = {"system": Theme.AUTO, "light": Theme.LIGHT, "dark": Theme.DARK}


def to_qfluent_theme(mode: str) -> Theme:
    return _QFLUENT_THEME.get(mode, Theme.AUTO)


def detect_system_theme() -> str:
    """Nur für Anzeige-/Diagnosezwecke - qfluentwidgets' Theme.AUTO macht die
    eigentliche Erkennung (inkl. Live-Reaktion auf Windows-Theme-Wechsel) selbst."""
    if sys.platform != "win32":
        return "dark"
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "light" if value == 1 else "dark"
    except OSError:
        return "dark"


def semantic_colors() -> dict:
    """Aktuell passende semantische Farben (success/error/warning/accent/neutral)."""
    return _DARK_SEMANTIC if isDarkTheme() else _LIGHT_SEMANTIC
