"""Wiederverwendbare Custom-Widgets für die Hauptoberfläche, aufbauend auf qfluentwidgets."""

import os

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QDragEnterEvent, QDropEvent
from PyQt5.QtWidgets import QVBoxLayout, QWidget
from i18n import tr
from qfluentwidgets import (
    ComboBox, LineEdit, PushButton, SingleDirectionScrollArea, SpinBox, isDarkTheme, qconfig,
)
from qfluentwidgets.components.navigation.pivot import Pivot, PivotItem

# Fluent-Standardhöhe für Eingabe-/Schaltflächen. Wird als Mindesthöhe erzwungen,
# damit ein Layout sie nie unter die Texthöhe zusammenstauchen und dadurch die
# Beschriftung abschneiden kann.
CONTROL_MIN_HEIGHT = 33


def enforce_control_heights(root: QWidget, min_height: int = CONTROL_MIN_HEIGHT):
    """Setzt für alle Eingabe-Steuerelemente unterhalb von `root` eine Mindesthöhe.

    Ohne das darf Qt sie bei Platzmangel beliebig flach quetschen - dann ragt der
    Text oben aus dem Widget heraus (abgeschnittene Buchstaben).

    Pivot/SegmentedWidget sind ausgenommen: deren Einträge sind zwar technisch
    PushButtons, ihre Höhe gehört aber dem Pivot selbst - der zeichnet Auswahl-Pille
    und Indikator relativ zu Item- bzw. Widget-Höhe. Eine von außen erzwungene
    Item-Höhe bringt beides auseinander."""
    for widget_type in (LineEdit, PushButton, ComboBox, SpinBox):
        for widget in root.findChildren(widget_type):
            if isinstance(widget, PivotItem) or isinstance(widget.parent(), Pivot):
                continue
            widget.setMinimumHeight(min_height)


def surface_color() -> str:
    """Flächenfarbe des Inhaltsbereichs, passend zum aktuellen Design."""
    return "#272727" if isDarkTheme() else "#f9f9f9"


# Rundung oben links am Inhaltsbereich, wie sie qfluentwidgets in
# fluent_window.qss fuer StackedWidget setzt.
CONTENT_CORNER_RADIUS = 10

# Flaeche der Seitenleiste - eine Spur abgesetzt vom Inhaltsbereich, damit die
# Trennung ohne Trennlinie erkennbar bleibt.
SIDEBAR_DARK = "#1f1f1f"
SIDEBAR_LIGHT = "#f0f0f0"


def apply_surface_background(widget: QWidget):
    """Gibt einem Widget eine deckende Fläche und hält sie beim Designwechsel aktuell.

    Deckend statt durchsichtig aus zwei Gründen: beim Seitenwechsel verschiebt
    qfluentwidgets die ganze Seite, und bei durchsichtigem Hintergrund muss Qt für
    jedes Zwischenbild alles darunter neu zeichnen - bei großen Fenstern bricht die
    Animation dadurch auf die Hälfte ein. Und optisch bleibt es einheitlich, statt
    dass mal der Fensterhintergrund durchscheint und mal nicht."""
    widget.setAttribute(Qt.WA_StyledBackground, True)
    if not widget.objectName():
        widget.setObjectName(f"surface{id(widget)}")

    def refresh():
        widget.setStyleSheet(
            f"#{widget.objectName()} {{"
            f" background-color: {surface_color()};"
            # Muss die Rundung des Inhaltsbereichs mitmachen (fluent_window.qss:
            # border-top-left-radius: 10px). Sonst deckt die eckige Flaeche die
            # runde Ecke zu und beim Verschieben waehrend der Animation blitzt
            # sie kurz wieder auf - mal rund, mal eckig.
            f" border-top-left-radius: {CONTENT_CORNER_RADIUS}px;"
            f" }}")

    refresh()
    qconfig.themeChanged.connect(refresh)
    widget._surface_refresh = refresh  # Referenz halten, sonst wird sie eingesammelt


class ScrollablePage(QWidget):
    """Seite, deren Inhalt bei zu kleinem Fenster scrollt statt zusammengequetscht
    zu werden.

    Qt verteilt bei Platzmangel weniger als die Mindesthöhe an die Kind-Widgets,
    wodurch sich Beschriftungen und Felder überlappen und Text abgeschnitten wird.
    Mit `setWidgetResizable(True)` bekommt der Inhalt bei genug Platz weiterhin die
    volle Fläche (Tabellen mit Stretch wachsen also normal mit), bei zu wenig Platz
    behält er aber seine natürliche Größe und die Seite wird scrollbar.
    """

    def __init__(self, object_name: str, parent=None):
        super().__init__(parent)
        self.setObjectName(object_name)
        apply_surface_background(self)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.scroll_area = SingleDirectionScrollArea(orient=Qt.Vertical)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        outer.addWidget(self.scroll_area)

        self.content = QWidget()
        self.content.setStyleSheet("QWidget { background: transparent; }")
        self.scroll_area.setWidget(self.content)

        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(20, 20, 20, 20)
        self.content_layout.setSpacing(14)


class DragDropLineEdit(LineEdit):
    """Fluent-LineEdit mit Drag & Drop Unterstützung für Ordner."""

    path_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setReadOnly(True)
        self.setPlaceholderText(tr("Ordner hierher ziehen oder durchsuchen..."))

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if not urls:
            return

        path = os.path.normpath(urls[0].toLocalFile().strip())

        if os.path.isdir(path):
            self.setText(path)
            self.path_dropped.emit(path)
        elif os.path.isfile(path):
            folder = os.path.dirname(path)
            self.setText(folder)
            self.path_dropped.emit(folder)
