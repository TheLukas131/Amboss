"""Kopiert eine Datei in die Mediathek - geprüft, abbrechbar, mit Fortschritt.

Drei Dinge, die ein einfaches shutil.copy2 nicht leistet:

*Geprüft.* Nach dem Kopieren wird die Kopie Byte für Byte mit der Quelle
verglichen, und zwar bevor sie ihren endgültigen Namen bekommt. Eine Kopie, die
abweicht, hat in der Mediathek nie unter dem richtigen Namen gelegen. Vorher
wurde nur die Dateigrösse verglichen - eine Datei mit vertauschtem Inhalt
gleicher Länge wäre durchgegangen, und danach wird der lokale Ordner gelöscht.

*Abbrechbar.* Kopiert wird in Blöcken, zwischen denen nachgefragt wird, ob
abgebrochen werden soll. Vorher lief eine angefangene Datei immer zu Ende -
bei einem Film über ein langsames Netzlaufwerk hiess "Stoppen" dann: in zwanzig
Minuten.

*Mit Fortschritt.* Jeder Block wird gemeldet. Vorher bewegte sich die Anzeige
nur zwischen zwei Dateien, und während eines grossen Films stand sie still.

Der Preis der Prüfung: jede Datei wird ein zweites Mal vom Ziel gelesen. Über
ein Netzlaufwerk dauert ein Transfer damit ungefähr doppelt so lang.

Eine Grenze, die sich von hier aus nicht aufheben lässt: gelesen wird, was das
Betriebssystem für den Inhalt der Zieldatei hält. Vor dem Vergleich werden die
Daten ausdrücklich zum Server geschrieben (fsync), aber ob Windows das
Zurücklesen aus dem Netz oder aus seinem eigenen Zwischenspeicher bedient,
entscheidet Windows. Abgebrochene, gekürzte und beim Schreiben verfälschte
Kopien fallen auf; ein Datenträger im NAS, der richtig Empfangenes falsch
ablegt, nicht in jedem Fall.
"""

import os
import shutil
from pathlib import Path
from typing import Callable, Optional

# Endung der Zwischendatei beim Verschieben in die Mediathek. Sie wird an den
# vollen Dateinamen angehängt und macht die Datei eindeutig wiedererkennbar -
# nach einem Absturz muss sie sich aufräumen lassen, ohne dass eine echte
# Mediendatei in Gefahr gerät.
TRANSFER_TEMP_SUFFIX = ".amboss-tmp"

# Blockgrösse. Gross genug, dass über SMB nicht jede Anfrage einzeln zählt,
# klein genug, dass ein Abbruch und die Anzeige nicht lange auf sich warten
# lassen: bei 100 MB/s ist ein Block in unter einer Zehntelsekunde durch.
CHUNK_SIZE = 8 * 1024 * 1024

COPYING = "copy"
VERIFYING = "verify"


class TransferCancelled(Exception):
    """Der Nutzer hat den Transfer abgebrochen."""


class VerificationFailed(OSError):
    """Die Kopie stimmt nicht mit der Quelle überein."""


def _read_full(datei, puffer: memoryview) -> int:
    """Füllt den Puffer, so weit die Datei reicht.

    Ein einzelnes readinto darf weniger liefern als verlangt, ohne dass die
    Datei zu Ende ist - über ein Netzlaufwerk kommt das vor. Beim Vergleich
    zweier Dateien würden die Blöcke dann gegeneinander verrutschen."""
    gelesen = 0
    while gelesen < len(puffer):
        n = datei.readinto(puffer[gelesen:])
        if not n:
            break
        gelesen += n
    return gelesen


def _copy(quelle: Path, ziel: Path, melde, abgebrochen) -> None:
    puffer = memoryview(bytearray(CHUNK_SIZE))
    with open(quelle, "rb", buffering=0) as src, open(ziel, "wb", buffering=0) as dst:
        while True:
            if abgebrochen():
                raise TransferCancelled()
            n = _read_full(src, puffer)
            if not n:
                break
            dst.write(puffer[:n])
            melde(COPYING, n)
        # Ausdrücklich zum Datenträger bzw. Server schicken, bevor verglichen
        # wird - sonst vergliche die Prüfung unter Umständen nur, was noch im
        # Zwischenspeicher des eigenen Rechners liegt.
        os.fsync(dst.fileno())


