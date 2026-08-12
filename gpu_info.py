"""Erkennt die verbaute Grafikkarte und ihre Encoder-Ausstattung.

Zwei Dinge sind hier zu unterscheiden, die leicht verwechselt werden:

*Kann die Karte AV1 erzeugen?* haengt an der Generation. AV1-Encoding gibt es
bei GeForce erst ab der RTX-4000-Reihe. Aeltere Karten spielen AV1 zwar ab,
erzeugen es aber nicht - der haeufigste Irrtum bei diesem Thema.

*Wie viele Encoder-Einheiten hat sie?* bestimmt, wie viele Konvertierungen
gleichzeitig sinnvoll sind. Diese Zahl meldet **keine** Schnittstelle: weder
nvidia-smi noch NVML kennen einen Zaehler dafuer (NVML liefert nur einen
Prozentwert der freien Kapazitaet). Sie stammt deshalb aus der Tabelle unten,
nachgeschlagen bei NVIDIA. Bei unbekannten Karten wird bewusst nicht geraten.

Wichtig: H.264, H.265 und AV1 teilen sich dieselben Einheiten. Die Kernzahl
gilt also unabhaengig vom gewaehlten Codec.
"""

import re
import subprocess
from dataclasses import dataclass
from typing import List, Optional

# Encoder-Einheiten je Modell.
#
# Reihenfolge ist bedeutsam - der erste Treffer gewinnt. Deshalb stehen die
# laengeren Namen oben: sonst wuerde "4070 Ti SUPER" schon bei "4070 Ti"
# haengenbleiben, und die beiden unterscheiden sich tatsaechlich (die SUPER
# basiert auf AD103 mit zwei Einheiten, die normale Ti auf AD104 mit einer).
#
# Unsicher ist einzig die RTX 4070 Ti: NVIDIAs karten-genaue Support-Matrix
# nennt zwei Einheiten, andere Quellen eine. Hier steht zwei, weil das die
# Angabe des Herstellers ist. Ein Irrtum waere folgenlos - die Zahl steuert nur
# einen Hinweistext, keine Begrenzung.
_NVENC_UNITS_DESKTOP = [
    # Blackwell - RTX 50
    ("5090", 3), ("5080", 2), ("5070 ti", 2), ("5070", 1),
    ("5060 ti", 1), ("5060", 1), ("5050", 1),
    # Ada Lovelace - RTX 40
    ("4090", 2), ("4080 super", 2), ("4080", 2),
    ("4070 ti super", 2), ("4070 ti", 2), ("4070 super", 1), ("4070", 1),
    ("4060 ti", 1), ("4060", 1),
]

# Laptop-Ableger sind nicht mit ihren Desktop-Namensvettern gleichzusetzen:
# die RTX 5070 Ti Laptop hat eine Einheit, die Desktop-Version zwei.
_NVENC_UNITS_LAPTOP = [
    ("5090", 3), ("5080", 2), ("5070 ti", 1), ("5070", 1),
    ("5060", 1), ("5050", 1),
    ("4090", 2), ("4080", 2), ("4070", 1), ("4060", 1), ("4050", 1),
]

# Ab dieser Modellreihe beherrscht GeForce AV1-Encoding.
_FIRST_AV1_SERIES = 40

_VIRTUAL_ADAPTERS = ("parsec", "virtual", "basic display", "basic render",
                     "remote display", "meta ", "citrix", "vmware", "oray")


@dataclass
class GpuInfo:
    """Was ueber die Grafikkarte bekannt ist."""

    name: str                      # Modellbezeichnung, wie der Treiber sie meldet
    vendor: str                    # "nvidia", "amd", "intel" oder "unbekannt"
    supports_av1: bool             # kann AV1 *erzeugen*, nicht nur abspielen
    encoder_units: Optional[int]   # None = unbekanntes Modell, nicht geraten

    @property
    def is_supported(self) -> bool:
        """Ob Amboss auf dieser Karte ueberhaupt arbeiten kann."""
        return self.vendor == "nvidia"


