from __future__ import annotations

import asyncio
import time
from datetime import datetime, tzinfo
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QThread, QTimer, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .config import (
    executable_dir,
    load_config,
    load_credentials,
    load_settings,
    resolve_path,
    save_credentials,
    save_settings,
)
from .constants import APP_NAME, VERSION
from .estimate import estimate_calls
from .models import ProgressInfo, QuotaInfo, RunSummary
from .runner import ScanCancelled, run_scan
from .theme import DARK, LIGHT, stylesheet


class ScanWorker(QObject):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, **kwargs) -> None:
        super().__init__()
        self.kwargs = kwargs
        self._cancelled = False

    def request_cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        try:
            summary = asyncio.run(
                run_scan(
                    **self.kwargs,
                    progress_callback=self.progress.emit,
                    cancel_requested=lambda: self._cancelled,
                )
            )
        except ScanCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.completed.emit(summary)


class CredentialsDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        client_id: str = "",
        client_secret: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("eBay API credentials")
        self.setModal(True)
        self.setMinimumWidth(470)
        if parent is not None:
            self.setStyleSheet(parent.styleSheet())

        layout = QVBoxLayout(self)
        explanation = QLabel(
            "Enter the production App ID and Cert ID from eBay. They are stored in "
            "Windows Credential Manager and are not shown on the main screen."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        form = QFormLayout()
        self.client_id_input = QLineEdit(client_id)
        self.client_id_input.setPlaceholderText("Client ID / App ID")
        self.client_secret_input = QLineEdit(client_secret)
        self.client_secret_input.setPlaceholderText("Client Secret / Cert ID")
        self.client_secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Client ID", self.client_id_input)
        form.addRow("Client Secret", self.client_secret_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_complete)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_if_complete(self) -> None:
        if not all(self.credentials()):
            QMessageBox.warning(self, APP_NAME, "Enter both the Client ID and Client Secret.")
            return
        self.accept()

    def credentials(self) -> tuple[str, str]:
        return self.client_id_input.text().strip(), self.client_secret_input.text().strip()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.config = load_config()
        self.settings = load_settings()
        self.thread: QThread | None = None
        self.worker: ScanWorker | None = None
        self.started_at: float | None = None
        self.last_output: Path | None = None
        self.last_outputs: list[Path] = []
        self._closing = False
        self._applying_theme = False

        self.estimate_timer = QTimer(self)
        self.estimate_timer.setSingleShot(True)
        self.estimate_timer.setInterval(250)
        self.estimate_timer.timeout.connect(self._refresh_estimate)

        self.setWindowTitle(APP_NAME)
        self.resize(900, 780)
        self.setMinimumSize(800, 700)
        self._set_icon()
        self._build_ui()
        self._load_state()
        self._create_tray()
        self._apply_theme()
        self._schedule_estimate()

        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.setInterval(250)
        self.elapsed_timer.timeout.connect(self._update_elapsed)

    def _resource(self, name: str) -> Path:
        return Path(__file__).resolve().parent / "resources" / name

    def _set_icon(self) -> None:
        icon_path = self._resource("icon.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _card(self) -> QFrame:
        frame = QFrame()
        frame.setProperty("class", "card")
        return frame

    def _stat(self, label: str, tooltip: str) -> tuple[QFrame, QLabel]:
        frame = QFrame()
        frame.setProperty("class", "stat")
        frame.setMinimumHeight(78)
        frame.setToolTip(tooltip)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(2)
        label_widget = QLabel(label)
        label_widget.setProperty("class", "statLabel")
        label_widget.setMinimumHeight(18)
        value = QLabel("—")
        value.setProperty("class", "statValue")
        value.setMinimumHeight(28)
        layout.addWidget(label_widget)
        layout.addWidget(value)
        return frame, value

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        header.addWidget(title, 1)

        theme_box = QHBoxLayout()
        theme_label = QLabel("Theme")
        theme_label.setObjectName("muted")
        theme_box.addWidget(theme_label)
        self.theme_group = QButtonGroup(self)
        self.theme_buttons: dict[str, QRadioButton] = {}
        for key, text in (("auto", "Auto"), ("light", "Light"), ("dark", "Dark")):
            button = QRadioButton(text)
            button.setProperty("themeKey", key)
            button.toggled.connect(self._theme_changed)
            self.theme_group.addButton(button)
            self.theme_buttons[key] = button
            theme_box.addWidget(button)
        header.addLayout(theme_box)
        outer.addLayout(header)

        input_card = self._card()
        input_layout = QVBoxLayout(input_card)
        input_layout.setContentsMargins(14, 12, 14, 14)
        input_layout.setSpacing(10)
        section = QLabel("INPUT AND API USAGE")
        section.setObjectName("sectionTitle")
        input_layout.addWidget(section)

        path_row = QHBoxLayout()
        self.input_path = QLineEdit()
        self.input_path.setPlaceholderText("masterlist.csv")
        self.input_path.setToolTip(
            "Choose any CSV filename. Relative names such as list.csv are read from the application folder."
        )
        self.input_path.textChanged.connect(self._schedule_estimate)
        self.browse_button = QPushButton("Browse")
        self.browse_button.setProperty("class", "secondary")
        self.browse_button.clicked.connect(self._browse_input)
        path_row.addWidget(self.input_path, 1)
        path_row.addWidget(self.browse_button)
        input_layout.addLayout(path_row)

        self.retry_toggle = QCheckBox(
            "Retry unmatched ISBNs with a broader search (recommended; uses extra search API calls)"
        )
        self.retry_toggle.setToolTip(
            "The original tool stopped after one structured ISBN search. The broader retry is enabled by default "
            "because it recovered most matches in the 1,706-book test. Disable it only when conserving quota is more important."
        )
        self.retry_toggle.toggled.connect(self._schedule_estimate)
        input_layout.addWidget(self.retry_toggle)

        self.shipping_toggle = QCheckBox(
            "Include shipping when choosing the best price (may use item-detail API calls)"
        )
        self.shipping_toggle.setToolTip(
            "Shipping already returned in search results is reused for free. A separate item-detail call is made only "
            "when a candidate listing does not include shipping in the search response."
        )
        self.shipping_toggle.toggled.connect(self._schedule_estimate)
        input_layout.addWidget(self.shipping_toggle)

        options_row = QHBoxLayout()
        options_row.addWidget(QLabel("Output"))
        self.output_format = QComboBox()
        self.output_format.addItem("CSV — plain values, best for existing formulas", "csv")
        self.output_format.addItem("XLSX — formatted columns and hyperlinks", "xlsx")
        self.output_format.addItem("Both CSV and XLSX", "both")
        options_row.addWidget(self.output_format, 1)
        options_row.addSpacing(12)
        options_row.addWidget(QLabel("Keep unused quota"))
        self.quota_reserve = QSpinBox()
        self.quota_reserve.setRange(0, 5000)
        self.quota_reserve.setSingleStep(50)
        self.quota_reserve.setSuffix(" calls")
        self.quota_reserve.setToolTip(
            "The scan stops and writes partial results before either reported daily quota falls below this reserve."
        )
        self.quota_reserve.valueChanged.connect(self._schedule_estimate)
        options_row.addWidget(self.quota_reserve)
        input_layout.addLayout(options_row)

        self.estimate_label = QLabel("Choose a valid CSV to estimate API usage.")
        self.estimate_label.setObjectName("muted")
        self.estimate_label.setWordWrap(True)
        input_layout.addWidget(self.estimate_label)
        outer.addWidget(input_card)

        run_card = self._card()
        run_layout = QVBoxLayout(run_card)
        run_layout.setContentsMargins(14, 12, 14, 14)
        run_layout.setSpacing(10)
        run_header = QHBoxLayout()
        run_title = QLabel("SCAN")
        run_title.setObjectName("sectionTitle")
        self.elapsed_label = QLabel("Elapsed 00:00")
        self.elapsed_label.setObjectName("muted")
        run_header.addWidget(run_title)
        run_header.addStretch(1)
        run_header.addWidget(self.elapsed_label)
        run_layout.addLayout(run_header)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Ready")
        run_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("muted")
        run_layout.addWidget(self.status_label)

        stats = QGridLayout()
        stats.setVerticalSpacing(10)
        stats.setHorizontalSpacing(12)
        processed_frame, self.processed_value = self._stat(
            "Identifiers processed",
            "Rows completed from the selected CSV. Duplicate identifiers are queried only once.",
        )
        found_frame, self.found_value = self._stat(
            "Matches found",
            "Identifiers for which at least one eligible eBay listing was found.",
        )
        search_calls_frame, self.search_calls_value = self._stat(
            "Search API calls",
            "Structured ISBN searches plus optional broader retries.",
        )
        item_calls_frame, self.item_calls_value = self._stat(
            "Item-detail API calls",
            "Extra calls used only when shipping is enabled and absent from a search result.",
        )
        search_quota_frame, self.search_quota_value = self._stat(
            "Search quota remaining",
            "Daily eBay Browse item_summary/search quota remaining.",
        )
        item_quota_frame, self.item_quota_value = self._stat(
            "Item-detail quota remaining",
            "Daily eBay Browse item-detail quota remaining.",
        )
        stats.addWidget(processed_frame, 0, 0)
        stats.addWidget(found_frame, 0, 1)
        stats.addWidget(search_calls_frame, 1, 0)
        stats.addWidget(item_calls_frame, 1, 1)
        stats.addWidget(search_quota_frame, 2, 0)
        stats.addWidget(item_quota_frame, 2, 1)
        run_layout.addLayout(stats)

        self.summary_box = QTextEdit()
        self.summary_box.setReadOnly(True)
        self.summary_box.setMinimumHeight(155)
        self.summary_box.setPlainText("Completion details will appear here.")
        run_layout.addWidget(self.summary_box, 1)

        buttons = QHBoxLayout()
        self.start_button = QPushButton("START")
        self.start_button.clicked.connect(self._start_scan)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setProperty("class", "danger")
        self.cancel_button.clicked.connect(self._cancel_scan)
        self.cancel_button.setVisible(False)
        self.open_file_button = QPushButton("Open result")
        self.open_file_button.setProperty("class", "secondary")
        self.open_file_button.clicked.connect(self._open_result)
        self.open_file_button.setEnabled(False)
        self.open_folder_button = QPushButton("Open output folder")
        self.open_folder_button.setProperty("class", "secondary")
        self.open_folder_button.clicked.connect(self._open_output_folder)
        buttons.addWidget(self.start_button, 1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.open_file_button)
        buttons.addWidget(self.open_folder_button)
        run_layout.addLayout(buttons)
        outer.addWidget(run_card, 1)

        version = QLabel(f"Version {VERSION}")
        version.setObjectName("muted")
        outer.addWidget(version)

    def _load_state(self) -> None:
        configured_input = str(self.settings.get("input_file") or "").strip()
        self.input_path.setText(configured_input or str(self.config.get("input_csv", "masterlist.csv")))
        self.retry_toggle.setChecked(bool(self.settings.get("retry_unmatched", True)))
        self.shipping_toggle.setChecked(bool(self.settings.get("include_shipping", False)))
        output_format = str(self.settings.get("output_format", "csv")).casefold()
        index = self.output_format.findData(output_format)
        self.output_format.setCurrentIndex(index if index >= 0 else 0)
        self.quota_reserve.setValue(int(self.settings.get("quota_reserve", 100)))
        theme = str(self.settings.get("theme", "auto"))
        self.theme_buttons.get(theme, self.theme_buttons["auto"]).setChecked(True)

    def _create_tray(self) -> None:
        self.tray: QSystemTrayIcon | None = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu(self)
        show_action = QAction("Show", self)
        show_action.triggered.connect(self._show_window)
        start_action = QAction("Start scan", self)
        start_action.triggered.connect(self._start_scan)
        output_action = QAction("Open output folder", self)
        output_action.triggered.connect(self._open_output_folder)
        credentials_action = QAction("Update eBay credentials…", self)
        credentials_action.triggered.connect(self._edit_credentials)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit)
        menu.addAction(show_action)
        menu.addAction(start_action)
        menu.addAction(output_action)
        menu.addAction(credentials_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self._show_window()
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick
            else None
        )
        self.tray.show()

    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _effective_theme(self) -> str:
        choice = str(self.settings.get("theme", "auto"))
        if choice != "auto":
            return choice
        return "dark" if QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark else "light"

    def _apply_theme(self) -> None:
        if self._applying_theme:
            return
        self._applying_theme = True
        try:
            selected = DARK if self._effective_theme() == "dark" else LIGHT
            new_stylesheet = stylesheet(selected)
            if self.styleSheet() != new_stylesheet:
                self.setStyleSheet(new_stylesheet)
        finally:
            self._applying_theme = False

    @Slot()
    def _theme_changed(self) -> None:
        checked = self.theme_group.checkedButton()
        if not checked or not checked.isChecked():
            return
        self.settings["theme"] = checked.property("themeKey")
        save_settings(self.settings)
        self._apply_theme()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.PaletteChange
            and self.settings.get("theme") == "auto"
            and not self._applying_theme
        ):
            QTimer.singleShot(0, self._apply_theme)

    def _resolved_input_path(self) -> Path:
        value = self.input_path.text().strip() or str(self.config.get("input_csv", "masterlist.csv"))
        return resolve_path(value)

    def _browse_input(self) -> None:
        current = self._resolved_input_path()
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select book list",
            str(current.parent if current.parent.exists() else executable_dir()),
            "CSV files (*.csv);;All files (*.*)",
        )
        if selected:
            self.input_path.setText(selected)
            self.settings["input_file"] = selected
            save_settings(self.settings)

    def _schedule_estimate(self, *_args) -> None:
        self.estimate_timer.start()

    def _refresh_estimate(self) -> None:
        input_file = self._resolved_input_path()
        if not input_file.exists() or input_file.suffix.casefold() != ".csv":
            self.estimate_label.setText("Choose a valid CSV to estimate API usage.")
            return
        try:
            estimate = estimate_calls(
                input_file,
                retry_unmatched=self.retry_toggle.isChecked(),
                include_shipping=self.shipping_toggle.isChecked(),
                shipping_item_limit=int(self.config.get("shipping_item_limit", 3)),
            )
        except Exception as exc:
            self.estimate_label.setText(f"Could not estimate this file: {exc}")
            return

        if estimate.search_min == estimate.search_max:
            search_text = f"{estimate.search_min:,} search calls"
        else:
            search_text = f"{estimate.search_min:,}–{estimate.search_max:,} search calls"
        detail_text = ""
        if self.shipping_toggle.isChecked():
            detail_text = (
                f"; 0–{estimate.item_detail_max:,} item-detail calls for shipping "
                "(usually fewer because search-result shipping is reused)"
            )
        self.estimate_label.setText(
            f"{estimate.total_identifiers:,} rows / {estimate.unique_identifiers:,} unique identifiers: "
            f"estimated {search_text}{detail_text}. The scan keeps {self.quota_reserve.value():,} calls in reserve."
        )

    def _edit_credentials(self) -> tuple[str, str] | None:
        current_id, current_secret = load_credentials(self.config)
        dialog = CredentialsDialog(
            self,
            client_id=current_id or "",
            client_secret=current_secret or "",
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        client_id, client_secret = dialog.credentials()
        try:
            save_credentials(client_id, client_secret)
        except Exception as exc:
            QMessageBox.critical(
                self,
                APP_NAME,
                f"Could not save credentials in Windows Credential Manager:\n\n{exc}",
            )
            return None
        self.status_label.setText("eBay credentials updated.")
        return client_id, client_secret

    def _credentials_for_scan(self) -> tuple[str, str] | None:
        client_id, client_secret = load_credentials(self.config)
        if client_id and client_secret:
            return client_id, client_secret
        return self._edit_credentials()

    def _start_scan(self) -> None:
        if self.thread and self.thread.isRunning():
            return

        input_file = self._resolved_input_path()
        if not input_file.exists():
            QMessageBox.warning(self, APP_NAME, f"Input file not found:\n{input_file}")
            return
        if input_file.suffix.lower() != ".csv":
            QMessageBox.warning(self, APP_NAME, "The input file must be a CSV file.")
            return

        credentials = self._credentials_for_scan()
        if credentials is None:
            return
        client_id, client_secret = credentials

        raw_input = self.input_path.text().strip() or str(self.config.get("input_csv", "masterlist.csv"))
        self.settings.update(
            {
                "input_file": raw_input,
                "retry_unmatched": self.retry_toggle.isChecked(),
                "include_shipping": self.shipping_toggle.isChecked(),
                "output_format": str(self.output_format.currentData()),
                "quota_reserve": self.quota_reserve.value(),
            }
        )
        save_settings(self.settings)

        output_dir = resolve_path(str(self.config.get("output_dir", "output")))
        self.worker = ScanWorker(
            input_file=input_file,
            output_dir=output_dir,
            config=self.config,
            client_id=client_id,
            client_secret=client_secret,
            include_shipping=self.shipping_toggle.isChecked(),
            retry_unmatched=self.retry_toggle.isChecked(),
            output_format=str(self.output_format.currentData()),
            quota_reserve=self.quota_reserve.value(),
        )
        self.thread = QThread(self)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.completed.connect(self._on_completed)
        self.worker.failed.connect(self._on_failed)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.completed.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.worker.cancelled.connect(self.thread.quit)
        self.thread.finished.connect(self._thread_finished)
        self.thread.start()

        self.started_at = time.monotonic()
        self.elapsed_timer.start()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFormat("Checking eBay quota…")
        self.status_label.setText(f"Starting scan of {input_file.name}…")
        self.summary_box.setPlainText("Scanning in progress. Results and quota usage will appear here.")
        self.processed_value.setText("0")
        self.found_value.setText("0")
        self.search_calls_value.setText("0")
        self.item_calls_value.setText("0")
        self.search_quota_value.setText("—")
        self.item_quota_value.setText("—")
        self.start_button.setEnabled(False)
        self.cancel_button.setVisible(True)
        self.browse_button.setEnabled(False)
        self.retry_toggle.setEnabled(False)
        self.shipping_toggle.setEnabled(False)
        self.output_format.setEnabled(False)
        self.quota_reserve.setEnabled(False)
        self.open_file_button.setEnabled(False)

    def _cancel_scan(self) -> None:
        if self.worker:
            self.worker.request_cancel()
            self.status_label.setText("Cancelling after active requests finish…")
            self.cancel_button.setEnabled(False)

    @Slot(object)
    def _on_progress(self, info: ProgressInfo) -> None:
        self.progress_bar.setRange(0, max(info.total, 1))
        self.progress_bar.setValue(info.completed)
        self.progress_bar.setFormat(f"{info.completed} of {info.total} identifiers")
        self.processed_value.setText(f"{info.completed} / {info.total}")
        self.found_value.setText(str(info.found))
        self.search_calls_value.setText(f"{info.search_calls:,}")
        self.item_calls_value.setText(f"{info.item_detail_calls:,}")
        self.status_label.setText(f"{info.status}: {info.current_identifier}")

    @staticmethod
    def _format_search_usage(summary: RunSummary) -> str:
        first = summary.api_call_breakdown.get("primary_search", 0)
        second = summary.api_call_breakdown.get("fallback_search", 0)
        total = first + second
        if second:
            return f"Search API calls used: {total:,} ({first:,} first searches + {second:,} broader retries)"
        return f"Search API calls used: {total:,}"

    @staticmethod
    def _format_item_usage(summary: RunSummary) -> str:
        detail = summary.api_call_breakdown.get("shipping_detail", 0)
        return f"Item-detail API calls used: {detail:,}"

    @staticmethod
    def _format_request_usage(summary: RunSummary) -> str:
        first = summary.api_call_breakdown.get("primary_search", 0)
        second = summary.api_call_breakdown.get("fallback_search", 0)
        detail = summary.api_call_breakdown.get("shipping_detail", 0)
        parts = [f"{first:,} first searches"]
        if second:
            parts.append(f"{second:,} broader retries")
        if detail:
            parts.append(f"{detail:,} item-detail calls")
        return f"eBay API calls used: {summary.api_calls:,} ({' + '.join(parts)})"

    @staticmethod
    def _quota_display(quota: QuotaInfo) -> str:
        if quota.remaining is None:
            return "Unavailable"
        suffix = " est." if quota.estimated else ""
        return f"{quota.remaining:,}{suffix}"

    @staticmethod
    def _quota_line(label: str, quota: QuotaInfo) -> str:
        if quota.remaining is None:
            return f"{label}: unavailable"
        if quota.limit is not None:
            text = f"{label}: {quota.remaining:,} of {quota.limit:,}"
        else:
            text = f"{label}: {quota.remaining:,}"
        if quota.estimated:
            text += " (locally adjusted while eBay reporting catches up)"
        return text

    @Slot(object)
    def _on_completed(self, summary: RunSummary) -> None:
        self.last_output = summary.output_file
        self.last_outputs = list(summary.output_files or [summary.output_file])
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat("Stopped safely" if summary.stopped_for_quota else "Complete")
        self.processed_value.setText(str(summary.total_identifiers - summary.skipped))
        self.found_value.setText(str(summary.found))
        self.search_calls_value.setText(
            f"{summary.api_call_breakdown.get('primary_search', 0) + summary.api_call_breakdown.get('fallback_search', 0):,}"
        )
        self.item_calls_value.setText(f"{summary.api_call_breakdown.get('shipping_detail', 0):,}")
        self.search_quota_value.setText(self._quota_display(summary.quota))
        self.item_quota_value.setText(self._quota_display(summary.item_quota))

        lines: list[str] = []
        if summary.stopped_for_quota:
            lines.extend(("STOPPED SAFELY: quota reserve reached.", summary.stop_reason, ""))
        lines.extend(
            [
                f"Processed: {summary.total_identifiers - summary.skipped} of {summary.total_identifiers} "
                f"({summary.unique_identifiers:,} unique total)",
                f"Matches found: {summary.found}",
                f"No match: {summary.no_match}",
                f"Not scanned: {summary.skipped}",
                f"Failed: {summary.failed}",
                self._format_search_usage(summary),
                self._format_item_usage(summary),
                f"Elapsed time: {self._format_elapsed(summary.elapsed_seconds)}",
                self._quota_line("Daily search quota remaining", summary.quota),
                self._quota_line("Daily item-detail quota remaining", summary.item_quota),
            ]
        )
        if summary.quota.reset_at:
            lines.append(f"Search quota reset: {self._format_quota_reset(summary.quota.reset_at)}")
        if summary.item_quota.reset_at and summary.item_quota.reset_at != summary.quota.reset_at:
            lines.append(f"Item-detail quota reset: {self._format_quota_reset(summary.item_quota.reset_at)}")
        for warning in summary.warnings:
            if warning and warning not in lines:
                lines.append(warning)
        lines.append("")
        if len(self.last_outputs) == 1:
            lines.append(f"Result saved to: {self.last_outputs[0]}")
        else:
            lines.append("Results saved to:")
            lines.extend(f"  {path}" for path in self.last_outputs)

        self.summary_box.setPlainText("\n".join(lines))
        self.status_label.setText("Scan stopped safely." if summary.stopped_for_quota else "Scan complete.")
        self.open_file_button.setEnabled(True)
        if self.tray:
            message = "Scan stopped at the quota reserve; partial results were saved." if summary.stopped_for_quota else "Scan complete. Results are ready."
            self.tray.showMessage(APP_NAME, message, QSystemTrayIcon.MessageIcon.Information, 5000)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Failed")
        self.status_label.setText("Scan failed.")
        if "credential" in message.casefold():
            message += "\n\nUse the tray icon's ‘Update eBay credentials…’ command to replace them."
        self.summary_box.setPlainText(message)

    @Slot()
    def _on_cancelled(self) -> None:
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Cancelled")
        self.status_label.setText("Scan cancelled.")
        self.summary_box.setPlainText("The scan was cancelled. No output file was written.")

    @Slot()
    def _thread_finished(self) -> None:
        self.elapsed_timer.stop()
        self.start_button.setEnabled(True)
        self.start_button.setText("RUN AGAIN")
        self.cancel_button.setVisible(False)
        self.cancel_button.setEnabled(True)
        self.browse_button.setEnabled(True)
        self.retry_toggle.setEnabled(True)
        self.shipping_toggle.setEnabled(True)
        self.output_format.setEnabled(True)
        self.quota_reserve.setEnabled(True)
        if self.worker:
            self.worker.deleteLater()
        if self.thread:
            self.thread.deleteLater()
        self.worker = None
        self.thread = None
        self._schedule_estimate()
        if self._closing:
            QTimer.singleShot(0, QApplication.quit)

    def _update_elapsed(self) -> None:
        if self.started_at is None:
            return
        self.elapsed_label.setText(f"Elapsed {self._format_elapsed(time.monotonic() - self.started_at)}")

    @staticmethod
    def _format_quota_reset(value: str, local_timezone: tzinfo | None = None) -> str:
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.astimezone()
            else:
                parsed = parsed.astimezone(local_timezone)
            hour = parsed.strftime("%I").lstrip("0") or "12"
            return f"{parsed:%m-%d-%Y} {hour}:{parsed:%M} {parsed:%p}"
        except (TypeError, ValueError):
            return value

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        seconds = max(0, int(seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"

    def _open_result(self) -> None:
        if self.last_output and self.last_output.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_output)))

    def _open_output_folder(self) -> None:
        output = self.last_output.parent if self.last_output else resolve_path(str(self.config.get("output_dir", "output")))
        output.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(output)))

    def _quit(self) -> None:
        if self.thread and self.thread.isRunning():
            self._closing = True
            if self.worker:
                self.worker.request_cancel()
            self.status_label.setText("Cancelling before exit…")
            return
        self._closing = True
        QApplication.quit()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.thread and self.thread.isRunning():
            if not self._closing:
                choice = QMessageBox.question(
                    self,
                    APP_NAME,
                    "A scan is still running. Cancel it and quit?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if choice != QMessageBox.StandardButton.Yes:
                    event.ignore()
                    return
                self._closing = True
                if self.worker:
                    self.worker.request_cancel()
                self.status_label.setText("Cancelling before exit…")
            event.ignore()
            return
        if self.tray:
            self.tray.hide()
        event.accept()