def _compare(quelle: Path, kopie: Path, melde, abgebrochen) -> None:
    # Verglichen werden die bytearrays, nicht die memoryviews darauf: zwei
    # bytearrays vergleicht Python in einem Zug (gemessen 12 GB/s), zwei
    # memoryviews Element für Element (430 MB/s) - langsamer als ein schnelles
    # Netzlaufwerk liefert, die Prüfung hätte den Transfer selbst gebremst.
    block_a, block_b = bytearray(CHUNK_SIZE), bytearray(CHUNK_SIZE)
    a, b = memoryview(block_a), memoryview(block_b)
    position = 0
    with open(quelle, "rb", buffering=0) as src, open(kopie, "rb", buffering=0) as dst:
        while True:
            if abgebrochen():
                raise TransferCancelled()
            n = _read_full(src, a)
            m = _read_full(dst, b)
            if n == m == len(block_a):
                gleich = block_a == block_b
            else:
                # Der letzte, angebrochene Block: nur so weit vergleichen, wie
                # gelesen wurde - dahinter steht noch der Block davor.
                gleich = n == m and block_a[:n] == block_b[:m]
            if not gleich:
                raise VerificationFailed(
                    f"Kopie weicht von der Quelle ab: {quelle.name} "
                    f"(ab Byte {position:,})"
                )
            if not n:
                return
            position += n
            melde(VERIFYING, n)


def copy_verified(quelle: Path, ziel: Path,
                  on_progress: Optional[Callable[[str, int], None]] = None,
                  cancelled: Optional[Callable[[], bool]] = None) -> None:
    """Kopiert `quelle` nach `ziel`, ohne dass dort je eine halbe oder
    ungeprüfte Datei mit dem endgültigen Namen liegt.

    Erst unter Zwischennamen ins selbe Verzeichnis, dann vergleichen, dann
    umbenennen: os.replace ist auf demselben Datenträger eine einzige Operation
    des Dateisystems, auch über SMB. Der Name zeigt entweder auf die alte Datei
    oder auf die neue, geprüfte - nie auf etwas dazwischen. Lag dort vorher eine
    ältere Fassung, bleibt sie unberührt, bis die neue nachweislich stimmt.

    `on_progress(abschnitt, bytes)` wird je Block gerufen, einmal beim Kopieren
    (COPYING) und einmal beim Vergleichen (VERIFYING) - eine Datei meldet also
    insgesamt das Doppelte ihrer Grösse. `cancelled()` wird zwischen den Blöcken
    befragt; bei True bricht der Vorgang mit TransferCancelled ab und räumt die
    Zwischendatei weg.

    Wirft VerificationFailed, wenn die Kopie abweicht, und OSError bei allem,
    was das Dateisystem meldet."""
    melde = on_progress or (lambda _abschnitt, _anzahl: None)
    abgebrochen = cancelled or (lambda: False)
    zwischen = ziel.with_name(ziel.name + TRANSFER_TEMP_SUFFIX)
    try:
        # Ein Überbleibsel eines abgebrochenen Laufs würde sonst verwechselt.
        if zwischen.exists():
            zwischen.unlink()
        _copy(quelle, zwischen, melde, abgebrochen)
        # Änderungszeit und Attribute übernehmen, wie shutil.copy2 es tat -
        # Medienserver sortieren "zuletzt hinzugefügt" unter anderem danach.
        shutil.copystat(quelle, zwischen)
        _compare(quelle, zwischen, melde, abgebrochen)
        zwischen.replace(ziel)
    except BaseException:
        # Auch bei Abbruch von aussen nichts Halbfertiges zurücklassen. Der
        # Fehler selbst wird weitergereicht, das Aufräumen darf ihn nicht
        # verdecken.
        try:
            if zwischen.exists():
                zwischen.unlink()
        except OSError:
            pass
        raise