def short_gpu_name(name: str) -> str:
    """Kürzt den Treibernamen auf das, was die Karte ausmacht.

    'NVIDIA GeForce RTX 5090' -> 'RTX 5090'. In der schmalen Seitenleiste ist
    für den vollen Namen kein Platz; der Hersteller ergibt sich ohnehin."""
    shortened = re.sub(r"^\s*(NVIDIA|AMD|Intel)\s+", "", name.strip(), flags=re.IGNORECASE)
    shortened = re.sub(r"^\s*(GeForce|Radeon)\s+", "", shortened, flags=re.IGNORECASE)
    shortened = re.sub(r"\s+Laptop GPU$", "", shortened, flags=re.IGNORECASE)
    return shortened or name.strip()


def _series_number(name: str) -> Optional[int]:
    """Zieht die Modellreihe aus einem Namen: 'GeForce RTX 4070 Ti' -> 40."""
    match = re.search(r"\b(?:RTX|GTX)\s*(\d{4})\b", name, re.IGNORECASE)
    return int(match.group(1)) // 100 if match else None


def _encoder_units_for(name: str) -> Optional[int]:
    lowered = name.lower()
    table = _NVENC_UNITS_LAPTOP if "laptop" in lowered else _NVENC_UNITS_DESKTOP
    for model, units in table:
        if model in lowered:
            return units
    return None


def _vendor_of(name: str) -> str:
    lowered = name.lower()
    if "nvidia" in lowered or "geforce" in lowered or "quadro" in lowered:
        return "nvidia"
    if "amd" in lowered or "radeon" in lowered:
        return "amd"
    if "intel" in lowered or "arc" in lowered:
        return "intel"
    return "unbekannt"


def _run(command: List[str], timeout: float = 6.0) -> Optional[str]:
    """Fuehrt ein Kommando ohne sichtbares Konsolenfenster aus."""
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def _nvidia_gpu_name() -> Optional[str]:
    """Fragt den NVIDIA-Treiber direkt - schnell und eindeutig, wenn vorhanden."""
    output = _run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
    if not output:
        return None
    names = [line.strip() for line in output.splitlines() if line.strip()]
    return names[0] if names else None


def _installed_display_adapters() -> List[str]:
    """Listet alle Anzeigeadapter - der Weg, der auch ohne NVIDIA-Treiber traegt.

    Wird nur benutzt, wenn nvidia-smi nichts liefert; die Abfrage kostet rund
    eine viertel Sekunde und soll den Start nicht unnoetig aufhalten."""
    output = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                   "Get-CimInstance Win32_VideoController | "
                   "Select-Object -ExpandProperty Name"])
    if not output:
        return []
    adapters = [line.strip() for line in output.splitlines() if line.strip()]
    # Virtuelle Adapter (Streaming, Fernwartung) sind keine echten Karten und
    # wuerden die Meldung sonst mit "Parsec Virtual Display Adapter" fuellen.
    real = [a for a in adapters
            if not any(marker in a.lower() for marker in _VIRTUAL_ADAPTERS)]
    return real or adapters


def detect_gpu() -> GpuInfo:
    """Ermittelt die Grafikkarte. Faellt nie mit einer Ausnahme aus."""
    name = _nvidia_gpu_name()

    if not name:
        adapters = _installed_display_adapters()
        # Falls doch eine NVIDIA dabei ist (Treiber ohne nvidia-smi), diese nehmen.
        for adapter in adapters:
            if _vendor_of(adapter) == "nvidia":
                name = adapter
                break
        else:
            if not adapters:
                return GpuInfo("", "unbekannt", False, None)
            name = adapters[0]

    vendor = _vendor_of(name)
    series = _series_number(name)
    supports_av1 = (vendor == "nvidia" and series is not None
                    and series >= _FIRST_AV1_SERIES)
    units = _encoder_units_for(name) if vendor == "nvidia" else None

    # Bekannte NVIDIA-Karte ohne Tabelleneintrag: aeltere Reihen haben
    # durchgaengig genau eine Einheit, das ist keine Schaetzung.
    if units is None and vendor == "nvidia" and series is not None and series < _FIRST_AV1_SERIES:
        units = 1

    return GpuInfo(name, vendor, supports_av1, units)
