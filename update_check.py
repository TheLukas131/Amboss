"""Fragt bei GitHub nach, ob es neuere Fassungen von Amboss gibt.

Bewusst nur nachfragen, nicht handeln: Amboss laedt keine neue Fassung
herunter und tauscht sich erst recht nicht selbst aus. Gefunden wird, was
neuer ist als die laufende Fassung, gemeldet wird es, und der Weg zur Datei
ist ein Verweis auf die Projektseite - der Nutzer entscheidet selbst, wann und
ob er wechselt.

Der Grund ist nicht Bequemlichkeit, sondern Vertrauen: eine laufende
Amboss.exe laesst sich unter Windows nicht ueberschreiben, ein Selbstaustausch
muesste also beim naechsten Start passieren - genau das Verhalten, das
Virenscanner an unsignierten Programmen als Schadsoftware behandeln. Ein
Werkzeug, das Quelldateien loescht, sollte vorhersagbar sein.

Gemeldet wird nicht nur die neueste Fassung, sondern jede uebersprungene: wer
von 1.2.3 auf 1.4.0 geht, hat auch 1.2.4 und 1.3.0 nie gesehen, und genau
darin steht womoeglich die Behebung des Fehlers, der ihn stoert.

Uebertragen wird dabei nichts ausser der Anfrage selbst: ein GET auf einen
oeffentlichen Endpunkt, ohne Anmeldung, ohne Kennung, ohne Nutzungsdaten.
"""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

REPOSITORY = "TheLukas131/Amboss"
API_URL = f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=30"
RELEASES_PAGE = f"https://github.com/{REPOSITORY}/releases/latest"

# GitHub weist Anfragen ohne User-Agent mit 403 ab. Der Name ist frei waehlbar;
# die API verlangt lediglich, dass ueberhaupt einer gesetzt ist.
_USER_AGENT = "Amboss-Update-Check"

# Kurz gehalten: die Pruefung laeuft beim Start nebenher, und ein Server, der
# nicht antwortet, darf nicht dazu fuehren, dass ein Thread minutenlang haengt.
_TIMEOUT = 8.0


@dataclass
class Release:
    """Eine veroeffentlichte Fassung, so wie GitHub sie meldet."""
    version: str        # ohne fuehrendes "v", also "1.3.0"
    page_url: str       # Seite mit den Dateien zum Herunterladen
    notes: str          # Text der Veroeffentlichung, ggf. leer


@dataclass
class UpdateInfo:
    """Alles, was seit der laufenden Fassung erschienen ist.

    `releases` ist absteigend sortiert, die neueste zuerst; `newest` ist
    dieselbe noch einmal einzeln, weil der Weg zum Herunterladen immer dorthin
    fuehrt - auch wenn darunter noch drei aeltere Eintraege stehen."""
    newest: Release
    releases: List[Release] = field(default_factory=list)

    @property
    def version(self) -> str:
        return self.newest.version

    @property
    def page_url(self) -> str:
        return self.newest.page_url


def parse_version(text: str) -> Optional[Tuple[int, ...]]:
    """Macht aus "v1.2.3" die Zahlenfolge (1, 2, 3).

    Alles, was nicht rein aus Zahlen und Punkten besteht, gilt als unbrauchbar
    und fuehrt zu None - lieber keine Meldung als eine falsche."""
    if not text:
        return None
    teile = text.strip().lstrip("vV").split(".")
    try:
        return tuple(int(teil) for teil in teile)
    except ValueError:
        return None


def _aufgefuellt(links: Tuple[int, ...], rechts: Tuple[int, ...]):
    """Gleicht die Laenge zweier Versionsangaben mit Nullen an, damit "1.3" und
    "1.3.0" gleich zaehlen."""
    laenge = max(len(links), len(rechts))
    return links + (0,) * (laenge - len(links)), rechts + (0,) * (laenge - len(rechts))


def is_newer(candidate: str, current: str) -> bool:
    """Ob `candidate` eine hoehere Version ist als `current`."""
    neu, alt = parse_version(candidate), parse_version(current)
    if neu is None or alt is None:
        return False
    neu, alt = _aufgefuellt(neu, alt)
    return neu > alt


def _releases(timeout: float = _TIMEOUT) -> Optional[List[Release]]:
    """Holt die veroeffentlichten Fassungen. None, wenn das nicht gelingt.

    Jeder Fehlschlag - kein Netz, Zeitueberschreitung, unerwartete Antwort -
    ist hier kein Fehler, sondern schlicht "nichts zu melden". Eine
    Update-Pruefung, die den Start mit Fehlermeldungen stoert, waere schlimmer
    als gar keine.

    Entwuerfe und Vorabfassungen bleiben aussen vor: was noch nicht fertig
    veroeffentlicht ist, soll auch niemanden zum Wechseln auffordern."""
    request = urllib.request.Request(
        API_URL,
        headers={"User-Agent": _USER_AGENT,
                 "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            daten = json.loads(response.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None

    if not isinstance(daten, list):
        return None

    gefunden = []
    for eintrag in daten:
        if not isinstance(eintrag, dict) or eintrag.get("draft") or eintrag.get("prerelease"):
            continue
        version = (eintrag.get("tag_name") or "").strip().lstrip("vV")
        if not parse_version(version):
            continue
        gefunden.append(Release(
            version=version,
            page_url=(eintrag.get("html_url") or RELEASES_PAGE).strip(),
            notes=(eintrag.get("body") or "").strip(),
        ))
    return gefunden


def latest_release(timeout: float = _TIMEOUT) -> Optional[Release]:
    """Die neueste veroeffentlichte Fassung, oder None."""
    gefunden = _releases(timeout=timeout)
    if not gefunden:
        return None
    return max(gefunden, key=lambda r: parse_version(r.version))


def find_update(current_version: str, skipped_version: str = "",
                timeout: float = _TIMEOUT) -> Optional[UpdateInfo]:
    """Gibt zurueck, was seit `current_version` erschienen ist - oder None.

    `skipped_version` ist die Fassung, die der Nutzer ausdruecklich nicht mehr
    gemeldet bekommen wollte. Erscheint spaeter eine noch neuere, wird die
    wieder gemeldet: abgelehnt wurde eine bestimmte Fassung, nicht die
    Pruefung an sich."""
    gefunden = _releases(timeout=timeout)
    if not gefunden:
        return None

    neuere = [r for r in gefunden if is_newer(r.version, current_version)]
    if not neuere:
        return None

    neuere.sort(key=lambda r: parse_version(r.version), reverse=True)
    if skipped_version and neuere[0].version == skipped_version.strip().lstrip("vV"):
        return None

    return UpdateInfo(newest=neuere[0], releases=neuere)
