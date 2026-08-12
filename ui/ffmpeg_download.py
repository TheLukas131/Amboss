"""Rueckfrage und Fortschrittsanzeige fuer den FFmpeg-Download.

Bewusst zweistufig: erst wird gefragt, was von wo geladen wird und wie gross es
ist, und erst nach Zustimmung geht etwas ueber die Leitung. Ein Programm, das
ungefragt Dateien aus dem Netz holt, ist genau das, was man nicht will.
"""

from PyQt5.QtCore import QThread, pyqtSignal
from qfluentwidgets import BodyLabel, CaptionLabel, ProgressBar, TitleLabel

import ffmpeg_setup
from i18n import tr
from ui.dialog_base import FittedMessageBox


class _DownloadThread(QThread):
    """Laedt FFmpeg abseits des Oberflaechen-Threads."""

    progress = pyqtSignal(int)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            ffmpeg_path, _ = ffmpeg_setup.fetch_ffmpeg(
                progress=self.progress.emit,
                cancelled=lambda: self._cancelled)
            self.finished_ok.emit(str(ffmpeg_path))
        except ffmpeg_setup.DownloadCancelled:
            self.failed.emit("")
        except ffmpeg_setup.DownloadFailed as error:
            self.failed.emit(str(error))
        except Exception as error:  # Netzwerk und Dateisystem sind unberechenbar
            self.failed.emit(str(error))


_REASONS = {
    "checksum_mismatch": "Die Pruefsumme stimmt nicht - die Datei wurde verworfen.",
    "checksum_unavailable": "Die Pruefsumme war nicht abrufbar - es wurde nichts entpackt.",
    "incomplete_archive": "Das Archiv enthielt nicht die erwarteten Programme.",
    "not_executable": "Die heruntergeladenen Programme liessen sich nicht starten.",
}


def describe_failure(reason: str) -> str:
    return tr(_REASONS.get(reason, "Der Download ist fehlgeschlagen."))


class _AskDialog(FittedMessageBox):
    """Rueckfrage vor dem Download - nennt Groesse, Ziel und Herkunft."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.widget.setMinimumWidth(560)

        size = ffmpeg_setup.download_size_bytes()
        size_text = (tr("etwa {mb} MB").format(mb=round(size / 1048576))
                     if size else tr("Größe unbekannt"))

        self.viewLayout.addWidget(TitleLabel(tr("FFmpeg fehlt")))
        body = BodyLabel(tr(
            "Amboss benötigt FFmpeg zum Konvertieren, auf diesem Rechner ist es "
            "aber nicht installiert.\n\n"
            "Amboss kann es jetzt herunterladen ({size}) und in seinem eigenen "
            "Ordner ablegen:\n{target}\n\n"
            "Quelle: {source}, die offiziellen Windows-Builds von FFmpeg. Am "
            "System wird nichts verändert; zum Entfernen genügt es, den Ordner "
            "zu löschen.").format(size=size_text, target=ffmpeg_setup.install_dir(),
                                  source=ffmpeg_setup.SOURCE_NAME))
        body.setWordWrap(True)
        self.viewLayout.addWidget(body)

        self.yesButton.setText(tr("Herunterladen"))
        self.cancelButton.setText(tr("Nicht jetzt"))


def ask_to_download(parent) -> bool:
    """Fragt, ob FFmpeg geholt werden darf. Nennt Quelle, Ziel und Groesse."""
    return bool(_AskDialog(parent).exec())


class FFmpegDownloadDialog(FittedMessageBox):
    """Zeigt den Fortschritt und laesst sich abbrechen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.widget.setMinimumWidth(480)

        self.viewLayout.addWidget(TitleLabel(tr("FFmpeg wird geladen")))

        self.status = BodyLabel(tr("Verbindung wird aufgebaut..."))
        self.viewLayout.addWidget(self.status)

        self.bar = ProgressBar()
        self.bar.setValue(0)
        self.viewLayout.addWidget(self.bar)

        self.detail = CaptionLabel(
            tr("Quelle: {source}").format(source=ffmpeg_setup.SOURCE_NAME))
        self.viewLayout.addWidget(self.detail)

        self.yesButton.setVisible(False)
        self.cancelButton.setText(tr("Abbrechen"))

        self.result_path = None
        self.error = None

        self.thread = _DownloadThread(self)
        self.thread.progress.connect(self._on_progress)
        self.thread.finished_ok.connect(self._on_done)
        self.thread.failed.connect(self._on_failed)
        self.cancelButton.clicked.connect(self.thread.cancel)

    def exec(self):
        self.thread.start()
        return super().exec()

    def _on_progress(self, percent: int):
        self.bar.setValue(percent)
        self.status.setText(tr("Wird geladen... {percent} %").format(percent=percent))

    def _on_done(self, path: str):
        self.result_path = path
        self.accept()

    def _on_failed(self, reason: str):
        self.error = reason
        self.reject()
