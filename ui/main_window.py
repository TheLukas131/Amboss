"""Hauptfenster der Anwendung - Windows-11-Stil mit Seitenleisten-Navigation
(qfluentwidgets FluentWindow) statt der alten Tab-Leiste."""

import logging
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFontMetrics
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QFileDialog, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QSizePolicy, QSystemTrayIcon,
    QTableWidgetItem, QTreeWidgetItem, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    BodyLabel, CardWidget, CaptionLabel, CheckBox, ComboBox, FluentIcon,
    FluentWindow, HorizontalSeparator, InfoBar, InfoBarPosition, LineEdit,
    IndeterminateProgressRing, MessageBox, NavigationItemPosition, PillPushButton, PrimaryPushButton,
    ProgressBar, PushButton, SegmentedWidget, Slider, SpinBox, StrongBodyLabel,
    TableWidget, TitleLabel, TransparentToolButton, TreeWidget, qconfig, setTheme,
    setThemeColor,
)

import crash_logging
from duplicate_detector import filter_duplicate_downloads
from ffmpeg_processor import FFmpegProcessor
from gpu_info import detect_gpu
from gpu_monitor import GpuMonitorThread
from library_layout import (
    NUMERIC_ONLY, category_for_staging_folder, detect_season_pattern, parse_season_convention,
)
from inprogress_mover import (
    delete_redundant_duplicates, move_videos_to_inprogress, prune_empty_inprogress_dirs,
)
from merge_detector import find_truncation_candidates
from resources import resource_path
from models import (
    APP_NAME, APP_TAGLINE, APP_VERSION, ANIME_KEYWORDS, CODEC_LABELS, CONTAINERS,
    DEFAULT_CODEC, cq_maximum_for,
    CONTAINER_LABELS, DEFAULT_CONTAINER, DEFAULT_OUTPUT_FOLDER,
    FileStatus, MediaType, NAS_CATEGORIES, NASUploadItem, NASUploadStatus,
    PRESET_BUCKET_LABELS, PRESET_BUCKETS, PRESET_LABELS, PRESETS, VideoFile,
    fold_to_enabled,
    VideoMetadata, get_cq_description,
)
from path_generator import PathGenerator
from pattern_matcher import PatternMatcher
from settings_manager import SettingsManager
from ui import theme
from ui.ffmpeg_download import FFmpegDownloadDialog, ask_to_download, describe_failure
from ui.log_page import LogPage
from ui.media_type_review_dialog import MediaTypeReviewDialog
from ui.merge_review_dialog import MergeReviewDialog
from ui.brand_widgets import BrandWidget
from ui.settings_page import SettingsPage
from ui.setup_dialog import SetupDialog
from ui.shutdown_countdown_dialog import ShutdownCountdownDialog
from ui.system_stats_widget import SystemStatsWidget
from ui.widgets import (
    DragDropLineEdit, ScrollablePage, SIDEBAR_DARK, SIDEBAR_LIGHT,
    apply_page_transition, apply_scroll_refresh_rate, enforce_control_heights,
)
from workers import ConversionWorker, NASUploadWorker, ScanWorker
from i18n import tr

logger = logging.getLogger(__name__)


