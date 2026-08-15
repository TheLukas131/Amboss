"""Zweisprachigkeit der Oberfläche (Deutsch/Englisch).

Der Schlüssel im Wörterbuch ist der deutsche Originaltext. Dadurch bleibt der
Quellcode ohne Nachschlagen lesbar (`tr("Konvertierung")` statt `tr("k_convert")`),
und fehlt eine Übersetzung, erscheint schlicht der deutsche Text statt eines
kryptischen Platzhalters.

Die Sprache wird einmal beim Start festgelegt. Ein Wechsel wirkt erst nach einem
Neustart - die Alternative wäre, sämtliche Seiten und Dialoge zur Laufzeit neu
aufzubauen, was den Nutzen nicht rechtfertigt.

Platzhalter in Texten sind benannt (`{count}`), nicht positionell, damit die
Wortstellung in der Übersetzung frei gewählt werden kann.
"""

import locale
from typing import Dict

_LANGUAGE = "de"

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "en": {
        # --- Navigation und Seitentitel ---
        "Konvertierung": "Conversion",
        "Details": "Details",
        "Protokoll": "Log",
        "NAS-Upload": "Library upload",
        "Einstellungen": "Settings",
        "Konvertiert Videos nach AV1, H.265 & H.264 über NVIDIA NVENC":
            "Converts video to AV1, H.265 and H.264 using NVIDIA NVENC",

        # --- Quelle/Ziel ---
        "QUELLORDNER": "SOURCE FOLDER",
        "ZIELORDNER": "OUTPUT FOLDER",
        "Durchsuchen": "Browse",
        "Ordner hierher ziehen oder durchsuchen...": "Drop a folder here or browse...",
        "Standard: 'Converted' im Quellverzeichnis": "Default: 'Converted' inside the source folder",
        "Noch nicht gescannt": "Not scanned yet",
        "Noch nichts konvertiert": "Nothing converted yet",
        "{count} Dateien · {size}": "{count} files · {size}",
        "{count} konvertiert · {size}": "{count} converted · {size}",
        "Quellordner auswählen": "Select source folder",
        "Zielordner auswählen": "Select output folder",

        # --- Encoding ---
        "CODEC": "CODEC",
        "PRESET": "PRESET",
        "QUALITÄT": "QUALITY",
        "Erweitert": "Advanced",
        "CQ {value}/{max} · {description}": "CQ {value}/{max} · {description}",
        "Getrennte Presets (Anime/Realfilm)": "Separate presets (animation / live action)",
        "Zeichentrick komprimiert oft spürbar anders als Realfilm - mit eigenen "
        "CQ/Preset/Codec-Werten je nach erkanntem Medientyp statt einem globalen Wert für alles.":
            "Animation often compresses noticeably differently from live action. Use separate "
            "CQ, preset and codec values per detected media type instead of one setting for everything.",
        "Getrennte Presets aktiv - die Werte oben werden ignoriert, siehe 'Erweitert'.":
            "Separate presets are active — the values above are ignored, see 'Advanced'.",
        "Parallele Tasks:": "Parallel tasks:",
        "R128 Audio-Normalisierung": "R128 audio normalisation",
        "Automatisches Umbenennen": "Rename automatically",
        "Quelle nach Konvertierung löschen": "Delete source after conversion",
        "Anime": "Animation",
        "Serie/Film": "Series / movie",

        # --- Warteschlange ---
        "Warteschlange": "Queue",
        "Warteschlange · {count} Dateien": "Queue · {count} files",
        "Warteschlange · {count} Dateien · {skipped} übersprungen":
            "Queue · {count} files · {skipped} skipped",
        "Alle": "All",
        "Wartend": "Waiting",
        "In Arbeit": "Running",
        "Fertig": "Done",
        "Fehler": "Failed",
        "Dateien scannen": "Scan files",
        "Liste leeren": "Clear list",
        "Dateiname": "File name",
        "Typ": "Type",
        "Status": "Status",
        "Fortschritt": "Progress",
        "Ziel": "Target",
        "Aus der Warteschlange entfernen": "Remove from queue",

        # --- Statistik und Steuerung ---
        "Gesamt: {count}": "Total: {count}",
        "Erfolgreich: {count}": "Succeeded: {count}",
        "Fehler: {count}": "Failed: {count}",
        "Vorher: {size}": "Before: {size}",
        "Nachher: {size}": "After: {size}",
        "Ersparnis: {value}": "Saved: {value}",
        "Vorher: -": "Before: —",
        "Nachher: -": "After: —",
        "Ersparnis: -": "Saved: —",
        "läuft noch...": "still running…",
        "Verbleibend: {time}": "Remaining: {time}",
        "Verbleibend: --:--:--": "Remaining: --:--:--",
        "Verbleibend: Berechne...": "Remaining: calculating…",
        "Nach Abschluss:": "When finished:",
        "Nichts weiter tun": "Do nothing",
        "Auf NAS verschieben": "Move to library",
        "PC herunterfahren": "Shut down PC",
        "Auf NAS verschieben, dann herunterfahren": "Move to library, then shut down",
        "Der NAS-Anteil wird gespeichert, das Herunterfahren nicht - nach einem "
        "Neustart der App ist 'herunterfahren' immer wieder aus.":
            "The library step is remembered, the shutdown is not — after restarting the "
            "application, 'shut down' is always off again.",
        "Konvertierung starten": "Start conversion",
        "Pause": "Pause",
        "Fortsetzen": "Resume",
        "Stoppen": "Stop",
        "{done}/{total} bereit": "{done}/{total} ready",
        "In Bearbeitung ({done}/{total})": "Running ({done}/{total})",
        "Fertig ({done}/{total})": "Finished ({done}/{total})",

        # --- Bibliothek / Upload ---
        "Medien in die Mediathek verschieben": "Move media to your library",
        "Verschiebe konvertierte Serien und Filme in deine Mediathek. "
        "Die Kategorie stammt direkt aus der beim Konvertieren erzeugten Ordnerstruktur.":
            "Move converted series and movies into your library. The category comes straight "
            "from the folder structure created during conversion.",
        "Converted-Ordner:": "Converted folder:",
        "Ordner mit konvertierten Medien auswählen...": "Select the folder with converted media...",
        "Aktualisieren": "Refresh",
        "Ziele prüfen": "Check targets",
        "Zielordner ändern": "Change target folders",
        "Nicht geprüft": "Not checked",
        "Nichts eingestellt": "Nothing configured",
        "{count} Ziele erreichbar": "{count} targets reachable",
        "{count} nicht erreichbar": "{count} unreachable",
        "Noch keine Zielordner eingestellt - unter Einstellungen festlegen, "
        "wohin die einzelnen Kategorien sollen.":
            "No target folders configured yet — set where each category should go under Settings.",
        "Ziele:": "Targets:",
        "Name": "Name",
        "Zielordner": "Target folder",
        "Größe": "Size",
        "Alle auswählen": "Select all",
        "Keine auswählen": "Select none",
        "Lokale Ordner nach dem Verschieben löschen": "Delete local folders after moving",
        "Fortschritt:": "Progress:",
        "Ausgewählte verschieben": "Move selected",
        "Alle verschieben": "Move all",
        "Keine Medien gefunden": "No media found",
        "{count} Medien gefunden | Gesamt: {size}": "{count} items found | total: {size}",

        # --- Details ---
        "Klicken Sie auf einen Eintrag, um Details anzuzeigen": "Select an entry to see its details",
        "Datei": "File",
        "Original": "Original",
        "Neu": "New",
        "Ersparnis": "Saved",
        "Originalgröße: -": "Original size: —",
        "Neue Größe: -": "New size: —",
        "Gesamtersparnis: -": "Total saved: —",

        # --- Protokoll ---
        "Leeren": "Clear",
        "Speichern": "Save",
        "{count} ältere Einträge laden ({remaining} weitere verfügbar)":
            "Load {count} older entries ({remaining} more available)",
        "Log speichern": "Save log",
        "Textdateien (*.txt)": "Text files (*.txt)",

        # --- Einstellungen ---
        "Design, Sprache und wohin die fertigen Dateien gehören.":
            "Appearance, language, and where finished files go.",
        "Darstellung": "Appearance",
        "Design": "Theme",
        "Sprache": "Language",
        "System": "System",
        "Hell": "Light",
        "Dunkel": "Dark",
        "Automatisch (Systemsprache)": "Automatic (system language)",
        "Mediathek": "Library",
        "Lege fest, wohin fertige Dateien verschoben werden. Was du leer lässt, "
        "gilt als nicht vorhanden - erkannte Dateien landen dann in der "
        "nächstpassenden Kategorie. Wer keine Anime-Filme getrennt führt, "
        "lässt diese Zeile einfach leer.":
            "Define where finished files are moved to. Anything you leave empty counts as "
            "not existing — detected files then go to the closest matching category. If you "
            "don't keep animated movies separately, just leave that row blank.",
        "nicht benutzt": "not used",
        "Kategorie nicht benutzen": "Don't use this category",
        "Aus einem Medienordner erkennen": "Detect from a library folder",
        "Wähle den Ordner, in dem deine Mediathek liegt. Vorhandene "
        "Unterordner werden den passenden Kategorien zugeordnet.":
            "Pick the folder your library lives in. Existing subfolders are matched to categories.",
        "Medienordner auswählen": "Select library folder",
        "Zielordner für {category}": "Target folder for {category}",
        "Zugeordnet: {list}": "Matched: {list}",
        "Keine bekannten Ordnernamen gefunden - bitte von Hand auswählen.":
            "No familiar folder names found — please pick them manually.",
        "Die Sprache wird beim nächsten Start der Anwendung übernommen.":
            "The language will be applied the next time the application starts.",
        "Serien im Anime-Stil, z.B. \\\\NAS\\Medien\\Anime":
            "Animated series, e.g. \\\\NAS\\Media\\Anime",
        "Filme im Anime-Stil - leer lassen, wenn nicht getrennt geführt":
            "Animated movies — leave empty if you don't keep them separately",
        "Spielfilme, z.B. \\\\NAS\\Medien\\Movies": "Feature films, e.g. \\\\NAS\\Media\\Movies",
        "Realserien, z.B. \\\\NAS\\Medien\\TV Shows": "Live-action series, e.g. \\\\NAS\\Media\\TV Shows",

        # --- Systemanzeige ---
        "SYSTEM": "SYSTEM",
        "Keine NVIDIA-GPU erkannt": "No NVIDIA GPU detected",

        # Verständliche Fehlermeldungen
        "Diese Tonspur passt nicht in MP4 (z.B. TrueHD oder DTS-HD MA). "
        "Mit MKV als Container bleibt sie erhalten.":
            "This audio track does not fit in MP4 (TrueHD or DTS-HD MA, for "
            "example). Choosing MKV as the container keeps it.",
        "Die Grafikkarte unterstützt diese Kombination nicht - bei AV1 "
        "meist ein Video mit 4:4:4-Farbabtastung.":
            "The graphics card does not support this combination — with AV1 "
            "that usually means a video with 4:4:4 chroma.",
        "Kein Speicherplatz mehr auf dem Ziellaufwerk.":
            "No space left on the target drive.",
        "Kein Schreibzugriff auf den Zielordner.":
            "No write access to the target folder.",
        "Unbekannter Fehler": "Unknown error",

        # Ausgabe-Container
        "Container:": "Container:",
        "MP4 - überall abspielbar (Standard)": "MP4 - plays everywhere (default)",
        "MKV - behält verlustfreien Ton und Bild-Untertitel":
            "MKV - keeps lossless audio and image subtitles",

        # Änderungsverlauf im Programm
        "Über Amboss": "About Amboss",
        "Änderungsverlauf": "Changelog",
        "Schließen": "Close",
        "Der Änderungsverlauf konnte nicht gelesen werden.":
            "The changelog could not be read.",

        # Scannen im Hintergrund
        "{done} von {total}": "{done} of {total}",
        "Scannt...": "Scanning...",
        "Scannt... {done} von {total}": "Scanning... {done} of {total}",
        "Scan fehlgeschlagen": "Scan failed",
        "Der Ordner konnte nicht gelesen werden:\n\n{error}":
            "The folder could not be read:\n\n{error}",
        "Dateien suchen": "Looking for files",
        "Mediathek lesen": "Reading library",
        "Videodaten lesen": "Reading video details",

        # FFmpeg nachladen
        "Amboss benötigt FFmpeg zum Konvertieren, auf diesem Rechner ist es "
        "aber nicht installiert.\n\n"
        "Amboss kann es jetzt herunterladen ({size}) und in seinem eigenen "
        "Ordner ablegen:\n{target}\n\n"
        "Quelle: {source}, die offiziellen Windows-Builds von FFmpeg. Am "
        "System wird nichts verändert; zum Entfernen genügt es, den Ordner "
        "zu löschen.":
            "Amboss requires FFmpeg to convert video, and it is not installed "
            "on this computer.\n\n"
            "Amboss can download it now ({size}) and keep it in its own "
            "folder:\n{target}\n\n"
            "Source: {source}, the official Windows builds of FFmpeg. Nothing "
            "on the system is modified; deleting that folder removes it again.",
        "FFmpeg wird geladen": "Downloading FFmpeg",
        "Herunterladen": "Download",
        "Nicht jetzt": "Not now",
        "Verbindung wird aufgebaut...": "Connecting...",
        "Wird geladen... {percent} %": "Downloading... {percent}%",
        "Quelle: {source}": "Source: {source}",
        "etwa {mb} MB": "about {mb} MB",
        "Größe unbekannt": "size unknown",
        "FFmpeg-Download fehlgeschlagen": "FFmpeg download failed",
        "FFmpeg-Download abgelehnt.": "FFmpeg download declined.",
        "FFmpeg-Download abgebrochen.": "FFmpeg download cancelled.",
        "FFmpeg eingerichtet: {path}": "FFmpeg set up: {path}",
        "Die Pruefsumme stimmt nicht - die Datei wurde verworfen.":
            "The checksum did not match; the file was discarded.",
        "Die Pruefsumme war nicht abrufbar - es wurde nichts entpackt.":
            "The checksum could not be retrieved; nothing was extracted.",
        "Das Archiv enthielt nicht die erwarteten Programme.":
            "The archive did not contain the expected programs.",
        "Die heruntergeladenen Programme liessen sich nicht starten.":
            "The downloaded programs could not be started.",
        "Der Download ist fehlgeschlagen.": "The download failed.",

        # Encoder-Ausstattung der Grafikkarte
        "Keine Grafikkarte erkannt": "No graphics card detected",
        "Deine Grafikkarte hat eine Encoder-Einheit.":
            "Your graphics card has one encoder unit.",
        "Deine Grafikkarte hat nur eine Encoder-Einheit. Mehr "
        "gleichzeitige Tasks bringen kaum noch Mehrleistung.":
            "Your graphics card has only one encoder unit. Additional "
            "concurrent tasks add very little throughput.",
        "Deine Grafikkarte hat {units} Encoder-Einheiten.":
            "Your graphics card has {units} encoder units.",
        "Deine Grafikkarte hat nur {units} Encoder-Einheiten. Mehr "
        "gleichzeitige Tasks bringen dann kaum noch Mehrleistung.":
            "Your graphics card only has {units} encoder units. Beyond that, "
            "additional concurrent tasks add very little throughput.",
        "Grafikkarte nicht unterstützt": "Graphics card not supported",
        "keine Grafikkarte erkannt": "no graphics card detected",
        "Gefunden: {found}\n\nAmboss kodiert über NVIDIA NVENC und "
        "benötigt dafür eine NVIDIA-Grafikkarte. Encoder von AMD und "
        "Intel sind derzeit nicht eingebaut.":
            "Found: {found}\n\nAmboss encodes through NVIDIA NVENC and requires "
            "an NVIDIA graphics card. AMD and Intel encoders are not currently "
            "implemented.",
        "AV1 auf dieser Grafikkarte nicht möglich":
            "AV1 not available on this graphics card",
        "{name} kann AV1 zwar abspielen, aber nicht erzeugen. Dafür "
        "wird mindestens eine GeForce RTX der 4000er-Reihe benötigt."
        "\n\nH.265 und H.264 funktionieren auf dieser Karte. H.265 "
        "erzeugt deutlich kleinere Dateien und ist die bessere Wahl, "
        "solange die Abspielgeräte es beherrschen.":
            "{name} can play AV1 back but cannot create it, which requires a "
            "GeForce RTX 4000 series card or newer.\n\nH.265 and H.264 both work "
            "on this card. H.265 produces considerably smaller files and is the "
            "better choice as long as your players support it.",

        # --- Dialoge und Meldungen ---
        "Ja": "Yes",
        "Nein": "No",
        "OK": "OK",
        "Abbrechen": "Cancel",
        "Schließen": "Close",
        "Bestätigung": "Please confirm",
        "Warnung": "Warning",
        "Keine Dateien zum Konvertieren.": "No files to convert.",
        "Bitte wählen Sie einen gültigen Quellordner.": "Please choose a valid source folder.",
        "Encoder nicht verfügbar": "Encoder unavailable",
        "Mindestens einer der gewählten Encoder ist auf diesem System nicht verfügbar. "
        "Bitte wählen Sie einen anderen Codec oder prüfen Sie Ihre GPU/Treiber.":
            "At least one of the selected encoders is not available on this system. Choose a "
            "different codec or check your GPU and drivers.",
        "Läuft noch": "Still running",
        "Beenden": "Quit",
        "Weiterlaufen lassen": "Keep running",
        "Interner Fehler": "Internal error",
        "Konvertierung abgeschlossen": "Conversion finished",
        "Konvertierung mit Fehlern abgeschlossen": "Conversion finished with errors",
        "Upload abgeschlossen": "Upload finished",
        "Upload mit Fehlern": "Upload finished with errors",
        "NAS-Upload abgeschlossen": "Library upload finished",
        "NAS-Upload mit Fehlern": "Library upload finished with errors",
        "Upload nicht möglich": "Upload not possible",
        "Keine Auswahl": "Nothing selected",
        "Keine Zielordner": "No target folders",
        "Liste leeren": "Clear list",
        "FFmpeg fehlt": "FFmpeg missing",
        # --- Nachtrag ---
        "Medien auf NAS verschieben": "Move media to your library",
        "Durchsuchen...": "Browse...",
        "Converted-Ordner auswählen": "Select converted folder",
        "Qualität vs. Dateigröße": "Quality vs. file size",
        "Geschwindigkeit": "Speed",
        "Codec (GPU/NVENC)": "Codec (GPU / NVENC)",
        "Metadaten": "Metadata",
        "unbekannt": "unknown",
        "Gesamt: 0": "Total: 0",
        "Erfolgreich: 0": "Succeeded: 0",
        "Fehler: 0": "Failed: 0",
        "Verarbeitet": "Processing",
        "Übersprungen": "Skipped",
        "Pausiert": "Paused",
        "Bereit": "Ready",
        "Wird verschoben...": "Moving...",
        "Unbekannt": "Unknown",
        "Anime Filme": "Animated movies",
        "Filme": "Movies",
        "Serien": "Series",
        "p1 - Sehr schnell (Schlechtere Kompression)": "p1 - Very fast (worse compression)",
        "p2 - Schnell": "p2 - Fast",
        "p3 - Schnell": "p3 - Fast",
        "p4 - Ausgewogen": "p4 - Balanced",
        "p5 - Ausgewogen (Standard)": "p5 - Balanced (default)",
        "p6 - Langsamer": "p6 - Slower",
        "p7 - Langsam (Beste Kompression)": "p7 - Slow (best compression)",
        "AV1 (NVENC, GPU) - Standard": "AV1 (NVENC, GPU) - default",
        "H.265 / HEVC (NVENC, GPU)": "H.265 / HEVC (NVENC, GPU)",
        "H.264 (NVENC, GPU)": "H.264 (NVENC, GPU)",
        "Sehr hohe Qualität": "Very high quality",
        "Hohe Qualität": "High quality",
        "Ausgewogen": "Balanced",
        "Kompakt": "Compact",
        "Maximale Kompression": "Maximum compression",
        "eine Konvertierung": "a conversion",
        "ein NAS-Upload": "a library upload",
        "und": "and",
        "Es läuft gerade {what}.\n\nBeim Beenden wird das abgebrochen; bereits fertige "
        "Dateien bleiben erhalten.\n\nWirklich beenden?":
            "{what} is currently running.\n\nQuitting will abort it; files already finished "
            "are kept.\n\nQuit anyway?",
        "Der angegebene Quellordner ist ungültig oder existiert nicht:\n\n{path}":
            "The source folder is invalid or does not exist:\n\n{path}",
        "Der Upload kann nicht starten:\n\n{reason}": "The upload cannot start:\n\n{reason}",
        "kein Zielordner eingestellt": "no target folder configured",
        "nicht erreichbar: {list}": "unreachable: {list}",
        "{count} Datei(en) erfolgreich konvertiert.": "{count} file(s) converted successfully.",
        "{done} erfolgreich, {failed} fehlgeschlagen. Details im Protokoll.":
            "{done} succeeded, {failed} failed. See the log for details.",
        "{count} Datei(en) konnten nicht konvertiert werden:\n\n{list}\n\n"
        "Überprüfen Sie das Protokoll für Details.":
            "{count} file(s) could not be converted:\n\n{list}\n\nSee the log for details.",
        "{count} Medium/Medien erfolgreich verschoben.": "{count} item(s) moved successfully.",
        "{count} Medium/Medien erfolgreich aufs NAS verschoben.":
            "{count} item(s) moved to your library.",
        "{count} Medium/Medien konnten nicht verschoben werden.":
            "{count} item(s) could not be moved.",
        "{done} verschoben, {failed} fehlgeschlagen. Lokale Ordner bleiben erhalten.":
            "{done} moved, {failed} failed. Local folders are kept.",
        "Bitte wählen Sie mindestens ein Medium zum Verschieben aus.":
            "Please select at least one item to move.",
        "Sie haben 'Lokale Ordner löschen' aktiviert.\n\n{count} Ordner werden nach "
        "erfolgreich verifiziertem Kopieren gelöscht.\n\nFortfahren?":
            "You enabled 'delete local folders'.\n\n{count} folder(s) will be deleted once "
            "the copy has been verified.\n\nContinue?",
        "Details im Protokoll.": "See the log for details.",
        # --- Neutrale Formulierungen statt NAS/Medienserver ---
        "Mediathek einsortieren": "File into library",
        "In die Mediathek verschieben": "Move into library",
        "In die Mediathek verschieben, dann herunterfahren": "Move into library, then shut down",
        "Das Verschieben wird gespeichert, das Herunterfahren nicht - nach einem "
        "Neustart der App ist 'herunterfahren' immer wieder aus.":
            "The move step is remembered, the shutdown is not — after restarting the "
            "application, 'shut down' is always off again.",
        "Fertige Medien einsortieren": "File finished media",
        "ein Verschiebevorgang": "a move",
        "Verschieben mit Fehlern": "Move finished with errors",
        "Verschieben abgeschlossen": "Move finished",
        "{count} Medium/Medien in die Mediathek verschoben.": "{count} item(s) moved into your library.",
        "Automatisches Einsortieren ist aktiv": "Automatic filing is enabled",
        "Nach der Konvertierung werden diese Dateien in die Mediathek verschoben - "
        "die Kategorie bestimmt den Zielordner. Bitte kurz prüfen, ob alles stimmt "
        "(z.B. Anime-Filme werden manchmal als normale Filme erkannt).\n"
        "Die Auswahl gilt jeweils für alle Folgen des Titels.":
            "After conversion these files are moved into your library — the category "
            "determines the target folder. Please check that everything is right "
            "(animated movies are sometimes detected as regular ones).\n"
            "Each choice applies to every episode of that title.",
        "Titel": "Title",
        "Dateien": "Files",
        "Kategorie": "Category",
        "1 Datei": "1 file",
        "{count} Dateien": "{count} files",
        "Bestätigen und starten": "Confirm and start",
        "Serien im Anime-Stil": "Animated series",
        "Filme im Anime-Stil - leer lassen, wenn nicht getrennt geführt":
            "Animated movies — leave empty if you don't keep them separately",
        "Spielfilme": "Feature films",
        "Realserien": "Live-action series",
        "Ordner mit fertigen Dateien:": "Folder with finished files:",
        # --- Einrichtung beim ersten Start ---
        "Willkommen bei Amboss": "Welcome to Amboss",
        "Einmalige Einrichtung. Alles lässt sich später unter Einstellungen ändern.":
            "One-time setup. Everything can be changed later under Settings.",
        "Was hast du in deiner Mediathek?": "What does your library contain?",
        "Hake an, was du führst, und wähle den zugehörigen Ordner. Was du weglässt, "
        "gibt es für Amboss nicht - entsprechende Dateien werden dann der "
        "nächstpassenden Kategorie zugeordnet. Ohne jeden Ordner wird nur konvertiert "
        "und nichts verschoben; auch das ist in Ordnung.":
            "Tick what you keep and pick the matching folder. Anything you leave out does "
            "not exist as far as Amboss is concerned - those files are filed under the "
            "closest category instead. With no folders at all, files are only converted "
            "and never moved, which is a perfectly valid way to use it.",
        "Los geht's": "Get started",
        "Zielordner wählen...": "Choose target folder...",
        # --- Restliche Dialoge und Meldungen ---
        "Originalgröße: {size}": "Original size: {size}",
        "Neue Größe: {size}": "New size: {size}",
        "Gesamtersparnis: {percent}% ({size})": "Total saved: {percent}% ({size})",
        "Auflösung": "Resolution",
        "Dauer": "Duration",
        "Video-Codec": "Video codec",
        "Audio-Codec": "Audio codec",
        "Video-Bitrate": "Video bitrate",
        "Audio-Bitrate": "Audio bitrate",
        "Nachher: läuft noch...": "After: still running...",
        "Ersparnis: läuft noch...": "Saved: still running...",
        "{count} ältere Einträge laden ({remaining} weitere verfügbar)":
            "Load {count} older entries ({remaining} more available)",
        "Es ist noch kein Zielordner hinterlegt.\n\nUnter Einstellungen kannst du je Kategorie "
        "festlegen, wohin die fertigen Dateien verschoben werden.":
            "No target folder has been configured yet.\n\nUnder Settings you can define where "
            "finished files go for each category.",
        "Diese Ordner sind gerade nicht erreichbar:\n\n{list}\n\nLiegen sie auf einem "
        "Netzlaufwerk? Stimmen die Pfade? Bestehen die Zugriffsrechte?":
            "These folders are currently unreachable:\n\n{list}\n\nAre they on a network "
            "share? Are the paths correct? Do you have access rights?",
        "Zielordner nicht erreichbar": "Target folder unreachable",
        "Bitte wählen Sie einen gültigen Converted-Ordner aus.":
            "Please choose a valid folder containing converted media.",
        "FFmpeg wurde nicht gefunden.\n\nBitte installieren Sie FFmpeg und stellen Sie sicher, "
        "dass es im System-PATH verfügbar ist.":
            "FFmpeg was not found.\n\nPlease install FFmpeg and make sure it is available on "
            "your system PATH.",
        "Die Liste kann nicht geleert werden, während eine Konvertierung läuft.":
            "The list cannot be cleared while a conversion is running.",
        "Es wurden {count} Dateien verarbeitet.\n\nMöchten Sie die Liste wirklich leeren?":
            "{count} file(s) have been processed.\n\nDo you really want to clear the list?",
        "Bitte wählen Sie einen gültigen Quellordner.\n\nHinweis: Ziehen Sie einen Ordner auf "
        "das 'Quelle:'-Feld oder klicken Sie auf 'Durchsuchen...' neben dem Quelle-Feld.":
            "Please choose a valid source folder.\n\nTip: drag a folder onto the source field, "
            "or use the Browse button next to it.",
        "Sie haben 'Quelle nach Konvertierung löschen' aktiviert.\n\nQuelldateien werden nur "
        "nach nachweislich erfolgreicher Konvertierung gelöscht.\n\nFortfahren?":
            "You enabled 'delete source after conversion'.\n\nSource files are removed only "
            "after the conversion has been verified as successful.\n\nContinue?",
        "{count} Datei(en) fertig konvertiert. {savings}": "{count} file(s) converted. {savings}",
        # Zusammenfuehren-Dialog
        "Mögliche Namens-Duplikate": "Possible duplicate names",
        "Es wurden Ordnernamen gefunden, bei denen einer exakt der Anfang eines anderen ist - "
        "ein typisches Zeichen für einen beim Download abgeschnittenen Namen (z.B. durch das "
        "Windows-Zeichenlimit). Wähle pro Vorschlag, ob zusammengeführt werden soll. Die bereits "
        "konvertierten Dateien sind davon unabhängig - dies betrifft nur die Ordnerstruktur.":
            "Folder names were found where one is exactly the beginning of another - a typical "
            "sign of a name truncated during download (for instance by the Windows path length "
            "limit). Decide for each suggestion whether to merge. Already converted files are "
            "unaffected; this only concerns the folder structure.",
        "'{shorter}' ({shorter_count} Dateien) und '{longer}' ({longer_count} Dateien) scheinen "
        "dieselbe Serie zu sein.\nZusammenführen zu '{longer}'?":
            "'{shorter}' ({shorter_count} files) and '{longer}' ({longer_count} files) appear to "
            "be the same series.\nMerge into '{longer}'?",
        "Ja, zusammenführen": "Yes, merge",
        "Zusammengeführt zu '{name}'": "Merged into '{name}'",
        "Fehler beim Zusammenführen: {error}": "Error while merging: {error}",
        "(Nicht zusammengeführt)": "(not merged)",
        # Herunterfahren
        "Der PC fährt in {seconds} Sekunden herunter.\nZum Abbrechen auf 'Abbrechen' klicken.":
            "The PC will shut down in {seconds} seconds.\nClick 'Cancel' to stop it.",
        # Markenhinweis
        "AV1™ ist eine Marke der Alliance for Open Media. Diese Anwendung setzt die "
        "AV1-Spezifikation um; sie steht in keiner Verbindung zur Alliance for Open Media "
        "und wird von ihr nicht unterstützt oder zertifiziert.":
            "AV1™ is a trademark of the Alliance for Open Media. This application implements "
            "the AV1 specification; it is not affiliated with, endorsed by, or certified by "
            "the Alliance for Open Media.",
        "1 Kategorie eingerichtet.": "1 category configured.",
        "Bitte einen Ordner wählen für: {list}": "Please choose a folder for: {list}",
        "Zielordner fehlt": "Target folder missing",
        "Für {list} ist noch kein Ordner gewählt.\n\nBitte einen Ordner angeben "
        "oder das Häkchen entfernen, wenn du diese Kategorie nicht führst.":
            "No folder has been chosen for {list}.\n\nPlease pick a folder, or clear the "
            "checkbox if you don't keep that category.",
        "{count} Kategorien eingerichtet.": "{count} categories configured.",
        "Keine Kategorie eingerichtet - Amboss konvertiert dann nur und verschiebt nichts.":
            "No categories configured - Amboss will only convert and never move anything.",
        "Serien im Anime-Stil": "Animated series",
        "Filme im Anime-Stil - weglassen, wenn nicht getrennt geführt":
            "Animated movies - leave out if you don't keep them separately",
    }
}


def detect_system_language() -> str:
    """Deutsch, wenn Windows deutsch ist - sonst Englisch."""
    try:
        code = locale.getdefaultlocale()[0] or ""
    except (ValueError, TypeError):
        code = ""
    return "de" if code.lower().startswith("de") else "en"


def set_language(value: str) -> str:
    """Legt die Sprache fest. 'auto' folgt der Systemsprache. Gibt die
    tatsächlich gesetzte Sprache zurück."""
    global _LANGUAGE
    _LANGUAGE = detect_system_language() if value in (None, "", "auto") else value
    if _LANGUAGE not in ("de", "en"):
        _LANGUAGE = "en"
    return _LANGUAGE


def current_language() -> str:
    return _LANGUAGE


def tr(text: str) -> str:
    """Übersetzt einen deutschen Originaltext. Fehlt die Übersetzung, bleibt der
    Originaltext stehen - lieber deutsch als leer."""
    if _LANGUAGE == "de":
        return text
    return TRANSLATIONS.get(_LANGUAGE, {}).get(text, text)
