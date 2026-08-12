"""Liest GPU-Auslastung/Temperatur über nvidia-smi - reine Zusatzinfo für die UI,
darf die App nie blockieren oder crashen, falls keine NVIDIA-GPU/Treiber vorhanden ist.

Wichtig: NVENC läuft auf einem eigenen, von den CUDA/Shader-Kernen getrennten
Hardware-Block. `utilization.gpu` misst nur Letzteres und bleibt beim reinen
Encodieren oft niedrig (z.B. 15-20%), obwohl der Encoder selbst ausgelastet ist -
für diese App ist deshalb `utilization.encoder` die relevante Zahl."""

import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

from PyQt5.QtCore import QThread, pyqtSignal

_CREATIONFLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


@dataclass
class GpuStats:
    encoder_percent: int
    core_percent: int
    temperature_celsius: int
    memory_used_mb: int
    memory_total_mb: int
    name: str


def get_gpu_stats() -> Optional[GpuStats]:
    """Gibt aktuelle GPU-Werte zurück oder None, wenn nvidia-smi nicht verfügbar
    ist (kein NVIDIA-GPU/Treiber) - dann bleibt die Anzeige in der UI einfach leer."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.encoder,utilization.gpu,temperature.gpu,memory.used,memory.total,name",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=3, creationflags=_CREATIONFLAGS,
        )
        if result.returncode != 0:
            return None

        parts = [p.strip() for p in result.stdout.strip().split(",")]
        if len(parts) < 6:
            return None

        return GpuStats(
            encoder_percent=int(float(parts[0])),
            core_percent=int(float(parts[1])),
            temperature_celsius=int(float(parts[2])),
            memory_used_mb=int(float(parts[3])),
            memory_total_mb=int(float(parts[4])),
            name=parts[5],
        )
    except (subprocess.SubprocessError, ValueError, OSError, FileNotFoundError):
        return None


class GpuMonitorThread(QThread):
    """Fragt nvidia-smi im Hintergrund ab und meldet die Werte per Signal.

    Vorher lief die Abfrage per QTimer direkt im GUI-Thread - ein hängender
    Treiber hätte die Oberfläche bis zum Timeout (3 s) eingefroren, alle 3
    Sekunden erneut."""

    stats_ready = pyqtSignal(object)  # GpuStats oder None

    def __init__(self, interval_seconds: float = 3.0, parent=None):
        super().__init__(parent)
        self._interval = interval_seconds
        self._running = True

    def run(self):
        while self._running:
            self.stats_ready.emit(get_gpu_stats())
            # In kleinen Schritten warten, damit stop() nicht bis zu einem
            # vollen Intervall blockiert.
            waited = 0.0
            while self._running and waited < self._interval:
                self.msleep(100)
                waited += 0.1

    def stop(self):
        self._running = False