class MainWindow(FluentWindow):
    """Hauptfenster der Anwendung."""

    def __init__(self):
        super().__init__()
        self.settings = SettingsManager()

        self.videos: List[VideoFile] = []
        # Beim Scannen aussortierte Doppel-Downloads; gelöscht erst beim Start.
        self._redundant_duplicates: List[Path] = []
        self.worker: Optional[ConversionWorker] = None
        self.ffmpeg = FFmpegProcessor()
        self.encoder_available = True
        self.current_filter = "all"
        self.conversion_start_time: Optional[float] = None
        self.completed_files_durations: List[float] = []
        # Auflösung ("1920x1080") -> Liste gemessener Encoding-Geschwindigkeiten
        # (Video-Sekunden pro Wanduhr-Sekunde) - Basis für die Batch-ETA (siehe
        # _estimate_speed_for/_compute_batch_eta_seconds). Pro Konvertierungslauf neu.
        self._resolution_speeds: Dict[str, List[float]] = {}
        # True, wenn sowohl Auto-NAS-Upload als auch Auto-Shutdown aktiv waren -
        # der Shutdown-Countdown soll dann erst NACH dem Upload erscheinen,
        # nicht schon nach der Konvertierung selbst.
        self._shutdown_after_nas_upload = False

        self.nas_items: List[NASUploadItem] = []
        self.nas_worker: Optional[NASUploadWorker] = None
        self.scan_worker: Optional[ScanWorker] = None
        # Worker-Index -> Tabellenzeile, siehe _start_nas_upload/_nas_row_for
        self._nas_row_for_worker_idx: Dict[int, int] = {}
        # Seitenwechsel-Sperre, siehe _on_stacked_page_changed
        self._previous_page = None
        self._returning_to_settings = False
        # Einmal je Programmlauf aus der Mediathek abgelesen, siehe current_season_pattern()
        self._detected_season_pattern = None
        self.nas_categories = NAS_CATEGORIES

        # Wird erst nach vollständigem Seitenaufbau + initialem Laden der
        # Einstellungen auf True gesetzt. Verhindert, dass die während des
        # Konstruierens/Vorbelegens der Steuerelemente ausgelösten changed-Signale
        # (z.B. setMinimum/setMaximum, die den Wert klemmen) schon versuchen zu speichern.
        self._ui_ready = False

        setThemeColor("#0078D4")
        setTheme(theme.to_qfluent_theme(self.settings.get("theme")))

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1300, 860)
        self.setMinimumSize(1050, 700)
        # Kein Mica/Acryl: der durchscheinende Fensterhintergrund wirkte je nach
        # Seite unterschiedlich - mal schimmerte der Desktop durch, mal nicht, und
        # die Ecken des Inhaltsbereichs sahen von Seite zu Seite anders aus.
        # Eine durchgehend deckende Flaeche ist ruhiger und zeichnet schneller.
        try:
            self.setMicaEffectEnabled(False)
        except Exception:
            pass  # Nicht kritisch (z.B. auf Windows 10 / Nicht-Windows)

        # Vor dem Seitenaufbau: der Hinweis am Task-Zähler braucht die Angaben.
        self.gpu_info = detect_gpu()

        self._build_pages()
        self._apply_settings_to_controls()
        self._update_encoder_hint()
        self.check_ffmpeg()

        self.eta_timer = QTimer()
        self.eta_timer.timeout.connect(self.update_eta_display)

        self.system_stats_widget.set_gpu(self.gpu_info)

        self.gpu_monitor = GpuMonitorThread()
        self.gpu_monitor.stats_ready.connect(self.system_stats_widget.update_stats)
        self.gpu_monitor.start()

        # Abgefangene Ausnahmen sichtbar machen, statt sie nur in die Datei zu
        # schreiben - sonst merkt man nur, dass "irgendwas nicht passiert ist".
        crash_logging.set_error_callback(self._on_unhandled_error)

        self._setup_tray_icon()

        # Erst einrichten, dann auf fehlende Voraussetzungen hinweisen - und beides
        # erst, wenn das Fenster steht. Ein modaler Dialog aus __init__ heraus
        # erscheint sonst noch vor dem Hauptfenster und wirkt wie ein Absturz.
        if self.settings.is_first_run:
            QTimer.singleShot(0, self._run_first_time_setup)
        QTimer.singleShot(0, self._warn_about_missing_requirements)

        # Scroll-Takt an den Monitor anpassen. Muss nach dem Aufbau aller Seiten
        # passieren, sonst sind die Tabellen und Scrollflächen noch nicht da.
        takt, betroffen = apply_scroll_refresh_rate(self)
        seiten = apply_page_transition(self.stackedWidget)
        self.log(f"Scroll-Takt: {takt} Bilder/s auf {betroffen} Flächen, "
                 f"Seitenwechsel geglättet ({seiten} Seiten)")

        self._ui_ready = True

    # =========================================================================
    # Navigation / Seiten-Aufbau
    # =========================================================================

    def _build_pages(self):
        self.convert_page = self._build_convert_page()
        self.details_page = self._build_details_page()
        self.log_page = LogPage()
        self.nas_page = self._build_nas_page()
        self.settings_page = SettingsPage(self._build_theme_toggle, self._on_settings_changed)

        # Dauerhaft ausgeklappte Seitenleiste statt der schmalen Icon-Leiste -
        # nur so ist unten Platz für das GPU-Panel. setExpandWidth() setzt
        # NavigationWidget.EXPAND_WIDTH global mit, die Einträge passen sich also an.
        self.navigationInterface.setExpandWidth(240)
        self.navigationInterface.setCollapsible(False)
        self.navigationInterface.setMenuButtonVisible(False)
        self._apply_sidebar_background()
        qconfig.themeChanged.connect(self._apply_sidebar_background)

        # Muss vor den Seiten eingefügt werden: addWidget(..., TOP) hängt an das
        # Ende des oberen Bereichs an, der Markenblock landete sonst unter der
        # Navigation statt darüber.
        self.navigationInterface.addWidget(
            routeKey="brand",
            widget=BrandWidget(resource_path("icon.ico"), APP_NAME, APP_VERSION),
            position=NavigationItemPosition.TOP,
        )

        self.addSubInterface(self.convert_page, FluentIcon.VIDEO, tr("Konvertierung"))
        self.addSubInterface(self.details_page, FluentIcon.DOCUMENT, tr("Details"))
        self.addSubInterface(self.log_page, FluentIcon.HISTORY, tr("Protokoll"))
        self.addSubInterface(self.nas_page, FluentIcon.CLOUD, tr("Mediathek"))
        self.addSubInterface(self.settings_page, FluentIcon.SETTING, tr("Einstellungen"),
                             position=NavigationItemPosition.BOTTOM)

        self.system_stats_widget = SystemStatsWidget()
        self.navigationInterface.addWidget(
            routeKey="systemStats", widget=self.system_stats_widget,
            position=NavigationItemPosition.BOTTOM,
        )

        self.stackedWidget.currentChanged.connect(self._on_stacked_page_changed)

    def switchTo(self, interface):
        """Seitenwechsel - mit einer Sperre für unfertige Einstellungen.

        Der Wechsel wird hier abgefangen, bevor der Seitenstapel überhaupt
        umschaltet; ein nachträgliches Zurückholen sähe man als kurzes
        Hin- und Herspringen. Die Navigationsleiste markiert die Zielseite
        allerdings schon beim Klick, deshalb wird ihre Auswahl zurückgesetzt."""
        if (interface is not self.settings_page
                and self.stackedWidget.currentWidget() is self.settings_page
                and self.settings_page.incomplete()):
            self.navigationInterface.setCurrentItem(self.settings_page.objectName())
            self._warn_settings_incomplete()
            return
        super().switchTo(interface)

    def _warn_settings_incomplete(self):
        names = ", ".join(tr(c) for c in self.settings_page.incomplete())
        self.log(tr("Zielordner fehlt") + ": " + names)
        self._notify(
            tr("Zielordner fehlt"),
            tr("Für {list} ist noch kein Ordner gewählt.\n\nBitte einen Ordner angeben "
               "oder das Häkchen entfernen, wenn du diese Kategorie nicht führst.")
            .format(list=names),
        )

    def _apply_sidebar_background(self):
        """Deckende Flaeche hinter der Seitenleiste.

        Die Leiste selbst bleibt durchsichtig - eine eigene Formatvorlage wuerde
        die von qfluentwidgets mitgelieferte ersetzen und damit die Farben der
        Eintraege mitnehmen. Stattdessen bekommt das Fenster die gewuenschte
        Farbe; die Inhaltsseiten liegen mit ihrer eigenen Flaeche darueber."""
        try:
            self.navigationInterface.setAcrylicEnabled(False)
        except Exception:
            pass  # aeltere qfluentwidgets-Fassungen kennen das nicht
        self.setCustomBackgroundColor(SIDEBAR_LIGHT, SIDEBAR_DARK)

    def _on_stacked_page_changed(self, index: int):
        widget = self.stackedWidget.widget(index)
        self.log_page.set_active(widget is self.log_page)

    def _build_theme_toggle(self) -> QHBoxLayout:
        """Kompakter Hell/Dunkel/System-Umschalter - einzige Einstellung, die
        nirgendwo sonst auf der Konvertierungs-Seite auftaucht."""
        row = QHBoxLayout()
        self.theme_selector = SegmentedWidget()
        for mode, label in theme.THEME_OPTIONS:
            self.theme_selector.addItem(
                routeKey=mode, text=tr(label), onClick=lambda _c=False, m=mode: self._on_theme_changed(m)
            )
        self.theme_selector.setCurrentItem(self.settings.get("theme"))
        # Horizontal: ohne Begrenzung zieht sich der Umschalter über die halbe Titelzeile.
        # Vertikal MUSS Fixed sein: SegmentedWidget.paintEvent zeichnet die Pille auf
        # Höhe der Items, den blauen Indikator aber bei height()-3.5. Darf das Widget
        # vom Layout höher gezogen werden als seine Items, driften beide auseinander
        # (Pille oben, Strich unten) - genau der "buggy" aussehende Zustand.
        self.theme_selector.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        row.addWidget(self.theme_selector, 0, Qt.AlignVCenter)
        return row

    def _on_theme_changed(self, mode: str):
        self.settings.set("theme", mode)
        self.settings.save()
        setTheme(theme.to_qfluent_theme(mode))

    # =========================================================================
    # Seite: Konvertierung
    # =========================================================================

    def _build_encoding_row(self, suffix: str) -> QHBoxLayout:
        """Baut eine CQ/Preset/Codec-Zeile und hängt die Widgets als
        self.crf_slider{suffix}, self.preset_combo{suffix}, self.codec_combo{suffix}
        an - suffix ist '' für die globale Zeile, '_anime'/'_realfilm' für getrennte Presets."""
        row = QHBoxLayout()
        row.setSpacing(28)

        quality_col = QVBoxLayout()
        quality_col.setSpacing(4)
        quality_col.addWidget(CaptionLabel(tr("Qualität vs. Dateigröße")))
        slider_row = QHBoxLayout()
        slider_row.addWidget(QLabel(""))
        crf_slider = Slider(Qt.Horizontal)
        crf_slider.setMinimum(20)
        crf_slider.setMaximum(51)
        crf_slider.setMinimumWidth(180)
        slider_row.addWidget(crf_slider, 1)
        slider_row.addWidget(QLabel(""))
        quality_col.addLayout(slider_row)
        crf_label = CaptionLabel("")
        quality_col.addWidget(crf_label)
        row.addLayout(quality_col, 2)
        crf_slider.valueChanged.connect(lambda v, lbl=crf_label: self.update_crf_label(v, lbl))
        crf_slider.valueChanged.connect(self._on_convert_control_changed)

        preset_col = QVBoxLayout()
        preset_col.setSpacing(4)
        preset_col.addWidget(CaptionLabel(tr("Geschwindigkeit")))
        preset_combo = ComboBox()
        for preset in PRESETS:
            preset_combo.addItem(tr(PRESET_LABELS[preset]), userData=preset)
        preset_combo.currentIndexChanged.connect(self._on_convert_control_changed)
        preset_col.addWidget(preset_combo)
        preset_col.addStretch()
        row.addLayout(preset_col, 1)

        codec_col = QVBoxLayout()
        codec_col.setSpacing(4)
        codec_col.addWidget(CaptionLabel(tr("Codec (GPU/NVENC)")))
        codec_combo = ComboBox()
        for codec, label in CODEC_LABELS.items():
            codec_combo.addItem(tr(label), userData=codec)
        codec_combo.currentIndexChanged.connect(self._on_encoder_selection_changed)
        codec_combo.currentIndexChanged.connect(self._on_convert_control_changed)
        codec_col.addWidget(codec_combo)
        codec_col.addStretch()
        row.addLayout(codec_col, 1)

        setattr(self, f"crf_slider{suffix}", crf_slider)
        setattr(self, f"crf_label{suffix}", crf_label)
        setattr(self, f"preset_combo{suffix}", preset_combo)
        setattr(self, f"codec_combo{suffix}", codec_combo)

        return row

    def _on_separate_presets_toggled(self, checked: bool):
        self.split_encoding_widget.setVisible(checked)
        self.split_presets_hint.setVisible(checked)
        # Die immer sichtbaren Werte oben gelten dann nicht mehr - ausgrauen statt
        # verstecken, damit die Zeile nicht bei jedem Umschalten die Höhe ändert.
        for widget in (self.codec_combo, self.preset_combo, self.crf_slider):
            widget.setEnabled(not checked)
        self._refresh_encoder_availability()

    def _on_encoding_section_toggled(self, checked: bool):
        self.encoding_details_widget.setVisible(checked)
        self.encoding_toggle_btn.setText(tr("Erweitert"))

    # =========================================================================
    # "Nach Abschluss"-Aktion
    #
    # Ersetzt die früheren zwei getrennten Checkboxen (Herunterfahren /
    # Auto-NAS-Upload). Nur der NAS-Anteil wird persistiert - Herunterfahren ist
    # bewusst nie gespeichert, damit es nach einem Neustart der App nie
    # unbemerkt noch aktiv ist.
    # =========================================================================

    POST_ACTION_NONE = "none"
    POST_ACTION_NAS = "nas"
    POST_ACTION_SHUTDOWN = "shutdown"
    POST_ACTION_NAS_SHUTDOWN = "nas_shutdown"

    def _build_post_action_combo(self) -> ComboBox:
        self.post_action_combo = ComboBox()
        self.post_action_combo.setMinimumWidth(310)
        for value, label in (
            (self.POST_ACTION_NONE, tr("Nichts weiter tun")),
            (self.POST_ACTION_NAS, tr("In die Mediathek verschieben")),
            (self.POST_ACTION_SHUTDOWN, tr("PC herunterfahren")),
            (self.POST_ACTION_NAS_SHUTDOWN, tr("In die Mediathek verschieben, dann herunterfahren")),
        ):
            self.post_action_combo.addItem(label, userData=value)
        self.post_action_combo.setToolTip(tr(
            "Das Verschieben wird gespeichert, das Herunterfahren nicht - nach einem "
            "Neustart der App ist 'herunterfahren' immer wieder aus."
        ))
        self.post_action_combo.currentIndexChanged.connect(self._on_convert_control_changed)
        return self.post_action_combo

    def _post_action(self) -> str:
        return self.post_action_combo.currentData() or self.POST_ACTION_NONE

    def _post_nas_enabled(self) -> bool:
        return self._post_action() in (self.POST_ACTION_NAS, self.POST_ACTION_NAS_SHUTDOWN)

    def _post_shutdown_enabled(self) -> bool:
        return self._post_action() in (self.POST_ACTION_SHUTDOWN, self.POST_ACTION_NAS_SHUTDOWN)

    def _set_post_action(self, value: str):
        index = self.post_action_combo.findData(value)
        if index >= 0:
            self.post_action_combo.setCurrentIndex(index)

    def _clear_post_shutdown(self):
        """Nach einmaligem Auslösen den Herunterfahren-Anteil entfernen, den
        NAS-Anteil aber stehen lassen."""
        self._set_post_action(self.POST_ACTION_NAS if self._post_nas_enabled() else self.POST_ACTION_NONE)

    def _card(self, layout_parent, title: str = None, stretch: int = 0):
        card = CardWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(10)
        if title:
            card_layout.addWidget(StrongBodyLabel(title))
        layout_parent.addWidget(card, stretch)
        return card_layout

    def _build_source_target_row(self) -> QHBoxLayout:
        """Quelle und Ziel als zwei gleichwertige Karten nebeneinander, jeweils
        mit einer Zusammenfassung darunter (Anzahl/Größe) - statt einer einzigen
        gedrängten Zeile aus vier Steuerelementen."""
        row = QHBoxLayout()
        row.setSpacing(14)

        source_card = CardWidget()
        source_layout = QVBoxLayout(source_card)
        source_layout.setContentsMargins(18, 14, 18, 14)
        source_layout.setSpacing(8)
        source_layout.addWidget(CaptionLabel(tr("QUELLORDNER")))
        source_input_row = QHBoxLayout()
        source_input_row.setSpacing(8)
        self.source_input = DragDropLineEdit()
        self.source_input.setPlaceholderText(tr("Ordner hierher ziehen oder durchsuchen..."))
        self.source_input.path_dropped.connect(self.on_source_changed)
        self.source_input.path_dropped.connect(self._on_convert_control_changed)
        self.source_input.editingFinished.connect(self._on_convert_control_changed)
        source_input_row.addWidget(self.source_input, 1)
        source_btn = PushButton(tr("Durchsuchen"))
        source_btn.clicked.connect(self.browse_source)
        source_input_row.addWidget(source_btn)
        source_layout.addLayout(source_input_row)
        self.source_summary_label = CaptionLabel(tr("Noch nicht gescannt"))
        source_layout.addWidget(self.source_summary_label)
        row.addWidget(source_card, 1)

        target_card = CardWidget()
        target_layout = QVBoxLayout(target_card)
        target_layout.setContentsMargins(18, 14, 18, 14)
        target_layout.setSpacing(8)
        target_layout.addWidget(CaptionLabel(tr("ZIELORDNER")))
        target_input_row = QHBoxLayout()
        target_input_row.setSpacing(8)
        self.target_input = LineEdit()
        self.target_input.setPlaceholderText(tr("Standard: 'Converted' im Quellverzeichnis"))
        self.target_input.editingFinished.connect(self._on_convert_control_changed)
        target_input_row.addWidget(self.target_input, 1)
        target_btn = PushButton(tr("Durchsuchen"))
        target_btn.clicked.connect(self.browse_target)
        target_input_row.addWidget(target_btn)
        target_layout.addLayout(target_input_row)
        self.target_summary_label = CaptionLabel(tr("Noch nichts konvertiert"))
        target_layout.addWidget(self.target_summary_label)
        row.addWidget(target_card, 1)

        return row

    def _build_encoding_card(self) -> CardWidget:
        """Die drei Werte, die man wirklich regelmäßig anfasst (Codec, Preset,
        Qualität), stehen immer sichtbar in einer Zeile; alles Seltenere liegt
        hinter 'Erweitert'."""
        card = CardWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 14, 18, 14)
        card_layout.setSpacing(10)

        quick_row = QHBoxLayout()
        quick_row.setSpacing(18)

        codec_col = QVBoxLayout()
        codec_col.setSpacing(4)
        codec_col.addWidget(CaptionLabel(tr("CODEC")))
        self.codec_combo = ComboBox()
        for codec, label in CODEC_LABELS.items():
            self.codec_combo.addItem(tr(label), userData=codec)
        self.codec_combo.currentIndexChanged.connect(self._on_encoder_selection_changed)
        self.codec_combo.currentIndexChanged.connect(self._on_convert_control_changed)
        codec_col.addWidget(self.codec_combo)
        quick_row.addLayout(codec_col, 2)

        preset_col = QVBoxLayout()
        preset_col.setSpacing(4)
        preset_col.addWidget(CaptionLabel(tr("PRESET")))
        self.preset_combo = ComboBox()
        for preset in PRESETS:
            self.preset_combo.addItem(tr(PRESET_LABELS[preset]), userData=preset)
        self.preset_combo.currentIndexChanged.connect(self._on_convert_control_changed)
        preset_col.addWidget(self.preset_combo)
        quick_row.addLayout(preset_col, 2)

        quality_col = QVBoxLayout()
        quality_col.setSpacing(4)
        self.crf_label = CaptionLabel(tr("QUALITÄT"))
        quality_col.addWidget(self.crf_label)
        self.crf_slider = Slider(Qt.Horizontal)
        self.crf_slider.setMinimum(20)
        self.crf_slider.setMaximum(51)
        self.crf_slider.setMinimumWidth(160)
        self.crf_slider.valueChanged.connect(lambda v: self.update_crf_label(v, self.crf_label))
        self.crf_slider.valueChanged.connect(self._on_convert_control_changed)
        quality_col.addWidget(self.crf_slider)
        quick_row.addLayout(quality_col, 3)

        self.encoding_toggle_btn = PushButton(tr("Erweitert"))
        self.encoding_toggle_btn.setCheckable(True)
        self.encoding_toggle_btn.setMinimumWidth(120)
        self.encoding_toggle_btn.clicked.connect(self._on_encoding_section_toggled)
        toggle_col = QVBoxLayout()
        toggle_col.addWidget(CaptionLabel(" "))
        toggle_col.addWidget(self.encoding_toggle_btn)
        quick_row.addLayout(toggle_col, 0)

        card_layout.addLayout(quick_row)

        self.split_presets_hint = CaptionLabel(
            tr("Getrennte Presets aktiv - die Werte oben werden ignoriert, siehe 'Erweitert'.")
        )
        self.split_presets_hint.setVisible(False)
        card_layout.addWidget(self.split_presets_hint)

        self.encoding_details_widget = QWidget()
        encoding_layout = QVBoxLayout(self.encoding_details_widget)
        encoding_layout.setContentsMargins(0, 8, 0, 0)
        encoding_layout.setSpacing(10)
        card_layout.addWidget(self.encoding_details_widget)
        self.encoding_details_widget.setVisible(False)

        self._fill_encoding_details(encoding_layout)
        return card

    def _fill_encoding_details(self, encoding_layout: QVBoxLayout):
        encoding_layout.addWidget(HorizontalSeparator())

        self.separate_presets_check = CheckBox(tr("Getrennte Presets (Anime/Realfilm)"))
        self.separate_presets_check.setToolTip(tr(
            "Zeichentrick komprimiert oft spürbar anders als Realfilm - mit eigenen "
            "CQ/Preset/Codec-Werten je nach erkanntem Medientyp statt einem globalen Wert für alles."
        ))
        self.separate_presets_check.toggled.connect(self._on_separate_presets_toggled)
        self.separate_presets_check.toggled.connect(self._on_convert_control_changed)
        encoding_layout.addWidget(self.separate_presets_check)

        # Die globalen Werte stehen bereits in der immer sichtbaren Zeile oben -
        # hier gibt es nur noch die aufgeteilte Variante.
        self.split_encoding_widget = QWidget()
        split_layout = QVBoxLayout(self.split_encoding_widget)
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.setSpacing(12)
        for bucket in PRESET_BUCKETS:
            split_layout.addWidget(StrongBodyLabel(tr(PRESET_BUCKET_LABELS[bucket])))
            split_layout.addLayout(self._build_encoding_row(f"_{bucket}"))
        encoding_layout.addWidget(self.split_encoding_widget)
        self.split_encoding_widget.setVisible(False)

        options_grid = QGridLayout()
        options_grid.setHorizontalSpacing(28)
        options_grid.setVerticalSpacing(8)

        tasks_column = QVBoxLayout()
        tasks_column.setSpacing(2)

        tasks_row = QHBoxLayout()
        tasks_row.addWidget(CaptionLabel(tr("Parallele Tasks:")))
        self.parallel_spin = SpinBox()
        self.parallel_spin.setMinimum(1)
        self.parallel_spin.setMaximum(8)
        self.parallel_spin.valueChanged.connect(self._on_convert_control_changed)
        self.parallel_spin.valueChanged.connect(self._update_encoder_hint)
        tasks_row.addWidget(self.parallel_spin)
        tasks_row.addStretch()
        tasks_column.addLayout(tasks_row)

        # Hinweis zur Encoder-Ausstattung. Bewusst nur ein Hinweis und keine
        # Begrenzung: mehr Läufe als Einheiten bringen zwar wenig, aber messbar
        # noch etwas - die Entscheidung bleibt beim Nutzer.
        self.encoder_hint = CaptionLabel("")
        self.encoder_hint.setWordWrap(True)
        tasks_column.addWidget(self.encoder_hint)

        options_grid.addLayout(tasks_column, 0, 0)

        self.normalize_check = CheckBox(tr("R128 Audio-Normalisierung"))
        self.normalize_check.toggled.connect(self._on_convert_control_changed)
        options_grid.addWidget(self.normalize_check, 0, 1)

        self.rename_check = CheckBox(tr("Automatisches Umbenennen"))
        self.rename_check.toggled.connect(self._on_convert_control_changed)
        options_grid.addWidget(self.rename_check, 1, 0)

        self.delete_source_check = CheckBox(tr("Quelle nach Konvertierung löschen"))
        self.delete_source_check.toggled.connect(self._on_convert_control_changed)
        options_grid.addWidget(self.delete_source_check, 1, 1)

        container_row = QHBoxLayout()
        container_row.addWidget(CaptionLabel(tr("Container:")))
        self.container_combo = ComboBox()
        for value in CONTAINERS:
            self.container_combo.addItem(tr(CONTAINER_LABELS[value]), userData=value)
        self.container_combo.currentIndexChanged.connect(self._on_convert_control_changed)
        self.container_combo.currentIndexChanged.connect(self._on_container_changed)
        container_row.addWidget(self.container_combo, 1)
        options_grid.addLayout(container_row, 2, 0, 1, 2)

        encoding_layout.addLayout(options_grid)

    def _build_queue_card(self) -> CardWidget:
        card = CardWidget()
        files_layout = QVBoxLayout(card)
        files_layout.setContentsMargins(18, 14, 18, 16)
        files_layout.setSpacing(10)

        toolbar_row = QHBoxLayout()
        toolbar_row.setSpacing(8)
        self.stats_label = StrongBodyLabel(tr("Warteschlange"))
        toolbar_row.addWidget(self.stats_label)
        toolbar_row.addStretch()

        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)
        self._filter_buttons = {}
        for key, label in (("all", tr("Alle")), ("waiting", tr("Wartend")), ("processing", tr("In Arbeit")),
                           ("done", tr("Fertig")), ("error", tr("Fehler"))):
            btn = PillPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(key == "all")
            btn.clicked.connect(lambda _c=False, k=key: self.apply_filter(k))
            self.filter_group.addButton(btn)
            self._filter_buttons[key] = btn
            toolbar_row.addWidget(btn)

        toolbar_row.addSpacing(12)

        self.scan_btn = PushButton(tr("Dateien scannen"))
        self.scan_btn.clicked.connect(self.scan_files)
        toolbar_row.addWidget(self.scan_btn)

        # Ein sich drehender Ring statt bloßer Textmeldungen. Grund: der teuerste
        # Schritt (die Mediathek nach der Staffel-Benennung absuchen) meldet sich
        # genau einmal und arbeitet dann sekundenlang stumm weiter. Ein Text, der
        # dabei stillsteht, sieht aus wie ein hängendes Programm - der Ring dreht
        # sich unabhängig davon, ob gerade eine Meldung kommt.
        self.scan_spinner = IndeterminateProgressRing()
        self.scan_spinner.setFixedSize(20, 20)
        self.scan_spinner.setStrokeWidth(3)
        self.scan_spinner.setVisible(False)
        toolbar_row.addWidget(self.scan_spinner)

        self.scan_status_label = CaptionLabel("")
        self.scan_status_label.setVisible(False)
        toolbar_row.addWidget(self.scan_status_label)

        self.clear_list_btn = PushButton(tr("Liste leeren"))
        self.clear_list_btn.clicked.connect(self.clear_file_list)
        self.clear_list_btn.setEnabled(False)
        toolbar_row.addWidget(self.clear_list_btn)

        files_layout.addLayout(toolbar_row)

        self.file_table = TableWidget()
        self.file_table.setBorderVisible(True)
        self.file_table.setBorderRadius(8)
        self.file_table.setColumnCount(6)
        self.file_table.setHorizontalHeaderLabels([tr("Dateiname"), tr("Typ"), tr("Status"), tr("Fortschritt"), tr("Ziel"), ""])
        self.file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.file_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.file_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.file_table.setColumnWidth(5, 44)
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.file_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.file_table.verticalHeader().setDefaultSectionSize(40)
        self.file_table.verticalHeader().setVisible(False)
        self.file_table.setMinimumHeight(240)
        files_layout.addWidget(self.file_table)

        return card

    def _build_action_bar(self) -> CardWidget:
        """Fußleiste: links die Bilanz des Laufs, rechts alles zum Starten/Stoppen."""
        card = CardWidget()
        controls_layout = QVBoxLayout(card)
        controls_layout.setContentsMargins(18, 14, 18, 14)
        controls_layout.setSpacing(12)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        self.stat_total_label = CaptionLabel(tr("Gesamt: 0"))
        stats_row.addWidget(self.stat_total_label)
        stats_row.addWidget(HorizontalSeparator())
        self.stat_success_label = CaptionLabel(tr("Erfolgreich: 0"))
        stats_row.addWidget(self.stat_success_label)
        stats_row.addWidget(HorizontalSeparator())
        self.stat_error_label = CaptionLabel(tr("Fehler: 0"))
        stats_row.addWidget(self.stat_error_label)
        stats_row.addWidget(HorizontalSeparator())
        self.stat_size_before_label = CaptionLabel(tr("Vorher: -"))
        stats_row.addWidget(self.stat_size_before_label)
        stats_row.addWidget(HorizontalSeparator())
        self.stat_size_after_label = CaptionLabel(tr("Nachher: -"))
        stats_row.addWidget(self.stat_size_after_label)
        stats_row.addWidget(HorizontalSeparator())
        self.stat_savings_label = CaptionLabel(tr("Ersparnis: -"))
        stats_row.addWidget(self.stat_savings_label)
        stats_row.addStretch()
        self.eta_label = CaptionLabel(tr("Verbleibend: --:--:--"))
        stats_row.addWidget(self.eta_label)
        controls_layout.addLayout(stats_row)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(12)
        self.total_progress = ProgressBar()
        self.total_progress.setMinimumWidth(200)
        progress_row.addWidget(self.total_progress, 1)
        self.total_progress_status_label = CaptionLabel("")
        self.total_progress_status_label.setMinimumWidth(150)
        progress_row.addWidget(self.total_progress_status_label)
        controls_layout.addLayout(progress_row)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(10)
        controls_row.addWidget(BodyLabel(tr("Nach Abschluss:")))
        controls_row.addWidget(self._build_post_action_combo())
        controls_row.addStretch()

        self.start_btn = PrimaryPushButton(tr("Konvertierung starten"))
        self.start_btn.setMinimumWidth(210)
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self.start_conversion)
        controls_row.addWidget(self.start_btn)

        self.pause_btn = PushButton(tr("Pause"))
        self.pause_btn.setMinimumWidth(110)
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self.toggle_pause)
        controls_row.addWidget(self.pause_btn)

        self.stop_btn = PushButton(tr("Stoppen"))
        self.stop_btn.setMinimumWidth(110)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_conversion)
        controls_row.addWidget(self.stop_btn)

        controls_layout.addLayout(controls_row)
        return card

    def _build_convert_page(self) -> QWidget:
        page = ScrollablePage("convertPage")
        outer = page.content_layout

        title_row = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title_col.addWidget(TitleLabel(tr("Konvertierung")))
        title_col.addWidget(CaptionLabel(tr(APP_TAGLINE)))
        title_row.addLayout(title_col)
        title_row.addStretch()
        outer.addLayout(title_row)

        outer.addLayout(self._build_source_target_row())
        outer.addWidget(self._build_encoding_card())
        outer.addWidget(self._build_queue_card(), 1)
        outer.addWidget(self._build_action_bar())

        enforce_control_heights(page)
        return page

    # =========================================================================
    # Seite: Details
    # =========================================================================

    def _build_details_page(self) -> QWidget:
        page = ScrollablePage("detailsPage")
        outer = page.content_layout

        outer.addWidget(TitleLabel(tr("Details")))

        card_layout = self._card(outer, stretch=1)
        info_label = CaptionLabel(tr("Klicken Sie auf einen Eintrag, um Details anzuzeigen"))
        card_layout.addWidget(info_label)

        self.details_tree = TreeWidget()
        self.details_tree.setBorderVisible(True)
        self.details_tree.setBorderRadius(8)
        self.details_tree.setColumnCount(5)
        self.details_tree.setHeaderLabels([tr("Datei"), tr("Original"), tr("Neu"), tr("Ersparnis"), tr("Status")])
        self.details_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.details_tree.setUniformRowHeights(True)
        self.details_tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.details_tree.itemClicked.connect(self.on_details_item_clicked)
        card_layout.addWidget(self.details_tree)

        summary_row = QHBoxLayout()
        self.total_original_label = CaptionLabel(tr("Originalgröße: -"))
        self.total_new_label = CaptionLabel(tr("Neue Größe: -"))
        self.total_savings_label = CaptionLabel(tr("Gesamtersparnis: -"))
        summary_row.addWidget(self.total_original_label)
        summary_row.addWidget(self.total_new_label)
        summary_row.addWidget(self.total_savings_label)
        summary_row.addStretch()
        card_layout.addLayout(summary_row)

        enforce_control_heights(page)
        return page

    # =========================================================================
    # Seite: NAS-Upload
    # =========================================================================

    def _build_nas_page(self) -> QWidget:
        page = ScrollablePage("nasPage")
        outer = page.content_layout

        outer.addWidget(TitleLabel(tr("Mediathek")))

        header_layout = self._card(outer, tr("Fertige Medien einsortieren"))
        desc_label = CaptionLabel(tr(
            "Verschiebe konvertierte Serien und Filme in deine Mediathek. "
            "Die Kategorie stammt direkt aus der beim Konvertieren erzeugten Ordnerstruktur."
        ))
        desc_label.setWordWrap(True)
        header_layout.addWidget(desc_label)

        folder_row = QHBoxLayout()
        folder_row.addWidget(BodyLabel(tr("Converted-Ordner:")))
        self.nas_source_input = LineEdit()
        self.nas_source_input.setPlaceholderText(tr("Ordner mit konvertierten Medien auswählen..."))
        folder_row.addWidget(self.nas_source_input, 1)
        browse_btn = PushButton(tr("Durchsuchen..."))
        browse_btn.clicked.connect(self.browse_nas_source)
        folder_row.addWidget(browse_btn)
        self.nas_scan_btn = PushButton(tr("Aktualisieren"))
        self.nas_scan_btn.clicked.connect(self.scan_converted_folder)
        folder_row.addWidget(self.nas_scan_btn)
        header_layout.addLayout(folder_row)

        nas_path_row = QHBoxLayout()
        # Die Zielordner werden je Kategorie in den Einstellungen gepflegt; hier
        # steht nur noch, was aktuell eingestellt ist.
        self.nas_targets_label = CaptionLabel("")
        self.nas_targets_label.setWordWrap(True)
        nas_path_row.addWidget(self.nas_targets_label, 1)
        self.nas_status_label = CaptionLabel(tr("Nicht geprüft"))
        nas_path_row.addWidget(self.nas_status_label)
        check_nas_btn = PushButton(tr("Ziele prüfen"))
        check_nas_btn.clicked.connect(self.check_nas_connection)
        nas_path_row.addWidget(check_nas_btn)
        settings_btn = PushButton(tr("Zielordner ändern"))
        settings_btn.clicked.connect(lambda: self.switchTo(self.settings_page))
        nas_path_row.addWidget(settings_btn)
        header_layout.addLayout(nas_path_row)

        table_layout = self._card(outer, stretch=1)
        self.nas_table = TableWidget()
        self.nas_table.setBorderVisible(True)
        self.nas_table.setBorderRadius(8)
        self.nas_table.setColumnCount(6)
        self.nas_table.setHorizontalHeaderLabels(["", tr("Name"), tr("Typ"), tr("Zielordner"), tr("Größe"), tr("Status")])
        header = self.nas_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        self.nas_table.setColumnWidth(0, 50)
        self.nas_table.setColumnWidth(2, 100)
        self.nas_table.setColumnWidth(3, 150)
        self.nas_table.setColumnWidth(4, 100)
        self.nas_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.nas_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.nas_table.verticalHeader().setDefaultSectionSize(40)
        self.nas_table.verticalHeader().setVisible(False)
        table_layout.addWidget(self.nas_table)

        stats_row = QHBoxLayout()
        self.nas_stats_label = CaptionLabel(tr("Keine Medien gefunden"))
        stats_row.addWidget(self.nas_stats_label)
        stats_row.addStretch()
        select_all_btn = PushButton(tr("Alle auswählen"))
        select_all_btn.clicked.connect(self.nas_select_all)
        stats_row.addWidget(select_all_btn)
        select_none_btn = PushButton(tr("Keine auswählen"))
        select_none_btn.clicked.connect(self.nas_select_none)
        stats_row.addWidget(select_none_btn)
        table_layout.addLayout(stats_row)

        options_row = QHBoxLayout()
        self.nas_delete_check = CheckBox(tr("Lokale Ordner nach dem Verschieben löschen"))
        self.nas_delete_check.toggled.connect(self._on_convert_control_changed)
        options_row.addWidget(self.nas_delete_check)
        options_row.addStretch()
        table_layout.addLayout(options_row)

        progress_layout = self._card(outer)
        progress_row = QHBoxLayout()
        progress_row.addWidget(BodyLabel(tr("Fortschritt:")))
        self.nas_progress = ProgressBar()
        progress_row.addWidget(self.nas_progress, 1)
        self.nas_current_label = CaptionLabel("")
        progress_row.addWidget(self.nas_current_label)
        progress_layout.addLayout(progress_row)

        buttons_row = QHBoxLayout()
        buttons_row.addStretch()
        self.nas_move_selected_btn = PrimaryPushButton(tr("Ausgewählte verschieben"))
        self.nas_move_selected_btn.setMinimumWidth(190)
        self.nas_move_selected_btn.setEnabled(False)
        self.nas_move_selected_btn.clicked.connect(self.nas_move_selected)
        buttons_row.addWidget(self.nas_move_selected_btn)
        self.nas_move_all_btn = PushButton(tr("Alle verschieben"))
        self.nas_move_all_btn.setMinimumWidth(160)
        self.nas_move_all_btn.setEnabled(False)
        self.nas_move_all_btn.clicked.connect(self.nas_move_all)
        buttons_row.addWidget(self.nas_move_all_btn)
        self.nas_stop_btn = PushButton(tr("Stoppen"))
        self.nas_stop_btn.setMinimumWidth(110)
        self.nas_stop_btn.setEnabled(False)
        self.nas_stop_btn.clicked.connect(self.nas_stop_upload)
        buttons_row.addWidget(self.nas_stop_btn)
        progress_layout.addLayout(buttons_row)

        enforce_control_heights(page)
        return page

    # =========================================================================
    # Einstellungen laden/speichern
    # =========================================================================

    def _apply_encoding_bucket_to_controls(self, suffix: str, cq_key: str, preset_key: str, codec_key: str):
        slider = getattr(self, f"crf_slider{suffix}")
        label = getattr(self, f"crf_label{suffix}")
        preset_combo = getattr(self, f"preset_combo{suffix}")
        codec_combo = getattr(self, f"codec_combo{suffix}")

        # Reihenfolge ist wichtig: erst der Codec, denn er bestimmt die
        # Obergrenze des Reglers. Umgekehrt würde ein gespeicherter AV1-Wert von
        # 60 am noch geltenden Maximum 51 abgeschnitten - und wäre damit still
        # verändert, ohne dass jemand etwas angefasst hat.
        codec = self.settings.get(codec_key)
        idx = codec_combo.findData(codec)
        if idx >= 0:
            codec_combo.setCurrentIndex(idx)
        slider.setMaximum(cq_maximum_for(codec or DEFAULT_CODEC))

        slider.setValue(self.settings.get(cq_key))
        self.update_crf_label(self.settings.get(cq_key), label, codec)

        idx = preset_combo.findData(self.settings.get(preset_key))
        if idx >= 0:
            preset_combo.setCurrentIndex(idx)

    def _apply_settings_to_controls(self):
        self._apply_encoding_bucket_to_controls("", "cq", "preset", "codec")
        for bucket in PRESET_BUCKETS:
            self._apply_encoding_bucket_to_controls(f"_{bucket}", f"cq_{bucket}", f"preset_{bucket}", f"codec_{bucket}")

        use_separate = self.settings.get("use_separate_presets")
        self.separate_presets_check.setChecked(use_separate)
        self._on_separate_presets_toggled(use_separate)

        # Erst jetzt, nachdem Codec UND gespeicherter CQ-Wert stehen: sonst
        # würde ein gespeicherter AV1-Wert von 60 am noch geltenden Maximum 51
        # abgeschnitten, bevor der Codec überhaupt gesetzt ist.
        self._apply_cq_range()

        self.parallel_spin.setValue(self.settings.get("parallel_tasks"))
        idx = self.container_combo.findData(self.settings.get("container"))
        if idx >= 0:
            self.container_combo.setCurrentIndex(idx)
        self.normalize_check.setChecked(self.settings.get("normalize_audio"))
        self.rename_check.setChecked(self.settings.get("rename_enabled"))
        self.delete_source_check.setChecked(self.settings.get("delete_source_after_convert"))
        self.nas_delete_check.setChecked(self.settings.get("delete_local_after_nas_move"))
        # Nur der NAS-Anteil wird geladen - Herunterfahren startet immer auf "aus".
        self._set_post_action(
            self.POST_ACTION_NAS if self.settings.get("auto_nas_upload_after_convert")
            else self.POST_ACTION_NONE
        )

        self.settings_page.set_category_folders(self.settings.get("category_folders"))
        self.settings_page.set_language(self.settings.get("language"))
        self._refresh_nas_targets_label()

        source_folder = self.settings.get("source_folder")
        if source_folder:
            self.source_input.setText(source_folder)
        target_folder = self.settings.get("target_folder")
        if target_folder:
            self.target_input.setText(target_folder)

    def _save_current_settings(self):
        values = {
            "cq": self.crf_slider.value(),
            "preset": self.preset_combo.currentData(),
            "codec": self.codec_combo.currentData(),
            "use_separate_presets": self.separate_presets_check.isChecked(),
            "parallel_tasks": self.parallel_spin.value(),
            "container": self.container_combo.currentData(),
            "normalize_audio": self.normalize_check.isChecked(),
            "rename_enabled": self.rename_check.isChecked(),
            "delete_source_after_convert": self.delete_source_check.isChecked(),
            "delete_local_after_nas_move": self.nas_delete_check.isChecked(),
            "auto_nas_upload_after_convert": self._post_nas_enabled(),
            "source_folder": self.source_input.text().strip(),
            "target_folder": self.target_input.text().strip(),
            "category_folders": self.settings_page.category_folders(),
            "language": self.settings_page.language(),
        }
        for bucket in PRESET_BUCKETS:
            values[f"cq_{bucket}"] = getattr(self, f"crf_slider_{bucket}").value()
            values[f"preset_{bucket}"] = getattr(self, f"preset_combo_{bucket}").currentData()
            values[f"codec_{bucket}"] = getattr(self, f"codec_combo_{bucket}").currentData()

        self.settings.update(values)
        self.settings.save()

    def _run_first_time_setup(self):
        """Einmalige Einrichtung beim allerersten Start.

        Ohne sie startet die Anwendung mit vier leeren Zielordnern, und dass das
        Einsortieren deshalb nicht laeuft, faellt erst nach der ersten fertigen
        Konvertierung auf."""
        dialog = SetupDialog(self._build_theme_toggle, self)
        dialog.exec_()

        self.settings_page.set_category_folders(dialog.category_folders())
        self.settings_page.set_language(dialog.language())
        self._detected_season_pattern = None
        self.settings.set("detected_season_pattern", "")
        self._save_current_settings()
        self._refresh_nas_targets_label()

        active = self.active_category_folders()
        if active:
            self.log(f"Eingerichtet: {', '.join(f'{c} -> {p}' for c, p in active.items())}")
        else:
            self.log("Keine Kategorie eingerichtet - es wird nur konvertiert, nicht verschoben.")

    def _on_settings_changed(self):
        """Wird von der Einstellungsseite bei jeder Änderung gerufen."""
        if not self._ui_ready:
            return
        previous_language = self.settings.get("language")
        self._save_current_settings()
        self._detected_season_pattern = None  # Zielordner geaendert -> neu ablesen
        self.settings.set("detected_season_pattern", "")
        self._refresh_nas_targets_label()
        if self.settings_page.language() != previous_language:
            self.settings_page.show_restart_hint()

    def _on_convert_control_changed(self, *_args):
        """Speichert sofort bei jeder Änderung eines Konvertierungs-Steuerelements,
        genau wie die Windows-11-Einstellungen-App - kein separater Speichern-Knopf."""
        if self._ui_ready:
            self._save_current_settings()

    def _on_encoder_selection_changed(self, *_args):
        self._refresh_encoder_availability()
        self._apply_cq_range()

    def _apply_cq_range(self):
        """Passt Reichweite und Beschriftung der Qualitätsregler an den Codec an.

        AV1 rechnet auf einer Skala bis 63, H.265 und H.264 bis 51. Der Regler
        folgt dem, damit bei AV1 auch die stärkere Kompression erreichbar ist.

        Beim Wechsel nach unten kappt Qt einen zu hohen Wert von selbst. Das ist
        hier gewollt und unbedenklich, weil man es sieht: der Regler springt
        sichtbar, und die Beschriftung nennt die neue Grenze. Ein Wert, den der
        Encoder ablehnt, kann so gar nicht erst entstehen - `-cq 60` an H.265
        bricht mit 'Value out of range' ab."""
        paare = [("", self.codec_combo if hasattr(self, "codec_combo") else None)]
        paare += [(f"_{bucket}", getattr(self, f"codec_combo_{bucket}", None))
                  for bucket in PRESET_BUCKETS]

        for suffix, kasten in paare:
            regler = getattr(self, f"crf_slider{suffix}", None)
            beschriftung = getattr(self, f"crf_label{suffix}", None)
            if regler is None or beschriftung is None:
                continue
            codec = (kasten.currentData() if kasten else None) or DEFAULT_CODEC
            regler.setMaximum(cq_maximum_for(codec))
            self.update_crf_label(regler.value(), beschriftung, codec)

    def _refresh_encoder_availability(self):
        """Prüft alle aktuell relevanten Encoder - bei getrennten Presets können
        Anime und Realfilm unterschiedliche Codecs verwenden, dann müssen beide
        verfügbar sein."""
        if self.separate_presets_check.isChecked():
            codecs = {self.codec_combo_anime.currentData(), self.codec_combo_realfilm.currentData()}
        else:
            codecs = {self.codec_combo.currentData()}
        codecs.discard(None)

        unavailable = [c for c in codecs if not self.ffmpeg.check_encoder_available(c)]
        self.encoder_available = len(unavailable) == 0
        for codec in unavailable:
            self.log(f"⚠️ Encoder '{codec}' ist auf diesem System nicht verfügbar!")
        self._update_start_button_state()

    def closeEvent(self, event):
        # Ohne Nachfrage würde das Schließen den laufenden ffmpeg-Prozess als Waise
        # zurücklassen und die halbfertige .tmp-Datei im Zielordner liegen lassen.
        running = []
        if self.worker and self.worker.isRunning():
            running.append(tr("eine Konvertierung"))
        if self.nas_worker and self.nas_worker.isRunning():
            running.append(tr("ein Verschiebevorgang"))

        if running:
            if not self._confirm(
                tr("Läuft noch"),
                tr("Es läuft gerade {what}.\n\nBeim Beenden wird das abgebrochen; bereits fertige "
                   "Dateien bleiben erhalten.\n\nWirklich beenden?")
                .format(what=f" {tr('und')} ".join(running)),
                yes_text=tr("Beenden"), no_text=tr("Weiterlaufen lassen"),
            ):
                event.ignore()
                return

            if self.worker:
                self.worker.stop()
                self.worker.wait(5000)
            if self.nas_worker:
                self.nas_worker.stop()
                self.nas_worker.wait(5000)

        self.gpu_monitor.stop()
        self.gpu_monitor.wait(2000)
        if self.tray_icon:
            self.tray_icon.hide()
        self._save_current_settings()
        super().closeEvent(event)

    # =========================================================================
    # Dialog-/Benachrichtigungs-Helfer
    # =========================================================================

    def _confirm(self, title: str, content: str, yes_text=tr("Ja"), no_text=tr("Nein")) -> bool:
        box = MessageBox(title, content, self)
        box.yesButton.setText(yes_text)
        box.cancelButton.setText(no_text)
        return bool(box.exec_())

    def _notify(self, title: str, content: str):
        box = MessageBox(title, content, self)
        box.cancelButton.hide()
        box.yesButton.setText(tr("OK"))
        box.exec_()

    def _toast_success(self, title: str, content: str):
        InfoBar.success(title, content, duration=4000, position=InfoBarPosition.TOP, parent=self)

    def _toast_warning(self, title: str, content: str):
        InfoBar.warning(title, content, duration=6000, position=InfoBarPosition.TOP, parent=self)

    # =========================================================================
    # Windows-Benachrichtigungen (Infobereich)
    # =========================================================================

    def _setup_tray_icon(self):
        """Symbol im Infobereich - Voraussetzung für echte Windows-Toasts.

        QSystemTrayIcon.showMessage() erzeugt unter Windows 10/11 eine native
        Benachrichtigung; sie erscheint auch, wenn das Fenster minimiert ist.
        Ein zusätzliches Paket braucht es dafür nicht."""
        self.tray_icon = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        icon = QApplication.windowIcon()
        if icon.isNull():
            icon = self.style().standardIcon(self.style().SP_MediaPlay)

        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip(f"{APP_NAME} v{APP_VERSION}")
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.messageClicked.connect(self._restore_window)
        self.tray_icon.show()

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._restore_window()

    def _restore_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def notify_system(self, title: str, message: str, warning: bool = False):
        """Windows-Benachrichtigung - gedacht für den Fall, dass das Fenster
        minimiert ist und man den Abschluss sonst gar nicht mitbekommt."""
        if not self.tray_icon:
            return
        icon = QSystemTrayIcon.Warning if warning else QSystemTrayIcon.Information
        self.tray_icon.showMessage(title, message, icon, 10000)

    def _on_unhandled_error(self, summary: str, full_text: str):
        """Wird von crash_logging aufgerufen, wenn eine Ausnahme abgefangen wurde,
        die die App früher kommentarlos beendet hätte."""
        self.log(f"⚠️ Interner Fehler abgefangen: {summary}")
        self.log(f"   Details stehen in {crash_logging.CRASH_LOG_PATH}")
        for line in full_text.rstrip().splitlines():
            self.log(f"   {line}")
        try:
            self._toast_error(tr("Interner Fehler"), summary + "\n" + tr("Details im Protokoll."))
        except Exception:  # noqa: BLE001 - darf keinen zweiten Fehler auslösen
            pass

    def _toast_error(self, title: str, content: str):
        InfoBar.error(title, content, duration=6000, position=InfoBarPosition.TOP, parent=self)

    # =========================================================================
    # NAS-Upload Methoden
    # =========================================================================

    def browse_nas_source(self):
        start_dir = self.target_input.text().strip() or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(self, tr("Converted-Ordner auswählen"), start_dir)
        if folder:
            self.nas_source_input.setText(folder)
            self.scan_converted_folder()

    def current_season_pattern(self) -> str:
        """Wie Staffel-Ordner benannt werden.

        Vorrang hat eine ausdrückliche Einstellung; sonst wird die Schreibweise
        aus der vorhandenen Mediathek übernommen. Findet sich auch dort nichts,
        bleibt die reine Zahl - die einzige Variante, die in keiner Sprache
        falsch ist. So steht nirgends ein von der App vorgegebenes Wort."""
        configured = (self.settings.get("season_folder_pattern") or "").strip()
        if configured:
            return configured

        # Einmal Ermitteltes wird dauerhaft gemerkt, nicht nur für die laufende
        # Sitzung. Das Ablesen kostet auf einer Mediathek im Netz mehrere
        # Sekunden und liefert dabei jedes Mal dasselbe - die Benennung einer
        # gewachsenen Sammlung ändert sich nicht. Verworfen wird der Wert, wenn
        # der Nutzer die Kategorie-Ordner ändert (siehe _on_settings_changed).
        if self._detected_season_pattern is None:
            self._detected_season_pattern = (
                self.settings.get("detected_season_pattern") or "").strip() or None

        if self._detected_season_pattern is None:
            detected = detect_season_pattern(self.active_category_folders().values())
            self._detected_season_pattern = detected or NUMERIC_ONLY
            self.settings.set("detected_season_pattern", self._detected_season_pattern)
            self.settings.save()   # sofort schreiben, sonst wäre es beim nächsten Start wieder weg
            if detected:
                self.log(f"Staffel-Benennung aus der Mediathek übernommen: '{detected}'")
        return self._detected_season_pattern

    def active_category_folders(self) -> Dict[str, str]:
        """Kategorien mit hinterlegtem Zielordner - alles andere gilt als nicht benutzt."""
        folders = self.settings.get("category_folders") or {}
        return {c: p.strip() for c, p in folders.items() if (p or "").strip()}

    def _refresh_nas_targets_label(self):
        active = self.active_category_folders()
        if not active:
            self.nas_targets_label.setText(tr(
                "Noch keine Zielordner eingestellt - unter Einstellungen festlegen, "
                "wohin die einzelnen Kategorien sollen."
            ))
        else:
            self.nas_targets_label.setText(
                "Ziele:   " + "     ".join(f"{c} → {p}" for c, p in active.items())
            )

    def check_nas_connection(self):
        active = self.active_category_folders()
        if not active:
            self.nas_status_label.setText(tr("Nichts eingestellt"))
            self._notify(
                tr("Keine Zielordner"),
                tr("Es ist noch kein Zielordner hinterlegt.\n\nUnter Einstellungen kannst du je "
                   "Kategorie festlegen, wohin die fertigen Dateien verschoben werden.")
            )
            return

        missing = [f"{c}: {p}" for c, p in active.items() if not Path(p).exists()]
        if missing:
            self.nas_status_label.setText(f" {len(missing)} nicht erreichbar")
            self.log("❌ Nicht erreichbare Zielordner: " + " | ".join(missing))
            self._notify(
                tr("Zielordner nicht erreichbar"),
                tr("Diese Ordner sind gerade nicht erreichbar:\n\n{list}\n\nLiegen sie auf einem "
                   "Netzlaufwerk? Stimmen die Pfade? Bestehen die Zugriffsrechte?")
                .format(list="\n".join(missing))
            )
        else:
            self.nas_status_label.setText(f" {len(active)} Ziele erreichbar")
            self.log("✅ Alle Zielordner erreichbar: " + ", ".join(active))

    def _refresh_library_after_upload(self, completed: int):
        """Liest die Liste nach einem Verschiebe-Lauf neu ein.

        Ohne das bleiben erfolgreich verschobene Ordner in der Übersicht stehen,
        obwohl sie lokal nicht mehr existieren. Der Neuaufbau ist dem Entfernen
        einzelner Zeilen vorzuziehen: er bildet ab, was wirklich noch da ist -
        einschließlich der Ordner, die bei abgeschaltetem "lokal löschen"
        absichtlich liegenbleiben."""
        if not completed:
            return
        try:
            self.scan_converted_folder()
        except Exception as error:  # noqa: BLE001 - Anzeige darf nie den Lauf kippen
            self.log(f"Mediathek-Liste konnte nicht aktualisiert werden: {error}")

    def scan_converted_folder(self):
        """Scannt den Converted-Ordner nach Medien.

        Kategorie-Unterordner (Anime/Anime Filme/Filme/Serien), wie sie
        PathGenerator erzeugt, werden 1:1 übernommen - kein Raten nötig.
        Nur für Show-Ordner direkt im Wurzelverzeichnis (z.B. aus einer
        älteren Converted-Struktur ohne Kategorie-Ebene) greift weiterhin
        die Schlüsselwort-Heuristik als Fallback.
        """
        source = self.nas_source_input.text().strip()

        if not source:
            source = self.target_input.text().strip()
            if source:
                self.nas_source_input.setText(source)

        if not source or not os.path.isdir(source):
            self._notify(tr("Fehler"), tr("Bitte wählen Sie einen gültigen Converted-Ordner aus."))
            return

        self.log(f"📂 Scanne Converted-Ordner: {source}")
        self.nas_items.clear()

        source_path = Path(source)
        category_folders = self.settings.get("category_folders") or {}

        for entry in sorted(source_path.iterdir()):
            if not entry.is_dir() or entry.name.startswith(('_', '.')):
                continue

            category = category_for_staging_folder(entry.name, category_folders)
            if category:
                for show_folder in sorted(entry.iterdir()):
                    if not show_folder.is_dir() or show_folder.name.startswith(('_', '.')):
                        continue
                    self._add_nas_item(show_folder, category)
            else:
                # Sprachunabhaengig: ein Unterordner, dessen Name auf eine Zahl
                # endet, ist ein Staffelordner - egal ob "Staffel 2", "Season 2" oder "2".
                has_seasons = any(
                    sub.is_dir() and parse_season_convention(sub.name) is not None
                    for sub in entry.iterdir()
                )
                media_type = self._legacy_detect_media_type(entry.name, has_seasons)
                category = self._get_default_category(media_type)
                self._add_nas_item(entry, category, media_type, has_seasons)

        self.update_nas_table()

        total = len(self.nas_items)
        total_size = sum(item.total_size for item in self.nas_items)
        self.nas_stats_label.setText(tr("{count} Medien gefunden | Gesamt: {size}").format(
            count=total, size=self.format_size(total_size)))

        self.nas_move_selected_btn.setEnabled(total > 0)
        self.nas_move_all_btn.setEnabled(total > 0)

        self.log(f"Scan abgeschlossen: {total} Medien gefunden")

    def _add_nas_item(self, folder: Path, category: str, media_type: Optional[MediaType] = None,
                       has_seasons: bool = False):
        if media_type is None:
            media_type = MediaType(category) if category in [m.value for m in MediaType] else MediaType.UNBEKANNT
            has_seasons = category in (MediaType.ANIME.value, MediaType.SERIEN.value)

        item = NASUploadItem(
            folder_path=folder, name=folder.name, media_type=media_type,
            target_category=category, has_season_folders=has_seasons,
        )
        self.nas_items.append(item)
        self.log(f"  → {folder.name} [{media_type.value}] → {category}")

    @staticmethod
    def _legacy_detect_media_type(name: str, has_seasons: bool) -> MediaType:
        name_lower = name.lower()
        is_anime = any(kw in name_lower for kw in ANIME_KEYWORDS)
        if is_anime:
            return MediaType.ANIME if has_seasons else MediaType.ANIME_FILME
        return MediaType.SERIEN if has_seasons else MediaType.FILME

    @staticmethod
    def _get_default_category(media_type: MediaType) -> str:
        mapping = {
            MediaType.ANIME: tr("Anime"), MediaType.ANIME_FILME: tr("Anime Filme"),
            MediaType.FILME: tr("Filme"), MediaType.SERIEN: tr("Serien"), MediaType.UNBEKANNT: tr("Filme"),
        }
        return mapping.get(media_type, tr("Filme"))

    def _fit_category_column(self):
        """Passt die Kategorie-Spalte an den längsten Eintrag an.

        Eine feste Breite reicht nicht: die Kategorienamen sind übersetzt, und
        was auf Deutsch knapp passt ("Anime Filme"), läuft auf Englisch über
        ("Animated Movies"). Deshalb wird gemessen statt geschätzt."""
        metrics = QFontMetrics(self.nas_table.font())
        widest = max((metrics.width(tr(name)) for name in self.nas_categories),
                     default=0)
        # Zuschlag für Aufklapp-Pfeil, Innenabstand und Rahmen des Auswahlfelds.
        self.nas_table.setColumnWidth(3, max(150, widest + 68))

    def update_nas_table(self):
        colors = theme.semantic_colors()
        self.nas_table.setRowCount(len(self.nas_items))
        self._fit_category_column()

        for row, item in enumerate(self.nas_items):
            checkbox = CheckBox()
            checkbox.setChecked(True)
            checkbox_widget = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox_layout.addWidget(checkbox)
            checkbox_layout.setAlignment(Qt.AlignCenter)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            self.nas_table.setCellWidget(row, 0, checkbox_widget)

            self.nas_table.setItem(row, 1, QTableWidgetItem(item.name))

            type_item = QTableWidgetItem(tr(item.media_type.value))
            type_colors = {
                MediaType.ANIME: "#ff9900", MediaType.ANIME_FILME: "#ff6600",
                MediaType.FILME: "#0099ff", MediaType.SERIEN: colors["success"],
                MediaType.UNBEKANNT: colors["neutral"],
            }
            type_item.setForeground(QColor(type_colors.get(item.media_type, colors["neutral"])))
            type_item.setTextAlignment(Qt.AlignCenter)
            self.nas_table.setItem(row, 2, type_item)

            combo = ComboBox()
            combo.addItems(self.nas_categories)
            idx = combo.findText(item.target_category)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.currentTextChanged.connect(lambda text, r=row: self._on_category_changed(r, text))
            self.nas_table.setCellWidget(row, 3, combo)

            size_item = QTableWidgetItem(self.format_size(item.total_size))
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.nas_table.setItem(row, 4, size_item)

            status_item = QTableWidgetItem(tr(item.status.value))
            status_colors = {
                NASUploadStatus.BEREIT: colors["neutral"], NASUploadStatus.WIRD_VERSCHOBEN: colors["accent"],
                NASUploadStatus.FERTIG: colors["success"], NASUploadStatus.FEHLER: colors["error"],
                NASUploadStatus.UEBERSPRUNGEN: colors["warning"],
            }
            status_item.setForeground(QColor(status_colors.get(item.status, colors["neutral"])))
            status_item.setTextAlignment(Qt.AlignCenter)
            self.nas_table.setItem(row, 5, status_item)

    def _on_category_changed(self, row: int, text: str):
        if 0 <= row < len(self.nas_items):
            self.nas_items[row].target_category = text

    def nas_select_all(self):
        self._set_all_nas_checkboxes(True)

    def nas_select_none(self):
        self._set_all_nas_checkboxes(False)

    def _set_all_nas_checkboxes(self, checked: bool):
        for row in range(self.nas_table.rowCount()):
            widget = self.nas_table.cellWidget(row, 0)
            if widget:
                checkbox = widget.findChild(CheckBox)
                if checkbox:
                    checkbox.setChecked(checked)

    def _get_selected_items(self) -> List[NASUploadItem]:
        selected = []
        for row in range(self.nas_table.rowCount()):
            widget = self.nas_table.cellWidget(row, 0)
            if widget:
                checkbox = widget.findChild(CheckBox)
                if checkbox and checkbox.isChecked() and row < len(self.nas_items):
                    selected.append(self.nas_items[row])
        return selected

    def nas_move_selected(self):
        selected = self._get_selected_items()
        if not selected:
            self._notify(tr("Keine Auswahl"), tr("Bitte wählen Sie mindestens ein Medium zum Verschieben aus."))
            return
        self._start_nas_upload(selected)

    def nas_move_all(self):
        if self.nas_items:
            self._start_nas_upload(self.nas_items)

    def _start_nas_upload(self, items: List[NASUploadItem], skip_confirmation: bool = False):
        active = self.active_category_folders()
        unreachable = [f"{c}: {p}" for c, p in active.items() if not Path(p).exists()]
        if not active or unreachable:
            grund = (tr("kein Zielordner eingestellt") if not active
                     else tr("nicht erreichbar: {list}").format(list=" | ".join(unreachable)))
            if skip_confirmation:
                self.log(f"❌ Automatischer Upload abgebrochen - {grund}")
                self._toast_error(tr("Upload nicht möglich"), grund)
            else:
                self._notify(tr("Upload nicht möglich"), tr("Der Upload kann nicht starten:\n\n{reason}").format(reason=grund))
            return

        if self.nas_delete_check.isChecked() and not skip_confirmation:
            if not self._confirm(
                tr("Bestätigung"),
                tr("Sie haben 'Lokale Ordner löschen' aktiviert.\n\n{count} Ordner werden nach "
                   "erfolgreich verifiziertem Kopieren gelöscht.\n\nFortfahren?").format(count=len(items)),
            ):
                return

        self.nas_move_selected_btn.setEnabled(False)
        self.nas_move_all_btn.setEnabled(False)
        self.nas_stop_btn.setEnabled(True)
        self.nas_scan_btn.setEnabled(False)

        # Der Worker zählt seine Indizes über die ihm übergebene Liste. Bei
        # tr("Ausgewählte verschieben") ist das eine Teilmenge von self.nas_items,
        # die Tabellenzeilen richten sich aber nach self.nas_items - ohne diese
        # Übersetzung landete der Fortschritt auf der falschen Zeile.
        self._nas_row_for_worker_idx = {}
        for worker_idx, item in enumerate(items):
            for row, known in enumerate(self.nas_items):
                if known is item:
                    self._nas_row_for_worker_idx[worker_idx] = row
                    break

        delete_after = self.nas_delete_check.isChecked()
        self.nas_worker = NASUploadWorker(items, self.active_category_folders(), delete_after)
        self.nas_worker.progress_updated.connect(self.on_nas_progress_updated)
        self.nas_worker.item_completed.connect(self.on_nas_item_completed)
        self.nas_worker.total_progress_updated.connect(self.nas_progress.setValue)
        self.nas_worker.log_message.connect(self.log)
        self.nas_worker.all_completed.connect(self.on_nas_all_completed)

        self.log(f"📤 Starte NAS-Upload für {len(items)} Medien...")
        self.nas_worker.start()

    def nas_stop_upload(self):
        if self.nas_worker:
            self.nas_worker.stop()
            self.log("⏹️ NAS-Upload wird gestoppt...")

    def _nas_row_for(self, worker_idx: int) -> Optional[int]:
        """Übersetzt den Index des Workers (Position in der übergebenen Teilmenge)
        in die zugehörige Tabellenzeile (Position in self.nas_items)."""
        row = self._nas_row_for_worker_idx.get(worker_idx)
        return row if row is not None and 0 <= row < len(self.nas_items) else None

    # Endzustände, die kein Fortschrittssignal mehr überschreiben darf.
    _NAS_FINAL_STATES = (
        NASUploadStatus.FERTIG, NASUploadStatus.FEHLER, NASUploadStatus.UEBERSPRUNGEN,
    )

    def on_nas_progress_updated(self, idx: int, progress: int, message: str):
        row = self._nas_row_for(idx)
        if row is not None:
            item = self.nas_items[row]
            # Nicht überschreiben, wenn der Worker schon einen Endzustand gesetzt hat.
            # Er setzt FERTIG und sendet ERST DANACH "100 % - Fertig"; dieser Slot läuft
            # aber verzögert im GUI-Thread und hat den Status bisher wieder auf
            # "Wird verschoben" zurückgedreht. Am Ende stand deshalb bei jedem Medium
            # ein Zwischenzustand - und die Abschlussmeldung zählte tr("Erfolgreich: 0"),
            # obwohl alles korrekt auf dem NAS gelandet war.
            if item.status not in self._NAS_FINAL_STATES:
                item.status = NASUploadStatus.WIRD_VERSCHOBEN

            status_item = self.nas_table.item(row, 5)
            if status_item:
                status_item.setText(f"{progress}% - {message[:30]}")
                status_item.setForeground(QColor(theme.semantic_colors()["accent"]))

            self.nas_current_label.setText(f"{item.name}: {message}")

    def on_nas_item_completed(self, idx: int, success: bool, message: str):
        row = self._nas_row_for(idx)
        if row is not None:
            colors = theme.semantic_colors()
            status_item = self.nas_table.item(row, 5)
            if status_item:
                if success:
                    status_item.setText(tr("Fertig"))
                    status_item.setForeground(QColor(colors["success"]))
                else:
                    status_item.setText(tr("Fehler"))
                    status_item.setForeground(QColor(colors["error"]))
                    status_item.setToolTip(message)

    def on_nas_all_completed(self):
        self.nas_move_selected_btn.setEnabled(True)
        self.nas_move_all_btn.setEnabled(True)
        self.nas_stop_btn.setEnabled(False)
        self.nas_scan_btn.setEnabled(True)
        self.nas_current_label.setText("")

        completed = sum(1 for item in self.nas_items if item.status == NASUploadStatus.FERTIG)
        failed = sum(1 for item in self.nas_items if item.status == NASUploadStatus.FEHLER)

        # Die Liste zeigt, was lokal auf das Verschieben wartet. Nach einem Lauf
        # stimmt sie nicht mehr: verschobene Ordner sind weg, stehen aber weiter
        # da. Neu einlesen statt Einträge zu entfernen - so bleiben Ordner
        # sichtbar, die bewusst liegenbleiben (wenn "lokal löschen" aus ist)
        # oder deren Verschieben fehlgeschlagen ist.
        self._refresh_library_after_upload(completed)

        self.log(f"\n{'=' * 50}\nNAS-Upload abgeschlossen!\n✅ Erfolgreich: {completed}\n❌ Fehlgeschlagen: {failed}\n{'=' * 50}\n")

        if failed > 0:
            self.notify_system(
                tr("Verschieben mit Fehlern"),
                tr("{done} verschoben, {failed} fehlgeschlagen. Lokale Ordner bleiben erhalten.")
                .format(done=completed, failed=failed),
                warning=True,
            )
            self._toast_warning(tr("Upload mit Fehlern"), tr("{count} Medium/Medien konnten nicht verschoben werden.").format(count=failed))
        else:
            self.notify_system(
                tr("Verschieben abgeschlossen"),
                tr("{count} Medium/Medien in die Mediathek verschoben.").format(count=completed),
            )
            self._toast_success(tr("Upload abgeschlossen"), tr("{count} Medium/Medien erfolgreich verschoben.").format(count=completed))

        if self._shutdown_after_nas_upload:
            self._shutdown_after_nas_upload = False
            ShutdownCountdownDialog(self).exec_()

    def _trigger_auto_nas_upload(self):
        """Wird nach automatisch abgeschlossener Konvertierung aufgerufen, wenn
        'Nach Abschluss automatisch auf NAS verschieben' aktiv ist - scannt den
        gerade benutzten Zielordner und verschiebt alles Gefundene, ohne auf eine
        Bestätigung zu warten (die 'Lokale Ordner löschen'-Bestätigung eingeschlossen,
        da der Nutzer mit dieser Option bereits explizit beidem zugestimmt hat)."""
        target = self.target_input.text().strip()
        if not target:
            return
        if not self.nas_source_input.text().strip():
            self.nas_source_input.setText(target)

        self.scan_converted_folder()
        if not self.nas_items:
            self.log("📤 Automatischer NAS-Upload: keine Medien im Converted-Ordner gefunden.")
            return

        self.log(f"📤 Automatischer NAS-Upload nach Abschluss gestartet ({len(self.nas_items)} Medien)...")
        # Direkt auf die NAS-Seite wechseln: der Upload läuft unbeaufsichtigt los,
        # also soll man den Fortschritt sofort sehen statt ihn suchen zu müssen.
        self.switchTo(self.nas_page)
        self._start_nas_upload(self.nas_items, skip_confirmation=True)

    # =========================================================================
    # Allgemeine Hilfsmethoden
    # =========================================================================

    def check_ffmpeg(self):
        """Prüft die Voraussetzungen und protokolliert das Ergebnis.

        Der sichtbare Hinweis kommt getrennt über _warn_about_missing_requirements(),
        damit kein modaler Dialog erscheint, bevor das Hauptfenster überhaupt steht."""
        self.log("Prüfe FFmpeg und NVENC...")
        self._ffmpeg_available = self.ffmpeg.is_available()

        if self._ffmpeg_available:
            self.log("✅ FFmpeg gefunden")
        else:
            self.log("⚠️ FFmpeg nicht gefunden! Bitte installieren.")

        self._refresh_encoder_availability()
        if self.encoder_available:
            self.log("✅ Gewählte(r) Encoder verfügbar")
        else:
            self.log("⚠️ Mindestens ein gewählter Encoder nicht verfügbar! Passende NVIDIA-GPU erforderlich.")

    def _offer_ffmpeg_download(self) -> bool:
        """Bietet an, FFmpeg zu holen. Gibt zurück, ob es danach da ist."""
        if not ask_to_download(self):
            self.log(tr("FFmpeg-Download abgelehnt."))
            return False

        dialog = FFmpegDownloadDialog(self)
        if dialog.exec() and dialog.result_path:
            # Prozessor neu aufbauen, damit er die frisch abgelegten Programme sieht.
            self.ffmpeg = FFmpegProcessor()
            self._ffmpeg_available = self.ffmpeg.is_available()
            if self._ffmpeg_available:
                self.log(tr("FFmpeg eingerichtet: {path}").format(path=dialog.result_path))
                self._refresh_encoder_availability()
                self._update_start_button_state()
                return True

        if dialog.error:
            self._notify(tr("FFmpeg-Download fehlgeschlagen"), describe_failure(dialog.error))
        else:
            self.log(tr("FFmpeg-Download abgebrochen."))
        return False

    def _warn_about_missing_requirements(self):
        """Hinweis auf fehlende Voraussetzungen, nachdem das Fenster steht."""
        if not getattr(self, "_ffmpeg_available", True):
            if not self._offer_ffmpeg_download():
                self._notify(
                    tr("FFmpeg fehlt"),
                    tr("FFmpeg wurde nicht gefunden.\n\nBitte installieren Sie FFmpeg und stellen Sie "
                       "sicher, dass es im System-PATH verfügbar ist.")
                )

        gpu = self.gpu_info
        if not gpu.is_supported:
            # Die konkret verbaute Karte mit nennen - "keine NVIDIA-GPU gefunden"
            # allein lässt offen, ob die App bloß nichts erkannt hat.
            found = gpu.name or tr("keine Grafikkarte erkannt")
            self._notify(
                tr("Grafikkarte nicht unterstützt"),
                tr("Gefunden: {found}\n\nAmboss kodiert über NVIDIA NVENC und "
                   "benötigt dafür eine NVIDIA-Grafikkarte. Encoder von AMD und "
                   "Intel sind derzeit nicht eingebaut.").format(found=found)
            )
        elif not gpu.supports_av1:
            self._notify(
                tr("AV1 auf dieser Grafikkarte nicht möglich"),
                tr("{name} kann AV1 zwar abspielen, aber nicht erzeugen. Dafür "
                   "wird mindestens eine GeForce RTX der 4000er-Reihe benötigt."
                   "\n\nH.265 und H.264 funktionieren auf dieser Karte. H.265 "
                   "erzeugt deutlich kleinere Dateien und ist die bessere Wahl, "
                   "solange die Abspielgeräte es beherrschen.").format(name=gpu.name)
            )

    def _on_container_changed(self):
        """Der Container bestimmt die Endung der Zieldateien - bereits gescannte
        Einträge müssen deshalb neu berechnet werden.

        Ohne das zeigte die Liste weiterhin die alten Pfade, und die
        Kollisionsauflösung liefe gegen Dateien, die so gar nicht entstehen."""
        if not getattr(self, "_ui_ready", False) or not self.videos:
            return

        container = self.container_combo.currentData() or DEFAULT_CONTAINER
        target_path = Path(self.target_input.text().strip() or ".")
        rename_enabled = self.rename_check.isChecked()
        category_folders = self.settings.get("category_folders") or {}
        season_pattern = self.current_season_pattern()

        for video in self.videos:
            video.target_path = PathGenerator.generate(
                video, target_path, rename_enabled, category_folders,
                season_pattern, container)
            if video.status == FileStatus.UEBERSPRUNGEN and not video.target_path.exists():
                video.status = FileStatus.WARTEND
            elif video.status == FileStatus.WARTEND and video.target_path.exists():
                video.status = FileStatus.UEBERSPRUNGEN

        PathGenerator.resolve_collisions(self.videos)
        self.update_file_table()
        self.update_details_tree()

    def _update_encoder_hint(self):
        """Setzt den Hinweis unter dem Zähler für parallele Tasks.

        Bewusst kein Deckel auf die Zahl: über der Einheitenzahl steigt der
        Durchsatz messbar weiter, nur eben kaum noch. Diese Abwägung gehört dem
        Nutzer, die App liefert dafür bloß die Tatsachen."""
        hint = getattr(self, "encoder_hint", None)
        if hint is None:
            return

        units = self.gpu_info.encoder_units
        if not self.gpu_info.is_supported or units is None:
            hint.setText("")
            hint.setVisible(False)
            return

        hint.setVisible(True)
        # Eigene Texte für den Einzahl-Fall statt "1 Encoder-Einheiten".
        if self.parallel_spin.value() <= units:
            template = ("Deine Grafikkarte hat eine Encoder-Einheit." if units == 1
                        else "Deine Grafikkarte hat {units} Encoder-Einheiten.")
            hint.setTextColor(QColor(120, 120, 120), QColor(150, 150, 150))
        else:
            template = (
                "Deine Grafikkarte hat nur eine Encoder-Einheit. Mehr "
                "gleichzeitige Tasks bringen kaum noch Mehrleistung."
                if units == 1 else
                "Deine Grafikkarte hat nur {units} Encoder-Einheiten. Mehr "
                "gleichzeitige Tasks bringen dann kaum noch Mehrleistung.")
            hint.setTextColor(QColor(191, 122, 0), QColor(255, 190, 80))
        hint.setText(tr(template).format(units=units))

    def _update_start_button_state(self):
        self.start_btn.setEnabled(bool(self.videos) and self.encoder_available)

    def log(self, message: str):
        self.log_page.append(message)
        logger.info(message)

    def update_crf_label(self, value: int, label: Optional[CaptionLabel] = None,
                         codec: Optional[str] = None):
        """Beschriftet den Qualitätsregler - mit der Obergrenze des Codecs.

        Ohne die Grenze wäre nicht zu sehen, dass dieselbe Zahl je nach Codec
        etwas anderes bedeutet: AV1 rechnet auf einer Skala bis 63, H.265 und
        H.264 nur bis 51. Wer den Codec wechselt, bekäme sonst unbemerkt eine
        andere Qualität, obwohl der Regler unverändert steht."""
        if codec is None:
            codec = self.codec_combo.currentData() if hasattr(self, "codec_combo") else None
        grenze = cq_maximum_for(codec or DEFAULT_CODEC)
        (label or self.crf_label).setText(
            tr("CQ {value}/{max} · {description}").format(
                value=value, max=grenze, description=tr(get_cq_description(value))))

    def browse_source(self):
        start_dir = self.source_input.text().strip() or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(self, tr("Quellordner auswählen"), start_dir)
        if folder:
            folder = os.path.normpath(folder)
            self.source_input.setText(folder)
            self.on_source_changed(folder)
            self._on_convert_control_changed()

    def browse_target(self):
        folder = QFileDialog.getExistingDirectory(
            self, tr("Zielordner auswählen"), self.target_input.text() or os.path.expanduser("~")
        )
        if folder:
            self.target_input.setText(folder)
            self._on_convert_control_changed()

    def on_source_changed(self, path: str):
        if not self.target_input.text():
            self.target_input.setText(os.path.join(path, DEFAULT_OUTPUT_FOLDER))

    def apply_filter(self, filter_type: str):
        self.current_filter = filter_type
        for key, btn in self._filter_buttons.items():
            btn.setChecked(key == filter_type)

        for row in range(self.file_table.rowCount()):
            show = True
            if row < len(self.videos):
                video = self.videos[row]
                if filter_type == "waiting":
                    show = video.status == FileStatus.WARTEND
                elif filter_type == "processing":
                    show = video.status == FileStatus.VERARBEITET
                elif filter_type == "done":
                    show = video.status in (FileStatus.FERTIG, FileStatus.UEBERSPRUNGEN)
                elif filter_type == "error":
                    show = video.status == FileStatus.FEHLER
            self.file_table.setRowHidden(row, not show)

    def clear_file_list(self):
        if self.worker and self.worker.isRunning():
            self._notify(tr("Warnung"), tr("Die Liste kann nicht geleert werden, während eine Konvertierung läuft."))
            return

        completed = sum(1 for v in self.videos if v.status in (FileStatus.FERTIG, FileStatus.FEHLER))
        if completed > 0:
            if not self._confirm(tr("Liste leeren"), tr("Es wurden {count} Dateien verarbeitet.\n\nMöchten Sie die Liste wirklich leeren?")
                    .format(count=completed)):
                return

        self.videos.clear()
        self.file_table.setRowCount(0)
        self.details_tree.clear()
        self.total_progress.setValue(0)
        self.update_statistics()
        self.update_total_progress()
        self._update_queue_labels()
        self._update_start_button_state()
        self.clear_list_btn.setEnabled(False)
        self.log("📋 Dateiliste geleert")

    def _cleanup_stale_temp_files(self, target_path: Path):
        """Entfernt liegengebliebene '.name.tmp.<endung>'-Dateien im Zielordner.

        Bricht die App während eines Encodes ab (Absturz, Stromausfall), bleibt die
        angefangene Temp-Datei zurück. Sie ist wertlos - der Zielpfad entsteht erst
        beim atomaren Umbenennen - belegt aber Platz und verwirrt beim Nachschauen.

        Gesucht wird über alle Container hinweg: wer die Einstellung wechselt,
        soll auch die Reste des vorherigen Durchlaufs loswerden."""
        if not target_path.is_dir():
            return
        removed = 0
        for stale in target_path.rglob(".*.tmp.*"):
            try:
                stale.unlink()
                removed += 1
            except OSError:
                pass
        if removed:
            self.log(f"🧹 {removed} abgebrochene Zwischendatei(en) aus einem früheren Lauf entfernt")

    def _update_queue_labels(self):
        """Hält die Kopfzeile der Warteschlange und die Zusammenfassungen auf den
        Quelle-/Ziel-Karten synchron."""
        total = len(self.videos)
        if not total:
            self.stats_label.setText(tr("Warteschlange"))
            self.source_summary_label.setText(tr("Noch nicht gescannt"))
            self.target_summary_label.setText(tr("Noch nichts konvertiert"))
            return

        skipped = sum(1 for v in self.videos if v.status == FileStatus.UEBERSPRUNGEN)
        if skipped:
            self.stats_label.setText(tr("Warteschlange · {count} Dateien · {skipped} übersprungen")
                                     .format(count=total, skipped=skipped))
        else:
            self.stats_label.setText(tr("Warteschlange · {count} Dateien").format(count=total))

        total_before = sum(v.original_size for v in self.videos)
        self.source_summary_label.setText(
            tr("{count} Dateien · {size}").format(count=total, size=self.format_size(total_before))
        )

        done = [v for v in self.videos if v.new_size > 0]
        if done:
            self.target_summary_label.setText(
                tr("{count} konvertiert · {size}").format(
                    count=len(done), size=self.format_size(sum(v.new_size for v in done)))
            )
        else:
            self.target_summary_label.setText(tr("Noch nichts konvertiert"))

    def scan_files(self):
        """Startet den Scan. Die Arbeit selbst passiert im ScanWorker.

        Vorher lief alles hier, im Oberflächen-Thread - das Fenster fror für die
        Dauer ein, ohne jede Rückmeldung. Die teuren Schritte liegen auf dem
        Netzlaufwerk und dauern damit ein Vielfaches der reinen Rechenzeit."""
        if self.scan_worker and self.scan_worker.isRunning():
            return

        source = self.source_input.text().strip()

        if not source:
            self._notify(
                tr("Fehler"),
                tr("Bitte wählen Sie einen gültigen Quellordner.\n\nHinweis: Ziehen Sie einen "
                   "Ordner auf das 'Quelle:'-Feld oder klicken Sie auf 'Durchsuchen...' neben "
                   "dem Quelle-Feld.")
            )
            return

        source = os.path.normpath(source)
        if not os.path.isdir(source):
            self._notify(tr("Fehler"), tr("Der angegebene Quellordner ist ungültig oder existiert nicht:\n\n{path}").format(path=source))
            return

        self.log(f"Scanne Ordner: {source}")
        self.videos.clear()
        self.update_file_table()

        source_path = Path(source)
        target = self.target_input.text().strip()
        if not target:
            target = str(source_path / DEFAULT_OUTPUT_FOLDER)
            self.target_input.setText(target)
        target_path = Path(target).resolve()

        ignored_folders = [target_path, (source_path / DEFAULT_OUTPUT_FOLDER).resolve(),
                           (target_path / "_Unknown_Format").resolve()]

        self._set_scan_running(True)

        self.scan_worker = ScanWorker(
            source_path=source_path,
            target_path=Path(target),
            rename_enabled=self.rename_check.isChecked(),
            enabled_categories=list(self.active_category_folders()),
            category_folders=self.settings.get("category_folders") or {},
            # Bereits Ermitteltes weiterreichen: das Ablesen der Staffel-Benennung
            # aus der Mediathek ist der teuerste Schritt überhaupt (bis zu 60
            # Serienordner je Kategorie, einzeln über das Netz). Vor dem Umbau
            # geschah das einmal je Sitzung; ohne diese Zeile bei JEDEM Scan neu.
            configured_season_pattern=(
                (self.settings.get("season_folder_pattern") or "").strip()
                or self._detected_season_pattern
                or (self.settings.get("detected_season_pattern") or "").strip()),
            ffmpeg=self.ffmpeg,
            ignored_folders=ignored_folders,
            container=self.container_combo.currentData() or DEFAULT_CONTAINER,
        )
        self.scan_worker.progress.connect(self._on_scan_progress)
        self.scan_worker.log_message.connect(self.log)
        self.scan_worker.finished_ok.connect(self._on_scan_finished)
        self.scan_worker.failed.connect(self._on_scan_failed)
        self.scan_worker.start()

    def _set_scan_running(self, running: bool):
        """Sperrt die Bedienelemente, die während eines Scans nicht passen,
        und blendet die Fortschrittsanzeige ein bzw. aus."""
        self.scan_btn.setEnabled(not running)
        self.clear_list_btn.setEnabled(not running and bool(self.videos))
        self.scan_spinner.setVisible(running)
        self.scan_status_label.setVisible(running)
        if running:
            self.start_btn.setEnabled(False)
            self.scan_status_label.setText(tr("Scannt..."))
        else:
            self.scan_status_label.setText("")

    def _on_scan_progress(self, done: int, total: int, message: str):
        # Neben dem Ring auch benennen, woran gerade gearbeitet wird - gerade
        # beim Lesen der Mediathek dauert ein einzelner Schritt am längsten.
        if total and done:
            text = tr("{done} von {total}").format(done=done, total=total)
            if message:
                text = f"{text} · {message}"
        else:
            text = message or tr("Scannt...")
        self.scan_status_label.setText(text)

        if total:
            self.stats_label.setText(
                tr("Scannt... {done} von {total}").format(done=done, total=total))

    def _on_scan_failed(self, message: str):
        self._set_scan_running(False)
        self._update_queue_labels()
        self._notify(tr("Scan fehlgeschlagen"),
                     tr("Der Ordner konnte nicht gelesen werden:\n\n{error}").format(error=message))

    def _on_scan_finished(self, result):
        """Übernimmt das Ergebnis des Workers in die Oberfläche."""
        self._set_scan_running(False)

        if result.ignored_count:
            self.log(f"Gefunden: {len(result.videos)} Dateien "
                     f"({result.ignored_count} ignoriert im Output-Ordner)")
        else:
            self.log(f"Gefunden: {len(result.videos)} Dateien")

        for line in result.log_lines:
            self.log(line)

        self._redundant_duplicates = result.redundant_duplicates
        if self._redundant_duplicates:
            self.log(
                f"   {len(self._redundant_duplicates)} doppelte(r) Download wird beim Start der "
                "Konvertierung gelöscht (Scannen allein ändert nichts)."
            )

        # Dauerhaft merken, nicht nur für diese Sitzung: das Ablesen kostet auf
        # einer Mediathek im Netz mehrere Sekunden und ergibt jedes Mal
        # dasselbe. Geleert wird der Wert, sobald die Kategorie-Ordner wechseln.
        if result.season_pattern and result.season_pattern != self._detected_season_pattern:
            self._detected_season_pattern = result.season_pattern
            self.settings.set("detected_season_pattern", result.season_pattern)
            self.settings.save()
        self.videos = result.videos

        # Erst jetzt, nachdem der Scan durch ist: das Aufräumen liegengebliebener
        # Temp-Dateien durchsucht den Zielordner rekursiv und hat mit dem
        # Ergebnis des Scans nichts zu tun.
        self._cleanup_stale_temp_files(Path(self.target_input.text().strip() or "."))

        self.update_file_table()
        self.update_details_tree()
        self.update_statistics()
        self.update_total_progress()
        self._update_queue_labels()

        self._update_start_button_state()
        self.clear_list_btn.setEnabled(bool(self.videos))

    def update_file_table(self):
        colors = theme.semantic_colors()
        self.file_table.setRowCount(len(self.videos))

        for row, video in enumerate(self.videos):
            self.file_table.setItem(row, 0, QTableWidgetItem(video.source_path.name))
            type_item = QTableWidgetItem(tr(video.media_type.value))
            type_item.setTextAlignment(Qt.AlignCenter)
            self.file_table.setItem(row, 1, type_item)

            status_item = QTableWidgetItem(tr(video.status.value))
            status_item.setTextAlignment(Qt.AlignCenter)
            status_colors = {
                FileStatus.WARTEND: colors["neutral"], FileStatus.VERARBEITET: colors["accent"],
                FileStatus.FERTIG: colors["success"], FileStatus.FEHLER: colors["error"],
                FileStatus.UEBERSPRUNGEN: colors["neutral"], FileStatus.PAUSIERT: colors["warning"],
            }
            status_item.setForeground(QColor(status_colors.get(video.status, colors["neutral"])))
            self.file_table.setItem(row, 2, status_item)

            progress_bar = ProgressBar()
            progress_bar.setValue(video.progress)
            self.file_table.setCellWidget(row, 3, progress_bar)

            target_text = str(video.target_path) if video.target_path else "-"
            self.file_table.setItem(row, 4, QTableWidgetItem(target_text))

            remove_btn = TransparentToolButton(FluentIcon.CLOSE)
            remove_btn.setToolTip(tr("Aus der Warteschlange entfernen"))
            remove_btn.setFixedSize(28, 28)
            remove_btn.clicked.connect(lambda _c=False, v=video: self._remove_video(v))
            self.file_table.setCellWidget(row, 5, remove_btn)

        self._update_remove_buttons_enabled()
        self.apply_filter(self.current_filter)

    def _update_remove_buttons_enabled(self):
        """Während eines laufenden Laufs darf nichts entfernt werden - die
        Worker adressieren ihre Dateien über den Listenindex, ein Verschieben
        der Indizes mitten im Lauf würde Fortschritt auf die falsche Zeile schreiben."""
        running = bool(self.worker and self.worker.isRunning())
        for row in range(self.file_table.rowCount()):
            widget = self.file_table.cellWidget(row, 5)
            if widget is not None:
                widget.setEnabled(not running)

    def _remove_video(self, video: VideoFile):
        if self.worker and self.worker.isRunning():
            return
        self.videos = [v for v in self.videos if v is not video]
        self.log(f"➖ Aus der Warteschlange entfernt: {video.source_path.name}")
        self.update_file_table()
        self.update_details_tree()
        self.update_statistics()
        self.update_total_progress()
        self._update_queue_labels()
        self._update_start_button_state()
        self.clear_list_btn.setEnabled(bool(self.videos))

    def update_details_tree(self):
        colors = theme.semantic_colors()
        self.details_tree.clear()

        total_original = 0
        total_new = 0

        for video in self.videos:
            item = QTreeWidgetItem()
            item.setText(0, video.source_path.name)
            item.setText(1, self.format_size(video.original_size))
            total_original += video.original_size

            if video.new_size > 0:
                item.setText(2, self.format_size(video.new_size))
                total_new += video.new_size
                savings = ((video.original_size - video.new_size) / video.original_size) * 100
                if savings > 0:
                    item.setText(3, f" {savings:.1f}%")
                    item.setForeground(3, QColor(colors["success"]))
                else:
                    item.setText(3, f" {abs(savings):.1f}%")
                    item.setForeground(3, QColor(colors["error"]))
            else:
                item.setText(2, "-")
                item.setText(3, "-")

            item.setText(4, video.status.value)
            status_colors = {
                FileStatus.WARTEND: colors["neutral"], FileStatus.VERARBEITET: colors["accent"],
                FileStatus.FERTIG: colors["success"], FileStatus.FEHLER: colors["error"],
                FileStatus.UEBERSPRUNGEN: colors["neutral"],
            }
            item.setForeground(4, QColor(status_colors.get(video.status, colors["neutral"])))

            item.setData(0, Qt.UserRole, video)
            item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
            self.details_tree.addTopLevelItem(item)

        self.total_original_label.setText(tr("Originalgröße: {size}").format(size=self.format_size(total_original)))
        self.total_new_label.setText(tr("Neue Größe: {size}").format(size=self.format_size(total_new)))
        if total_original > 0 and total_new > 0:
            total_savings = ((total_original - total_new) / total_original) * 100
            self.total_savings_label.setText(
                tr("Gesamtersparnis: {percent}% ({size})").format(
                    percent=f"{total_savings:.1f}", size=self.format_size(total_original - total_new))
            )

    def on_details_item_clicked(self, item: QTreeWidgetItem, _column: int):
        if item.parent() is not None:
            return

        video: VideoFile = item.data(0, Qt.UserRole)
        if not video:
            return

        if item.childCount() > 0:
            item.takeChildren()
            return

        self._add_detail_children(item, video)
        item.setExpanded(True)

    def _add_detail_children(self, parent: QTreeWidgetItem, video: VideoFile):
        colors = theme.semantic_colors()
        src_meta = video.source_metadata or VideoMetadata()
        tgt_meta = self.ffmpeg.get_video_metadata(video.target_path) if video.target_path and video.target_path.exists() else None

        details = [
            ("Video-Codec", src_meta.video_codec or "-", tgt_meta.video_codec if tgt_meta else "-"),
            ("Audio-Codec", src_meta.audio_codec or "-", tgt_meta.audio_codec if tgt_meta else "-"),
            (tr("Auflösung"), src_meta.resolution or "-", tgt_meta.resolution if tgt_meta else "-"),
            ("Video-Bitrate", src_meta.video_bitrate or "-", tgt_meta.video_bitrate if tgt_meta else "-"),
            ("Audio-Bitrate", src_meta.audio_bitrate or "-", tgt_meta.audio_bitrate if tgt_meta else "-"),
            (tr("Dauer"), src_meta.duration or "-", tgt_meta.duration if tgt_meta else "-"),
        ]
        for label, before, after in details:
            child = QTreeWidgetItem()
            child.setText(0, f"    {label}")
            child.setText(1, str(before))
            child.setText(2, str(after))
            child.setForeground(0, QColor(colors["neutral"]))
            parent.addChild(child)

        meta_header = QTreeWidgetItem()
        meta_header.setText(0, tr("Metadaten"))
        meta_header.setForeground(0, QColor(colors["accent"]))
        parent.addChild(meta_header)

        meta_details = [
            ("Title", src_meta.title or "(nicht gesetzt)", tgt_meta.title if tgt_meta and tgt_meta.title else "-"),
            ("Show/Serie", src_meta.show_name or "(nicht gesetzt)", tgt_meta.show_name if tgt_meta and tgt_meta.show_name else "-"),
            ("Staffel", src_meta.season or "(nicht gesetzt)", tgt_meta.season if tgt_meta and tgt_meta.season else "-"),
            ("Episode", src_meta.episode or "(nicht gesetzt)", tgt_meta.episode if tgt_meta and tgt_meta.episode else "-"),
        ]
        for label, before, after in meta_details:
            child = QTreeWidgetItem()
            child.setText(0, f"        {label}")
            child.setText(1, str(before))
            child.setText(2, str(after))
            child.setForeground(0, QColor(colors["neutral"]))
            parent.addChild(child)

        if video.conversion_start_time and video.conversion_end_time:
            duration = video.conversion_end_time - video.conversion_start_time
            conv_child = QTreeWidgetItem()
            conv_child.setText(0, "Konvertierungsdauer")
            conv_child.setText(1, f"{int(duration // 60):02d}:{int(duration % 60):02d}")
            conv_child.setForeground(0, QColor(colors["neutral"]))
            parent.addChild(conv_child)

        if video.error_message:
            error_child = QTreeWidgetItem()
            error_child.setText(0, tr("Fehler"))
            error_child.setText(1, video.error_message[:100])
            error_child.setForeground(0, QColor(colors["error"]))
            error_child.setForeground(1, QColor(colors["error"]))
            parent.addChild(error_child)

    def update_statistics(self):
        total = len(self.videos)
        success = sum(1 for v in self.videos if v.status == FileStatus.FERTIG)
        errors = sum(1 for v in self.videos if v.status == FileStatus.FEHLER)

        total_before = sum(v.original_size for v in self.videos)

        self.stat_total_label.setText(tr("Gesamt: {count}").format(count=total))
        self.stat_success_label.setText(tr("Erfolgreich: {count}").format(count=success))
        self.stat_error_label.setText(tr("Fehler: {count}").format(count=errors))
        self.stat_size_before_label.setText(tr("Vorher: {size}").format(size=self.format_size(total_before)))

        # "Nachher"/tr("Ersparnis") erst zeigen, wenn der Lauf fertig ist - während
        # der Konvertierung wäre "alle Originalgrößen" gegen "nur die bisher
        # fertigen Dateien" verglichen worden, was absurd niedrige
        # Zwischenstände ergab (z.B. 20GB -> ein paar MB nach der ersten Datei).
        if self.worker and self.worker.isRunning():
            self.stat_size_after_label.setText(tr("Nachher: läuft noch..."))
            self.stat_savings_label.setText(tr("Ersparnis: läuft noch..."))
            return

        total_after = sum(v.new_size for v in self.videos if v.new_size > 0)
        self.stat_size_after_label.setText(tr("Nachher: {size}").format(size=self.format_size(total_after)))

        if total_before > 0 and total_after > 0:
            savings_pct = ((total_before - total_after) / total_before) * 100
            self.stat_savings_label.setText(
                tr("Ersparnis: {value}").format(
                    value=f"{savings_pct:.1f}% ({self.format_size(total_before - total_after)})")
            )
        else:
            self.stat_savings_label.setText(tr("Ersparnis: -"))

    @staticmethod
    def format_size(size_bytes: int) -> str:
        if size_bytes == 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        unit_index = 0
        size = float(size_bytes)
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1
        return f"{size:.2f} {units[unit_index]}"

    def _review_media_types_before_start(self) -> bool:
        """Zeigt vor dem Start eine editierbare Übersicht der erkannten
        Kategorien, wenn automatischer NAS-Upload aktiv ist - eine falsch
        erkannte Kategorie (z.B. Anime-Film als Film) würde sonst unbemerkt im
        falschen Zielordner landen. Gibt False zurück, wenn abgebrochen wurde."""
        reviewable = [v for v in self.videos if v.media_type != MediaType.UNBEKANNT]
        if not reviewable:
            return True

        dialog = MediaTypeReviewDialog(reviewable, self)
        if not dialog.exec_():
            return False

        target = self.target_input.text().strip()
        if target:
            target_path = Path(target)
            rename_enabled = self.rename_check.isChecked()
            for video in reviewable:
                video.target_path = PathGenerator.generate(
                    video, target_path, rename_enabled,
                    self.settings.get("category_folders") or {}, self.current_season_pattern())
            PathGenerator.resolve_collisions(self.videos)
            self.update_file_table()

        return True

    def start_conversion(self):
        if not self.videos:
            self._notify(tr("Fehler"), tr("Keine Dateien zum Konvertieren."))
            return

        if not self.encoder_available:
            self._notify(
                tr("Encoder nicht verfügbar"),
                tr("Mindestens einer der gewählten Encoder ist auf diesem System nicht verfügbar. "
                   "Bitte wählen Sie einen anderen Codec oder prüfen Sie Ihre GPU/Treiber.")
            )
            return

        if self.delete_source_check.isChecked():
            if not self._confirm(
                tr("Bestätigung"),
                tr("Sie haben 'Quelle nach Konvertierung löschen' aktiviert.\n\nQuelldateien werden "
                   "nur nach nachweislich erfolgreicher Konvertierung gelöscht.\n\nFortfahren?"),
            ):
                return

        if self._post_nas_enabled():
            if not self._review_media_types_before_start():
                return

        settings = {
            "cq": self.crf_slider.value(),
            "preset": self.preset_combo.currentData() or self.preset_combo.currentText()[:2],
            "codec": self.codec_combo.currentData(),
            "use_separate_presets": self.separate_presets_check.isChecked(),
            "parallel_tasks": self.parallel_spin.value(),
            "container": self.container_combo.currentData(),
            "normalize_audio": self.normalize_check.isChecked(),
            "delete_source_after_convert": self.delete_source_check.isChecked(),
        }
        for bucket in PRESET_BUCKETS:
            settings[f"cq_{bucket}"] = getattr(self, f"crf_slider_{bucket}").value()
            settings[f"preset_{bucket}"] = getattr(self, f"preset_combo_{bucket}").currentData()
            settings[f"codec_{bucket}"] = getattr(self, f"codec_combo_{bucket}").currentData()
        self._save_current_settings()

        source_root = Path(os.path.normpath(self.source_input.text().strip()))
        for line in delete_redundant_duplicates(self._redundant_duplicates):
            self.log(line)
        self._redundant_duplicates = []
        move_log_lines = move_videos_to_inprogress(self.videos, source_root)
        for line in move_log_lines:
            self.log(line)
        if move_log_lines:
            self.update_file_table()

        self.log(
            f"Starte Konvertierung mit Einstellungen: CQ={settings['cq']}, "
            f"Preset={settings['preset']}, Codec={settings['codec']}, Tasks={settings['parallel_tasks']}"
        )

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.pause_btn.setEnabled(True)
        self.scan_btn.setEnabled(False)
        self.clear_list_btn.setEnabled(False)

        self.conversion_start_time = time.time()
        self.completed_files_durations.clear()
        self._resolution_speeds.clear()
        self.eta_timer.start(1000)

        self.worker = ConversionWorker(self.videos, settings)
        self.worker.progress_updated.connect(self.on_progress_updated)
        self.worker.file_completed.connect(self.on_file_completed)
        self.worker.file_started.connect(self.on_file_started)
        self.worker.log_message.connect(self.log)
        self.worker.all_completed.connect(self.on_all_completed)
        self.worker.start()
        self._update_remove_buttons_enabled()

    def toggle_pause(self):
        if not self.worker:
            return
        if self.worker.is_paused():
            self.worker.resume()
            self.pause_btn.setText(tr("Pause"))
            self.log("▶️ Konvertierung fortgesetzt")
        else:
            self.worker.pause()
            self.pause_btn.setText(tr("Fortsetzen"))
            self.log("⏸️ Konvertierung pausiert")

    def stop_conversion(self):
        if self.worker:
            self.log("Stoppe Konvertierung...")
            self.worker.stop()

    def on_file_started(self, file_index: int):
        if 0 <= file_index < len(self.videos):
            self.videos[file_index].conversion_start_time = time.time()

    def on_progress_updated(self, file_index: int, progress: int, _message: str):
        if 0 <= file_index < len(self.videos):
            self.videos[file_index].progress = progress
            self.videos[file_index].status = FileStatus.VERARBEITET

            progress_bar = self.file_table.cellWidget(file_index, 3)
            if isinstance(progress_bar, ProgressBar):
                progress_bar.setValue(progress)

            status_item = self.file_table.item(file_index, 2)
            if status_item:
                status_item.setText(tr(FileStatus.VERARBEITET.value))
                status_item.setForeground(QColor(theme.semantic_colors()["accent"]))

        self.update_total_progress()

    def on_file_completed(self, file_index: int, success: bool, message: str):
        if 0 <= file_index < len(self.videos):
            colors = theme.semantic_colors()
            video = self.videos[file_index]
            # UEBERSPRUNGEN nicht überschreiben: der Worker setzt das, wenn die
            # Zieldatei schon existierte. Das meldet er als Erfolg, tr("Fertig") wäre
            # hier aber irreführend - konvertiert wurde in diesem Lauf nichts.
            if video.status != FileStatus.UEBERSPRUNGEN:
                video.status = FileStatus.FERTIG if success else FileStatus.FEHLER
            video.conversion_end_time = time.time()

            # Nur echt konvertierte Dateien als Geschwindigkeitsmessung verwenden.
            # Eine übersprungene Datei ist in Millisekunden "fertig" und ergäbe eine
            # absurd hohe Geschwindigkeit, die die ETA aller folgenden Dateien
            # gegen null ziehen würde.
            if (video.status == FileStatus.FERTIG
                    and video.conversion_start_time and video.conversion_end_time):
                wall_time = video.conversion_end_time - video.conversion_start_time
                self.completed_files_durations.append(wall_time)
                self._record_speed_sample(video, wall_time)

            if video.status == FileStatus.UEBERSPRUNGEN:
                video.progress = 100

            if success and video.target_path and video.target_path.exists():
                video.new_size = video.target_path.stat().st_size
                video.target_metadata = self.ffmpeg.get_video_metadata(video.target_path)

            progress_bar = self.file_table.cellWidget(file_index, 3)
            if isinstance(progress_bar, ProgressBar):
                progress_bar.setValue(video.progress)

            status_item = self.file_table.item(file_index, 2)
            if status_item:
                status_item.setText(tr(video.status.value))
                if video.status == FileStatus.UEBERSPRUNGEN:
                    status_item.setForeground(QColor(colors["neutral"]))
                else:
                    status_item.setForeground(QColor(colors["success"] if success else colors["error"]))

            self.update_details_tree()
            self.update_statistics()
            self.update_total_progress()
            self._update_queue_labels()
            self.log(f"{'✅' if success else '❌'} [{video.source_path.name}] {message}")

    def _record_speed_sample(self, video: VideoFile, wall_time: float):
        """Merkt sich, wie viele Video-Sekunden pro Wanduhr-Sekunde diese Auflösung
        auf dieser Maschine/mit diesen Encoding-Einstellungen tatsächlich schafft -
        Grundlage für die Restzeit-Schätzung noch nicht gestarteter Dateien."""
        if wall_time <= 0 or not video.source_metadata or not video.source_metadata.duration_seconds:
            return
        resolution = video.source_metadata.resolution or tr("unbekannt")
        speed = video.source_metadata.duration_seconds / wall_time
        self._resolution_speeds.setdefault(resolution, []).append(speed)

    @staticmethod
    def _pixel_count(resolution: str) -> Optional[int]:
        try:
            w, h = resolution.lower().split("x")
            return int(w) * int(h)
        except (ValueError, AttributeError):
            return None

    def _live_speed_for(self, video: VideoFile) -> Optional[float]:
        """Live-Geschwindigkeit einer GERADE laufenden Datei aus Fortschritt% und
        bisheriger Wanduhrzeit - schon nach wenigen Sekunden verfügbar, lange
        bevor die Datei fertig ist. Braucht keine vorherige Messung im Lauf."""
        if video.status != FileStatus.VERARBEITET or not video.conversion_start_time:
            return None
        if not video.source_metadata or not video.source_metadata.duration_seconds:
            return None
        elapsed = time.time() - video.conversion_start_time
        if elapsed < 5 or video.progress < 1:
            return None  # zu frueh, Encoder-Anlauf kann die ersten Sekunden verzerren
        encoded_video_seconds = video.source_metadata.duration_seconds * (video.progress / 100)
        return encoded_video_seconds / elapsed

    def _any_live_speed(self):
        """(Geschwindigkeit, Pixelzahl) der ersten gerade laufenden Datei mit
        brauchbarer Live-Schätzung, oder None."""
        for video in self.videos:
            speed = self._live_speed_for(video)
            if speed is not None:
                resolution = video.source_metadata.resolution if video.source_metadata else ""
                return speed, self._pixel_count(resolution)
        return None

    def _estimate_speed_for(self, video: VideoFile) -> Optional[float]:
        """Schätzt Video-Sekunden pro Wanduhr-Sekunde für dieses Video:
        1) exakter Messwert, falls diese Auflösung in diesem Lauf schon fertig wurde,
        2) per Pixelzahl von der am besten belegten bekannten Auflösung hochgerechnet,
        3) Live-Geschwindigkeit einer gerade laufenden Datei (ebenfalls pixelskaliert),
        4) None, wenn wirklich noch nichts vorliegt - dann zeigt die ETA lieber
        "Berechne..." statt einer geratenen Zahl. Eine frühere Version nahm hier
        pauschal 1x Echtzeit an, was für NVENC um ein Vielfaches zu langsam war
        (z.B. "2 Stunden" statt tatsächlicher 6 Minuten)."""
        resolution = (video.source_metadata.resolution if video.source_metadata else "") or tr("unbekannt")
        pixels = self._pixel_count(resolution)

        samples = self._resolution_speeds.get(resolution)
        if samples:
            return statistics.mean(samples)

        if pixels and self._resolution_speeds:
            best_resolution = max(self._resolution_speeds, key=lambda r: len(self._resolution_speeds[r]))
            best_pixels = self._pixel_count(best_resolution)
            if best_pixels:
                return statistics.mean(self._resolution_speeds[best_resolution]) * (best_pixels / pixels)

        if self._resolution_speeds:
            all_samples = [s for samples in self._resolution_speeds.values() for s in samples]
            return statistics.mean(all_samples)

        live = self._any_live_speed()
        if live is not None:
            live_speed, live_pixels = live
            if pixels and live_pixels:
                return live_speed * (live_pixels / pixels)
            return live_speed

        return None

    def _compute_batch_eta_seconds(self) -> Optional[float]:
        """Gesamt-ETA für die komplette Warteschlange über alle parallelen Tasks
        hinweg: laufende Dateien gehen mit ihrer per Live-Fortschritt und
        auflösungsbasierter Geschwindigkeit geschätzten Restzeit ein, wartende
        Dateien werden (längste zuerst) dem jeweils nächstfreien "Worker" in einer
        Timeline-Simulation zugeteilt - liefert so eine realistische
        Fertigstellungszeit statt eines rein sequenziellen Worst-Case.

        Gibt None zurück, solange für KEIN Video eine belastbare Geschwindigkeit
        vorliegt (typischerweise nur die ersten ~5 Sekunden nach Start) - dann
        zeigt die UI "Berechne..." statt einer möglicherweise stark falschen Zahl."""
        parallel = max(self.parallel_spin.value(), 1)

        running_remaining = []
        for video in self.videos:
            if video.status != FileStatus.VERARBEITET:
                continue
            duration = video.source_metadata.duration_seconds if video.source_metadata else 0
            if not duration:
                continue
            speed = self._estimate_speed_for(video)
            if speed is None:
                return None
            remaining_video_seconds = duration * (1 - video.progress / 100)
            running_remaining.append(remaining_video_seconds / max(speed, 0.05))

        queued_predictions = []
        for video in self.videos:
            if video.status != FileStatus.WARTEND:
                continue
            duration = video.source_metadata.duration_seconds if video.source_metadata else 0
            if not duration:
                queued_predictions.append(30.0)  # Notfall-Fallback ohne erkannte Länge
                continue
            speed = self._estimate_speed_for(video)
            if speed is None:
                return None
            queued_predictions.append(duration / max(speed, 0.05))

        if not running_remaining and not queued_predictions:
            return None

        worker_timelines = sorted(running_remaining)
        while len(worker_timelines) < parallel:
            worker_timelines.append(0.0)

        for job_time in sorted(queued_predictions, reverse=True):
            worker_timelines.sort()
            worker_timelines[0] += job_time

        return max(worker_timelines)

    def update_eta_display(self):
        if not self.worker or not self.worker.isRunning():
            self.eta_label.setText(tr("Verbleibend: --:--:--"))
            return

        eta_seconds = self._compute_batch_eta_seconds()
        if eta_seconds is None:
            self.eta_label.setText(tr("Verbleibend: Berechne..."))
            return

        hours, rem = divmod(int(eta_seconds), 3600)
        minutes, seconds = divmod(rem, 60)
        self.eta_label.setText(tr("Verbleibend: {time}").format(
            time=f"{hours:02d}:{minutes:02d}:{seconds:02d}"))

    def on_all_completed(self):
        # Muss VOR dem Nullsetzen von self.worker gelesen werden.
        was_stopped = bool(self.worker and self.worker._stop_requested)

        # Erst hier auf None setzen (nicht nur run() beendet, sondern für alle
        # anderen Stellen inkl. update_statistics() wirklich "nicht mehr aktiv") -
        # QThread.isRunning() kann sonst kurz nach dem all_completed-Signal noch
        # True liefern und "Nachher: läuft noch..." würde hier stehen bleiben.
        self.worker = None

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText(tr("Pause"))
        self.scan_btn.setEnabled(True)
        self.clear_list_btn.setEnabled(True)
        self.eta_timer.stop()
        self.eta_label.setText(tr("Verbleibend: --:--:--"))
        self._update_start_button_state()

        completed = sum(1 for v in self.videos if v.status == FileStatus.FERTIG)
        failed = sum(1 for v in self.videos if v.status == FileStatus.FEHLER)

        # Ersparnis-Zusammenfassung mit ins Protokoll - bleibt so auch erhalten,
        # wenn die lokalen Dateien danach automatisch aufs NAS verschoben und
        # gelöscht werden (die Statistik-Leiste selbst geht dann ja mit der
        # nächsten tr("Liste leeren")/App-Neustart verloren, das Protokoll nicht).
        total_before = sum(v.original_size for v in self.videos)
        total_after = sum(v.new_size for v in self.videos if v.new_size > 0)
        savings_line = ""
        if total_before > 0 and total_after > 0:
            savings_pct = ((total_before - total_after) / total_before) * 100
            savings_line = (
                f"\n Ersparnis: {savings_pct:.1f}% "
                f"({self.format_size(total_before)} {self.format_size(total_after)})"
            )

        self.log(
            f"\n{'=' * 50}\nKonvertierung abgeschlossen!\n Erfolgreich: {completed}\n"
            f"Fehlgeschlagen: {failed}{savings_line}\n{'=' * 50}\n"
        )

        self.update_details_tree()
        self.update_statistics()
        self.update_total_progress()
        self._update_queue_labels()
        self._update_remove_buttons_enabled()

        source = self.source_input.text().strip()
        if source:
            prune_empty_inprogress_dirs(Path(os.path.normpath(source)))

        if failed > 0:
            failed_files = [v.source_path.name for v in self.videos if v.status == FileStatus.FEHLER]
            failed_list = "\n".join(f"• {f}" for f in failed_files[:10])
            if len(failed_files) > 10:
                failed_list += f"\n... und {len(failed_files) - 10} weitere"
            self.notify_system(
                tr("Konvertierung mit Fehlern abgeschlossen"),
                tr("{done} erfolgreich, {failed} fehlgeschlagen. Details im Protokoll.")
                .format(done=completed, failed=failed),
                warning=True,
            )
            self._notify(
                tr("Konvertierung mit Fehlern abgeschlossen"),
                tr("{count} Datei(en) konnten nicht konvertiert werden:\n\n{list}\n\n"
                   "Überprüfen Sie das Protokoll für Details.").format(count=failed, list=failed_list)
            )
        else:
            saving_text = savings_line.replace("\n", " ").strip() or ""
            self.notify_system(
                tr("Konvertierung abgeschlossen"),
                tr("{count} Datei(en) fertig konvertiert. {savings}")
                .format(count=completed, savings=saving_text).strip(),
            )
            self._toast_success(tr("Konvertierung abgeschlossen"), tr("{count} Datei(en) erfolgreich konvertiert.").format(count=completed))

        self._check_for_truncated_name_duplicates()

        should_shutdown = self._post_shutdown_enabled() and not was_stopped
        if should_shutdown:
            self._clear_post_shutdown()  # einmalig, kein versehentliches Wiederauslösen

        if self._post_nas_enabled() and not was_stopped and completed > 0:
            self._shutdown_after_nas_upload = should_shutdown
            self._trigger_auto_nas_upload()
        elif should_shutdown:
            ShutdownCountdownDialog(self).exec_()

    def _check_for_truncated_name_duplicates(self):
        """Läuft nach jeder abgeschlossenen Konvertierung; blockiert nie die Konvertierung selbst."""
        target = self.target_input.text().strip()
        if not target:
            return

        target_path = Path(target)
        candidates = []
        for category in NAS_CATEGORIES:
            candidates.extend(find_truncation_candidates(target_path / category))

        if candidates:
            self.log(f"🔎 {len(candidates)} möglicher/mögliche Namens-Duplikat(e) durch Abschneidung gefunden")
            dialog = MergeReviewDialog(candidates, self)
            dialog.exec_()

    def update_total_progress(self):
        if not self.videos:
            self.total_progress_status_label.setText("")
            return
        # Übersprungene Dateien behalten progress=0, zählen aber als erledigt -
        # ohne diese Umrechnung blieb der Balken z.B. bei 66% stehen, während
        # daneben "Fertig (3/3)"stand.
        finished = (FileStatus.FERTIG, FileStatus.UEBERSPRUNGEN)
        avg_progress = sum(
            100 if v.status in finished else v.progress for v in self.videos
        ) // len(self.videos)
        self.total_progress.setValue(avg_progress)

        done = sum(1 for v in self.videos if v.status in finished)
        total = len(self.videos)
        if self.worker and self.worker.isRunning():
            self.total_progress_status_label.setText(tr("In Bearbeitung ({done}/{total})").format(
                done=done, total=total))
        elif done >= total:
            self.total_progress_status_label.setText(tr("Fertig ({done}/{total})").format(done=done, total=total))
        else:
            self.total_progress_status_label.setText(tr("{done}/{total} bereit").format(done=done, total=total))
