from __future__ import annotations

import asyncio
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QThread, QTimer, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
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
from .models import ProgressInfo, RunSummary
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
        self._closing = False
        self._applying_theme = False

        self.setWindowTitle(APP_NAME)
        self.resize(820, 650)
        self.setMinimumSize(760, 600)
        self._set_icon()
        self._build_ui()
        self._load_state()
        self._create_tray()
        self._apply_theme()

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
        section = QLabel("INPUT")
        section.setObjectName("sectionTitle")
        input_layout.addWidget(section)

        path_row = QHBoxLayout()
        self.input_path = QLineEdit()
        self.input_path.setPlaceholderText("masterlist.csv")
        self.input_path.setToolTip(
            "Choose any CSV filename. Relative names such as list.csv are read from the application folder."
        )
        self.browse_button = QPushButton("Browse")
        self.browse_button.setProperty("class", "secondary")
        self.browse_button.clicked.connect(self._browse_input)
        path_row.addWidget(self.input_path, 1)
        path_row.addWidget(self.browse_button)
        input_layout.addLayout(path_row)

        self.shipping_toggle = QCheckBox("Include shipping when choosing the best price (uses extra eBay requests)")
        self.shipping_toggle.setToolTip(
            "Checks up to the configured number of cheapest listings individually and compares item price plus shipping."
        )
        input_layout.addWidget(self.shipping_toggle)
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
        api_frame, self.api_value = self._stat(
            "eBay requests used",
            "The total requests made by this scan: first searches, second searches after no result, and optional shipping checks.",
        )
        remaining_frame, self.remaining_value = self._stat(
            "Daily requests remaining",
            "The remaining daily quota reported by eBay. This separate counter can update later than the scan total.",
        )
        stats.addWidget(processed_frame, 0, 0)
        stats.addWidget(found_frame, 0, 1)
        stats.addWidget(api_frame, 1, 0)
        stats.addWidget(remaining_frame, 1, 1)
        run_layout.addLayout(stats)

        self.summary_box = QTextEdit()
        self.summary_box.setReadOnly(True)
        self.summary_box.setMinimumHeight(140)
        self.summary_box.setPlainText("Completion details will appear here.")
        run_layout.addWidget(self.summary_box, 1)

        buttons = QHBoxLayout()
        self.start_button = QPushButton("START")
        self.start_button.clicked.connect(self._start_scan)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setProperty("class", "danger")
        self.cancel_button.clicked.connect(self._cancel_scan)
        self.cancel_button.setVisible(False)
        self.open_file_button = QPushButton("Open spreadsheet")
        self.open_file_button.setProperty("class", "secondary")
        self.open_file_button.clicked.connect(self._open_spreadsheet)
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
        self.shipping_toggle.setChecked(bool(self.settings.get("include_shipping", False)))
        theme = str(self.settings.get("theme", "auto"))
        self.theme_buttons.get(theme, self.theme_buttons["auto"]).setChecked(True)

    def _create_tray(self) -> None:
        self.tray: QSystemTrayIcon | None = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = self.windowIcon()
        self.tray = QSystemTrayIcon(icon, self)
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
        credentials = self._credentials_for_scan()
        if credentials is None:
            return
        client_id, client_secret = credentials

        if not input_file.exists():
            QMessageBox.warning(self, APP_NAME, f"Input file not found:\n{input_file}")
            return
        if input_file.suffix.lower() != ".csv":
            QMessageBox.warning(self, APP_NAME, "The input file must be a CSV file.")
            return

        raw_input = self.input_path.text().strip() or str(self.config.get("input_csv", "masterlist.csv"))
        self.settings["input_file"] = raw_input
        self.settings["include_shipping"] = self.shipping_toggle.isChecked()
        save_settings(self.settings)

        output_dir = resolve_path(str(self.config.get("output_dir", "output")))
        self.worker = ScanWorker(
            input_file=input_file,
            output_dir=output_dir,
            config=self.config,
            client_id=client_id,
            client_secret=client_secret,
            include_shipping=self.shipping_toggle.isChecked(),
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
        self.progress_bar.setFormat("Connecting to eBay…")
        self.status_label.setText(f"Starting scan of {input_file.name}…")
        self.summary_box.setPlainText(
            "Scanning in progress. Request details and the output path will appear here when complete."
        )
        self.processed_value.setText("0")
        self.found_value.setText("0")
        self.api_value.setText("0")
        self.remaining_value.setText("—")
        self.start_button.setEnabled(False)
        self.cancel_button.setVisible(True)
        self.browse_button.setEnabled(False)
        self.shipping_toggle.setEnabled(False)
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
        self.api_value.setText(str(info.api_calls))
        self.status_label.setText(f"{info.status}: {info.current_identifier}")

    @staticmethod
    def _request_breakdown_lines(summary: RunSummary) -> list[str]:
        breakdown = summary.api_call_breakdown
        first_searches = breakdown.get("primary_search", 0)
        second_searches = breakdown.get("fallback_search", 0)
        shipping_checks = breakdown.get("shipping_detail", 0)
        other = max(0, summary.api_calls - first_searches - second_searches - shipping_checks)

        lines = [
            "How that total was calculated:",
            f"  {first_searches} first searches — normally one for each unique book",
            f"+ {second_searches} second searches — only when the first search found nothing",
            f"+ {shipping_checks} shipping checks — only when shipping comparison is enabled",
        ]
        if other:
            lines.append(f"+ {other} repeated/other requests")
        lines.append(f"= {summary.api_calls} total requests")
        return lines

    @Slot(object)
    def _on_completed(self, summary: RunSummary) -> None:
        self.last_output = summary.output_file
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat("Complete")
        self.processed_value.setText(str(summary.total_identifiers))
        self.found_value.setText(str(summary.found))
        self.api_value.setText(str(summary.api_calls))

        quota_is_stale = (
            summary.api_calls > 0
            and summary.quota.used == 0
            and summary.quota.limit is not None
            and summary.quota.remaining == summary.quota.limit
        )
        if summary.quota.remaining is None:
            self.remaining_value.setText("Unavailable")
        else:
            suffix = "*" if quota_is_stale else ""
            self.remaining_value.setText(f"{summary.quota.remaining:,}{suffix}")

        lines = [
            f"Processed: {summary.total_identifiers} ({summary.unique_identifiers} unique)",
            f"Matches found: {summary.found}",
            f"No match: {summary.no_match}",
            f"Failed: {summary.failed}",
            "",
            *self._request_breakdown_lines(summary),
            "",
            f"Elapsed time: {self._format_elapsed(summary.elapsed_seconds)}",
        ]

        if summary.quota.remaining is not None:
            if summary.quota.limit is not None:
                lines.append(
                    f"eBay says {summary.quota.remaining:,} of {summary.quota.limit:,} daily requests remain."
                )
            else:
                lines.append(f"eBay says {summary.quota.remaining:,} daily requests remain.")
            if quota_is_stale:
                lines.append(
                    "* eBay's daily counter has not caught up yet. It does not change the exact total shown above."
                )
        else:
            lines.append("eBay's separate daily-limit counter was unavailable.")
        if summary.quota.reset_at:
            lines.append(f"eBay says the daily limit resets at: {summary.quota.reset_at}")
        lines.extend(("", f"Results saved to: {summary.output_file}"))

        self.summary_box.setPlainText("\n".join(lines))
        self.status_label.setText("Scan complete.")
        self.open_file_button.setEnabled(True)
        if self.tray:
            self.tray.showMessage(
                APP_NAME,
                "Scan complete. The XLSX results are ready.",
                QSystemTrayIcon.MessageIcon.Information,
                5000,
            )

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
        self.summary_box.setPlainText("The scan was cancelled. No output workbook was written.")

    @Slot()
    def _thread_finished(self) -> None:
        self.elapsed_timer.stop()
        self.start_button.setEnabled(True)
        self.start_button.setText("RUN AGAIN")
        self.cancel_button.setVisible(False)
        self.cancel_button.setEnabled(True)
        self.browse_button.setEnabled(True)
        self.shipping_toggle.setEnabled(True)
        if self.worker:
            self.worker.deleteLater()
        if self.thread:
            self.thread.deleteLater()
        self.worker = None
        self.thread = None
        if self._closing:
            QTimer.singleShot(0, QApplication.quit)

    def _update_elapsed(self) -> None:
        if self.started_at is None:
            return
        self.elapsed_label.setText(f"Elapsed {self._format_elapsed(time.monotonic() - self.started_at)}")

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        seconds = max(0, int(seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"

    def _open_spreadsheet(self) -> None:
        if self.last_output and self.last_output.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_output)))

    def _open_output_folder(self) -> None:
        output = (
            self.last_output.parent
            if self.last_output
            else resolve_path(str(self.config.get("output_dir", "output")))
        )
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
