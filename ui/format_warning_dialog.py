"""Zeigt vor dem Start, was die gewählte Einstellung kostet.

Der Dialog erscheint nur, wenn es etwas zu melden gibt. Er nennt je Befund, wie
viele Dateien betroffen sind, was verloren geht und welche Einstellung es
behebt - und stellt auf Wunsch nur die betroffenen Dateien um, nicht die ganze
Auswahl.

Der Haken je Befund ist der Kern: bei einer Staffel mit Bild-Untertiteln und
gleichzeitig einem HDR-Film in derselben Liste sind es zwei verschiedene
Abhilfen für zwei verschiedene Gruppen. Ein einzelner "Alles umstellen"-Knopf
würde beides über einen Kamm scheren.

Die Regeln selbst stehen in format_warnings.py, ohne Qt und einzeln prüfbar.
"""

from typing import Dict, List

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel, CaptionLabel, CheckBox, SingleDirectionScrollArea,
    StrongBodyLabel, TitleLabel,
)

from format_warnings import (
    SEVERITY_FAILS, SEVERITY_LOSES, SEVERITY_UNAVOIDABLE, Finding,
)
from i18n import tr
from ui.dialog_base import FittedMessageBox
from ui.theme import semantic_colors

# So viele Dateinamen werden je Befund genannt, danach nur noch gezählt. Eine
# Staffel mit 24 Folgen soll den Dialog nicht auf Bildschirmhöhe treiben.
_MAX_NAMEN = 4


class FormatWarningDialog(FittedMessageBox):
    """Verlustvorschau mit Haken je Befund."""

    def __init__(self, findings: List[Finding], parent=None):
        super().__init__(parent)
        self.findings = findings
        self._boxes: Dict[str, CheckBox] = {}
        self.dismiss_check = None
        self.widget.setMinimumWidth(680)
        self._build()

    # =====================================================================
    # Aufbau
    # =====================================================================

    def _build(self):
        self.viewLayout.addWidget(TitleLabel(tr("Bei dieser Einstellung geht etwas verloren")))

        bricht_ab = any(f.severity == SEVERITY_FAILS for f in self.findings)
        einleitung = BodyLabel(
            tr("Für einen Teil der Dateien passt die gewählte Kombination aus Codec "
               "und Container nicht. Amboss kann die betroffenen Dateien einzeln "
               "umstellen - alles andere bleibt, wie es eingestellt ist.")
            if not bricht_ab else
            tr("Für einen Teil der Dateien passt die gewählte Kombination aus Codec "
               "und Container nicht; bei einigen würde die Konvertierung abbrechen. "
               "Amboss kann die betroffenen Dateien einzeln umstellen - alles "
               "andere bleibt, wie es eingestellt ist.")
        )
        einleitung.setWordWrap(True)
        self.viewLayout.addWidget(einleitung)

        bereich = SingleDirectionScrollArea(orient=Qt.Vertical)
        bereich.setWidgetResizable(True)
        bereich.setMaximumHeight(340)
        bereich.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        inhalt = QWidget()
        inhalt.setStyleSheet("QWidget { background: transparent; }")
        layout = QVBoxLayout(inhalt)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(4)

        for finding in self.findings:
            self._add_finding(layout, finding)

        layout.addStretch()
        bereich.setWidget(inhalt)
        self.viewLayout.addWidget(bereich, 1)

        self.dismiss_check = CheckBox(
            tr("Für diese Einstellung nicht mehr fragen"))
        self.dismiss_check.setToolTip(tr(
            "Gilt nur für die hier gezeigten Punkte und genau diese Auswahl von "
            "Codec und Container. Wählst du später etwas anderes, wird wieder "
            "gefragt."))
        self.viewLayout.addWidget(self.dismiss_check)

        self.cancelButton.setText(tr("Abbrechen"))
        self._refresh_primary_button()

    def _add_finding(self, layout: QVBoxLayout, finding: Finding):
        farben = semantic_colors()
        farbe = {
            SEVERITY_FAILS: farben["error"],
            SEVERITY_LOSES: farben["warning"],
            SEVERITY_UNAVOIDABLE: farben["neutral"],
        }.get(finding.severity, farben["neutral"])

        if layout.count():
            abstand = QWidget()
            abstand.setFixedHeight(12)
            layout.addWidget(abstand)

        anzahl = len(finding.videos)
        kopf = StrongBodyLabel(
            tr("{count} Datei(en)").format(count=anzahl)
            + ("  ·  " + tr("Konvertierung bricht ab")
               if finding.severity == SEVERITY_FAILS else "")
        )
        kopf.setStyleSheet(f"color: {farbe};")
        layout.addWidget(kopf)

        # Erst hier übersetzt: die Regeln liefern deutsche Originaltexte, damit
        # nicht die Sprache am Befund klebt, die beim Auswerten gerade galt.
        problem = BodyLabel(tr(finding.problem))
        problem.setWordWrap(True)
        layout.addWidget(problem)

        namen = [v.source_path.name for v in finding.videos[:_MAX_NAMEN]]
        if anzahl > _MAX_NAMEN:
            namen.append(tr("und {count} weitere").format(count=anzahl - _MAX_NAMEN))
        dateien = CaptionLabel("  ·  ".join(namen))
        dateien.setWordWrap(True)
        layout.addWidget(dateien)

        if finding.has_remedy:
            box = CheckBox(tr(finding.remedy))
            box.setChecked(True)
            box.stateChanged.connect(lambda _s: self._refresh_primary_button())
            self._boxes[finding.key] = box
            layout.addWidget(box)
        else:
            ohne = CaptionLabel(tr("Dafür gibt es keine Abhilfe - nur zur Kenntnis."))
            ohne.setWordWrap(True)
            layout.addWidget(ohne)

    # =====================================================================
    # Zustand
    # =====================================================================

    def _refresh_primary_button(self):
        """Der Knopf sagt, was er tut - nicht mehr und nicht weniger.

        Ohne Haken ist "Umstellen und starten" eine Lüge; dann heisst er
        "Trotzdem konvertieren", und genau das passiert auch."""
        if self.selected_findings():
            self.yesButton.setText(tr("Umstellen und starten"))
        else:
            self.yesButton.setText(tr("Trotzdem konvertieren"))

    def selected_findings(self) -> List[Finding]:
        """Die Befunde, deren Abhilfe angewendet werden soll."""
        return [f for f in self.findings
                if f.key in self._boxes and self._boxes[f.key].isChecked()]

    def dismiss_requested(self) -> bool:
        return bool(self.dismiss_check and self.dismiss_check.isChecked())
