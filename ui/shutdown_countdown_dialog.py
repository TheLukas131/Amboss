"""Countdown-Dialog vor dem automatischen Herunterfahren nach Abschluss einer
Konvertierung. Der eigentliche Shutdown läuft über Windows' eigenen verzögerten
`shutdown /s /t N` - so bleibt er auch bestehen, falls diese App währenddessen
beendet wird; Abbrechen ruft `shutdown /a` auf, um genau das rückgängig zu machen.

Erbt von MessageBoxBase statt einem nackten QDialog - nur so bekommt der Dialog
den zum aktuellen Theme passenden Hintergrund."""

import subprocess

from PyQt5.QtCore import QTimer
from qfluentwidgets import BodyLabel, TitleLabel
from i18n import tr
from ui.dialog_base import FittedMessageBox

SHUTDOWN_DELAY_SECONDS = 60
_CREATIONFLAGS = subprocess.CREATE_NO_WINDOW


class ShutdownCountdownDialog(FittedMessageBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._remaining = SHUTDOWN_DELAY_SECONDS

        self.viewLayout.addWidget(TitleLabel(tr("Konvertierung abgeschlossen")))
        self.label = BodyLabel("")
        self.label.setWordWrap(True)
        self.viewLayout.addWidget(self.label)

        self.cancelButton.setText(tr("Abbrechen"))
        self.cancelButton.clicked.connect(self._on_cancel_clicked)
        self.hideYesButton()

        self._update_label()
        subprocess.run(
            ["shutdown", "/s", "/t", str(SHUTDOWN_DELAY_SECONDS)],
            capture_output=True, creationflags=_CREATIONFLAGS,
        )

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

    def _update_label(self):
        self.label.setText(tr(
            "Der PC fährt in {seconds} Sekunden herunter.\nZum Abbrechen auf 'Abbrechen' klicken."
        ).format(seconds=self._remaining))

    def _tick(self):
        self._remaining -= 1
        if self._remaining <= 0:
            self._timer.stop()
            self.accept()
            return
        self._update_label()

    def _on_cancel_clicked(self):
        """Läuft zusätzlich zum eingebauten Cancel-Button-Handler von
        MessageBoxBase (der ruft bereits reject() auf) - hier nur der
        eigentliche Seiteneffekt, den geplanten Shutdown abzubrechen."""
        subprocess.run(["shutdown", "/a"], capture_output=True, creationflags=_CREATIONFLAGS)
        self._timer.stop()
