"""Gemeinsame Basis für alle eigenen Dialoge.

qfluentwidgets' MaskDialogBase legt seine Größe einmal im Konstruktor fest
(`setGeometry(0, 0, parent.width(), parent.height())`). Wird das Hauptfenster
danach noch größer - etwa weil es beim Start maximiert wird und das erst nach
dem Erzeugen des Dialogs greift -, bleibt die abdunkelnde Fläche auf der alten
Größe stehen und deckt nur einen Teil des Fensters ab.

Diese Basisklasse zieht die Geometrie beim Anzeigen nach und hält sie
anschließend an der Größe des Elternfensters.
"""

from PyQt5.QtCore import QEvent
from qfluentwidgets import MessageBoxBase


class FittedMessageBox(MessageBoxBase):
    """MessageBoxBase, dessen Abdunkelung immer das ganze Elternfenster bedeckt."""

    def __init__(self, parent=None):
        super().__init__(parent)
        if parent is not None:
            parent.installEventFilter(self)

    def _fit_to_parent(self):
        parent = self.parent()
        if parent is not None:
            self.setGeometry(0, 0, parent.width(), parent.height())

    def showEvent(self, event):
        self._fit_to_parent()
        super().showEvent(event)

    def eventFilter(self, obj, event):
        # Auch mitwachsen, wenn das Fenster bei offenem Dialog seine Größe ändert
        # (Maximieren per Tastenkürzel, Bildschirmwechsel, DPI-Änderung).
        if obj is self.parent() and event.type() == QEvent.Resize and self.isVisible():
            self._fit_to_parent()
        return super().eventFilter(obj, event)
