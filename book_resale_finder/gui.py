from __future__ import annotations

import asyncio
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
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
from PySide6.QtCore import QUrl

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


class CredentialsDialog(QMessageBox):
    """Kept for compatibility only; credentials are edited inline in the main window."""


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

        self.setWindowTitle(APP_NAME)
        self.resize(820, 720)
        self.setMinimumSize(760, 660)
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

    def _stat(self, label: str) -> tuple[QFrame, QLabel]:
        frame = QFrame()
        frame.setProperty("class", "stat")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        label_widget = QLabel(label)
        label_widget.setProperty("class", "statLabel")
        value = QLabel("—")
        value.setProperty("class", "statValue")
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
        title_box = QVBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        subtitle = QLabel("Find the lowest active eBay offer for every ASIN in a Keepa export.")
        subtitle.setObjectName("subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)

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
        self.browse_button = QPushButton("Browse")
        self.browse_button.setProperty("class", "secondary")
        self.browse_button.clicked.connect(self._browse_input)
        path_row.addWidget(self.input_path, 1)
        path_row.addWidget(self.browse_button)
        input_layout.addLayout(path_row)

        self.shipping_toggle = QCheckBox("Include shipping when choosing the best price (uses extra API calls)")
        self.shipping_toggle.setToolTip(
            "Checks up to the configured number of cheapest listings individually and compares item price plus shipping."
        )
        input_layout.addWidget(self.shipping_toggle)
        outer.addWidget(input_card)

        credentials_card = self._card()
        credentials_layout = QVBoxLayout(credentials_card)
        credentials_layout.setContentsMargins(14, 12, 14, 14)
        credentials_layout.setSpacing(10)
        credential_header = QHBoxLayout()
        credential_title = QLabel("EBAY API CREDENTIALS")
        credential_title.setObjectName("sectionTitle")
        self.credentials_status = QLabel()
        self.credentials_status.setObjectName("muted")
        credential_header.addWidget(credential_title)
        credential_header.addStretch(1)
        credential_header.addWidget(self.credentials_status)
        credentials_layout.addLayout(credential_header)
        credential_grid = QGridLayout()
        self.client_id_input = QLineEdit()
        self.client_id_input.setPlaceholderText("Client ID / App ID")
        self.client_secret_input = QLineEdit()
        self.client_secret_input.setPlaceholderText("Client Secret / Cert ID")
        self.client_secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.save_credentials_button = QPushButton("Save credentials")
        self.save_credentials_button.clicked.connect(self._save_credentials)
        credential_grid.addWidget(self.client_id_input, 0, 0)
        credential_grid.addWidget(self.client_secret_input, 0, 1)
        credential_grid.addWidget(self.save_credentials_button, 0, 2)
        credentials_layout.addLayout(credential_grid)
        outer.addWidget(credentials_card)

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

        self.status_label = QLabel("Ready to scan masterlist.csv")
        self.status_label.setObjectName("muted")
        run_layout.addWidget(self.status_label)

        stats = QGridLayout()
        processed_frame, self.processed_value = self._stat("Processed")
        found_frame, self.found_value = self._stat("Listings found")
        api_frame, self.api_value = self._stat("API calls this run")
        remaining_frame, self.remaining_value = self._stat("Calls remaining")
        stats.addWidget(processed_frame, 0, 0)
        stats.addWidget(found_frame, 0, 1)
        stats.addWidget(api_frame, 1, 0)
        stats.addWidget(remaining_frame, 1, 1)
        run_layout.addLayout(stats)

        self.summary_box = QTextEdit()
        self.summary_box.setReadOnly(True)
        self.summary_box.setMinimumHeight(110)
        self.summary_box.setPlainText("Completion details will appear here.")
        run_layout.addWidget(self.summary_box)

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

        footer = QHBoxLayout()
        version = QLabel(f"Version {VERSION}")
        version.setObjectName("muted")
        note = QLabel("Input: ASIN column • Output: formatted XLSX")
        note.setObjectName("muted")
        footer.addWidget(version)
        footer.addStretch(1)
        footer.addWidget(note)
        outer.addLayout(footer)

    def _load_state(self) -> None:
        configured_input = str(self.settings.get("input_file") or "").strip()
        if configured_input:
            path = Path(configured_input)
        else:
            path = resolve_path(str(self.config.get("input_csv", "masterlist.csv")))
        self.input_path.setText(str(path))
        self.shipping_toggle.setChecked(bool(self.settings.get("include_shipping", False)))
        theme = str(self.settings.get("theme", "auto"))
        self.theme_buttons.get(theme, self.theme_buttons["auto"]).setChecked(True)
        client_id, client_secret = load_credentials(self.config)
        if client_id:
            self.client_id_input.setText(client_id)
        if client_secret:
            self.client_secret_input.setText(client_secret)
        self._update_credentials_status()

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
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit)
        menu.addAction(show_action)
        menu.addAction(start_action)
        menu.addAction(output_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self._show_window() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
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
        self.setStyleSheet(stylesheet(DARK if self._effective_theme() == "dark" else LIGHT))

    @Slot()
    def _theme_changed(self) -> None:
        checked = self.theme_group.checkedButton()
        if not checked:
            return
        self.settings["theme"] = checked.property("themeKey")
        save_settings(self.settings)
        self._apply_theme()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and self.settings.get("theme") == "auto":
            self._apply_theme()

    def _browse_input(self) -> None:
        current = Path(self.input_path.text()).expanduser()
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select Keepa masterlist",
            str(current.parent if current.parent.exists() else executable_dir()),
            "CSV files (*.csv);;All files (*.*)",
        )
        if selected:
            self.input_path.setText(selected)
            self.settings["input_file"] = selected
            save_settings(self.settings)

    def _update_credentials_status(self) -> None:
        client_id = self.client_id_input.text().strip()
        secret = self.client_secret_input.text().strip()
        self.credentials_status.setText("Configured" if client_id and secret else "Required before scanning")

    def _save_credentials(self) -> None:
        client_id = self.client_id_input.text().strip()
        secret = self.client_secret_input.text().strip()
        if not client_id or not secret:
            QMessageBox.warning(self, APP_NAME, "Enter both the Client ID and Client Secret.")
            return
        try:
            save_credentials(client_id, secret)
        except Exception as exc:
            QMessageBox.critical(
                self,
                APP_NAME,
                f"Could not save credentials in Windows Credential Manager:\n\n{exc}",
            )
            return
        self._update_credentials_status()
        self.status_label.setText("eBay API credentials saved securely.")

    def _start_scan(self) -> None:
        if self.thread and self.thread.isRunning():
            return
        input_file = Path(self.input_path.text().strip()).expanduser()
        client_id = self.client_id_input.text().strip()
        client_secret = self.client_secret_input.text().strip()
        if not client_id or not client_secret:
            QMessageBox.warning(self, APP_NAME, "Enter your eBay API credentials first.")
            return
        if not input_file.exists():
            QMessageBox.warning(self, APP_NAME, f"Input file not found:\n{input_file}")
            return

        self.settings["input_file"] = str(input_file)
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
        self.status_label.setText("Starting scan…")
        self.summary_box.setPlainText("Scanning in progress. The formatted workbook will be written when the scan completes.")
        self.processed_value.setText("0")
        self.found_value.setText("0")
        self.api_value.setText("0")
        self.remaining_value.setText("—")
        self.start_button.setEnabled(False)
        self.cancel_button.setVisible(True)
        self.browse_button.setEnabled(False)
        self.shipping_toggle.setEnabled(False)
        self.client_id_input.setEnabled(False)
        self.client_secret_input.setEnabled(False)
        self.save_credentials_button.setEnabled(False)
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

    @Slot(object)
    def _on_completed(self, summary: RunSummary) -> None:
        self.last_output = summary.output_file
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat("Complete")
        self.processed_value.setText(str(summary.total_identifiers))
        self.found_value.setText(str(summary.found))
        self.api_value.setText(str(summary.api_calls))
        self.remaining_value.setText(
            str(summary.quota.remaining) if summary.quota.remaining is not None else "Unavailable"
        )
        lines = [
            f"Processed {summary.total_identifiers} identifiers ({summary.unique_identifiers} unique).",
            f"Listings found: {summary.found}",
            f"No match: {summary.no_match}",
            f"Failed: {summary.failed}",
            f"API calls made this run: {summary.api_calls}",
            f"Elapsed time: {self._format_elapsed(summary.elapsed_seconds)}",
        ]
        if summary.quota.limit is not None and summary.quota.used is not None:
            lines.append(f"API calls used: {summary.quota.used} out of {summary.quota.limit}")
        if summary.quota.remaining is not None:
            lines.append(f"Remaining calls: {summary.quota.remaining}")
        if summary.quota.reset_at:
            lines.append(f"Quota resets at: {summary.quota.reset_at} UTC")
        lines.append(f"Results saved to: {summary.output_file}")
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
        self.client_id_input.setEnabled(True)
        self.client_secret_input.setEnabled(True)
        self.save_credentials_button.setEnabled(True)
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
