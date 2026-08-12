"""Marke der Anwendung ganz oben in der Seitenleiste."""

from pathlib import Path

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, NavigationWidget, StrongBodyLabel

BRAND_HEIGHT = 62
AV1_TRADEMARK_NOTE = (
    "AV1™ ist eine Marke der Alliance for Open Media. Diese Anwendung setzt die "
    "AV1-Spezifikation um; sie steht in keiner Verbindung zur Alliance for Open Media "
    "und wird von ihr nicht unterstützt oder zertifiziert."
)


class BrandWidget(NavigationWidget):
    """Symbol und Name der Anwendung ganz oben in der Seitenleiste."""

    def __init__(self, icon_path: Path, name: str, version: str, parent=None):
        super().__init__(isSelectable=False, parent=parent)
        self.setFixedSize(40, BRAND_HEIGHT)

        self._content = QWidget(self)
        row = QHBoxLayout(self._content)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(10)

        icon = QIcon(str(icon_path))
        if not icon.isNull():
            logo = QLabel()
            logo.setPixmap(icon.pixmap(30, 30))
            row.addWidget(logo)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        text_col.addWidget(StrongBodyLabel(name))
        text_col.addWidget(CaptionLabel(f"v{version}"))
        row.addLayout(text_col)
        row.addStretch()

        self._content.setVisible(False)

    def setCompacted(self, isCompacted: bool):
        """Wie beim GPU-Panel: die Basisklasse würde auf 36px Höhe zwingen."""
        self.isCompacted = isCompacted
        if isCompacted:
            self.setFixedSize(40, 0)
        else:
            self.setFixedSize(self.EXPAND_WIDTH, BRAND_HEIGHT)
        self._content.setVisible(not isCompacted)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._content.setGeometry(0, 0, self.width(), self.height())
