"""Dauerhaft sichtbare GPU-Anzeige am unteren Ende der Seitenleiste.

Erbt von NavigationWidget, weil NavigationInterface.addWidget() seine Kinder
u.a. per setCompacted() umschaltet - ein nacktes QWidget würde dabei mit einem
AttributeError auffliegen. Die Basisklasse zwingt Kinder normalerweise auf eine
feste Höhe von 36px; setCompacted() ist hier deshalb überschrieben, damit das
mehrzeilige Panel seine echte Höhe behalten darf."""

from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, NavigationWidget, ProgressBar

from gpu_info import short_gpu_name
from gpu_monitor import GpuStats
from i18n import tr

PANEL_HEIGHT = 168


class SystemStatsWidget(NavigationWidget):
    """Zeigt NVENC-/GPU-Auslastung, VRAM und Temperatur - die Werte, die beim
    Encodieren tatsächlich interessieren (siehe gpu_monitor.py zur Unterscheidung
    zwischen NVENC-Block und allgemeinen GPU-Kernen)."""

    def __init__(self, parent=None):
        super().__init__(isSelectable=False, parent=parent)
        self.setFixedSize(40, PANEL_HEIGHT)

        self._content = QWidget(self)
        layout = QVBoxLayout(self._content)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(6)

        # Bewusst ohne eigene Formatvorlage: setStyleSheet() ersetzt die von
        # qfluentwidgets mitgelieferte samt Themenfarbe - die Beschriftung blieb
        # dadurch im Dunkelmodus schwarz und war praktisch unsichtbar.
        self.title_label = CaptionLabel(tr("SYSTEM"))
        layout.addWidget(self.title_label)

        # Welche Karte überhaupt erkannt wurde - sonst bleibt bei jeder Meldung
        # über fehlende Unterstützung offen, was die App eigentlich gefunden hat.
        self.gpu_name_label = CaptionLabel("–")
        self.gpu_name_label.setToolTip("")
        layout.addWidget(self.gpu_name_label)

        self.nvenc_value, self.nvenc_bar = self._add_meter(layout, "NVENC")
        self.gpu_value, self.gpu_bar = self._add_meter(layout, "GPU")

        self.detail_label = CaptionLabel("–")
        layout.addWidget(self.detail_label)
        layout.addStretch()

        self._content.setVisible(False)  # bis zum ersten setCompacted(False)

    def set_gpu(self, info):
        """Trägt die erkannte Grafikkarte oben ins Panel ein."""
        if not info or not info.name:
            self.gpu_name_label.setText(tr("Keine Grafikkarte erkannt"))
            self.gpu_name_label.setToolTip("")
            return

        # In der schmalen Leiste ist kein Platz für "NVIDIA GeForce RTX 5090";
        # der volle Name steht im Tooltip.
        label = short_gpu_name(info.name)
        if info.encoder_units:
            label = f"{label} · {info.encoder_units}× NVENC"
        self.gpu_name_label.setText(label)
        self.gpu_name_label.setToolTip(info.name)

    def _add_meter(self, layout: QVBoxLayout, name: str):
        row = QHBoxLayout()
        row.setSpacing(6)
        name_label = CaptionLabel(name)
        name_label.setFixedWidth(52)
        row.addWidget(name_label)
        bar = ProgressBar()
        bar.setFixedHeight(4)
        bar.setValue(0)
        row.addWidget(bar, 1)
        value_label = CaptionLabel("–")
        value_label.setFixedWidth(38)
        value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(value_label)
        layout.addLayout(row)
        return value_label, bar

    def setCompacted(self, isCompacted: bool):
        """Basisklasse würde hier auf 36px Höhe zwingen - das Panel braucht mehr.
        In der schmalen Leiste wird stattdessen der komplette Inhalt ausgeblendet."""
        self.isCompacted = isCompacted
        if isCompacted:
            self.setFixedSize(40, 0)
        else:
            self.setFixedSize(self.EXPAND_WIDTH, PANEL_HEIGHT)
        self._content.setVisible(not isCompacted)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._content.setGeometry(0, 0, self.width(), self.height())

    def update_stats(self, stats: Optional[GpuStats]):
        if stats is None:
            self.nvenc_value.setText("–")
            self.gpu_value.setText("–")
            self.nvenc_bar.setValue(0)
            self.gpu_bar.setValue(0)
            self.detail_label.setText(tr("Keine NVIDIA-GPU erkannt"))
            return

        self.nvenc_value.setText(f"{stats.encoder_percent}%")
        self.nvenc_bar.setValue(stats.encoder_percent)
        self.gpu_value.setText(f"{stats.core_percent}%")
        self.gpu_bar.setValue(stats.core_percent)

        vram_used = stats.memory_used_mb / 1024
        vram_total = stats.memory_total_mb / 1024
        self.detail_label.setText(
            f"{vram_used:.1f}/{vram_total:.0f} GB · {stats.temperature_celsius}°C"
        )
