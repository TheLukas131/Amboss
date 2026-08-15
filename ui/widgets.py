"""Wiederverwendbare Custom-Widgets für die Hauptoberfläche, aufbauend auf qfluentwidgets."""

import os

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QDragEnterEvent, QDropEvent
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QWidget
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


# Obergrenze für den Scroll-Takt. Darüber hinaus bringt es nichts Sichtbares
# mehr, kostet aber Rechenzeit - gerade bei 4K, wo jedes Bild teuer ist.
MAX_SCROLL_FPS = 240


def apply_scroll_refresh_rate(root: QWidget, screen=None):
    """Passt den Scroll-Takt an die Bildwiederholrate des Monitors an.

    qfluentwidgets fährt seine Scroll-Animation mit fest eingestellten 60
    Bildern je Sekunde. Auf einem 240-Hz-Monitor wirkt das sichtbar stockend:
    gezeichnet wird nur jedes vierte Bild, das der Schirm anzeigen könnte.
    Gemessen skaliert es sauber mit - 60 ergab 63 Schritte/s, 240 ergab 219.

    Qts *eigene* Animationen (Seitenwechsel, Ein-/Ausblenden) hängen dagegen an
    einem internen Zeitgeber mit rund 16 ms, den die öffentliche Schnittstelle
    nicht freigibt. Die bleiben also bei 60 - dagegen hilft nur ein anderes
    Oberflächen-System.
    """
    if screen is None:
        screen = QApplication.primaryScreen()
    rate = int(round(screen.refreshRate())) if screen else 60
    fps = max(60, min(rate, MAX_SCROLL_FPS))

    motoren = []
    for widget in [root] + root.findChildren(QWidget):
        # Scrollflächen tragen ihren Motor direkt, Tabellen/Listen/Bäume
        # über einen Delegaten mit je einem für waagerecht und senkrecht.
        smooth = getattr(widget, "smoothScroll", None)
        if smooth is not None:
            motoren.append(getattr(smooth, "fixedStepScrollEngine", None))
        delegat = getattr(widget, "scrollDelagate", None) or getattr(widget, "scrollDelegate", None)
        if delegat is not None:
            for richtung in ("verticalSmoothScroll", "horizonSmoothScroll"):
                teil = getattr(delegat, richtung, None)
                if teil is not None:
                    motoren.append(getattr(teil, "fixedStepScrollEngine", None))

    gesetzt = 0
    for motor in motoren:
        if motor is not None and hasattr(motor, "fps"):
            motor.fps = fps
            gesetzt += 1
    return fps, gesetzt


# Seitenwechsel: Weg und Dauer der Einblend-Bewegung.
#
# Vorher schob qfluentwidgets die Seite 76 px in 250 ms. Qt zeichnet Animationen
# mit rund 60 Schritten je Sekunde - unabhaengig vom Monitor -, das sind also gut
# 5 px je Schritt. Auf 60 Hz faellt das nicht auf, weil jedes Monitorbild einen
# neuen Stand bekommt. Auf 120 oder 240 Hz wird derselbe Stand zwei- bzw. viermal
# hintereinander gezeigt, und dann sieht man die 5-px-Spruenge als Ruckeln.
#
# Mit 20 px in 200 ms sind es 1,7 px je Schritt. Auf 60 Hz bleibt es genauso
# fluessig wie vorher, nur dezenter; darueber verschwindet das Stocken.
PAGE_SLIDE_PIXELS = 20
PAGE_SLIDE_DURATION_MS = 200


def apply_page_transition(stacked) -> int:
    """Stellt die Einblend-Bewegung aller Seiten flacher und kuerzer ein."""
    inner = getattr(stacked, "view", None) or stacked
    infos = getattr(inner, "aniInfos", None)
    if not infos:
        return 0

    angepasst = 0
    for info in infos:
        try:
            info.deltaY = PAGE_SLIDE_PIXELS
            info.ani.setDuration(PAGE_SLIDE_DURATION_MS)
            angepasst += 1
        except (AttributeError, TypeError):
            continue
    return angepasst


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
