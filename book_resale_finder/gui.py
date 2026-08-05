"""Book Resale Finder desktop interface with compact, resilient stat cards."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy

from .gui_v115 import CredentialsDialog, MainWindow as _MainWindow, ScanWorker


class MainWindow(_MainWindow):
    """Apply presentation fixes without duplicating the main GUI implementation."""

    def _stat(self, label: str, tooltip: str) -> tuple[QFrame, QLabel]:
        # The previous two-line cards could be vertically compressed until the
        # value label was completely clipped. Keep each label and value on one
        # line so every result remains visible at all supported window sizes.
        frame = QFrame()
        frame.setProperty("class", "stat")
        frame.setMinimumHeight(48)
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        frame.setToolTip(tooltip)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(12)

        label_widget = QLabel(label)
        label_widget.setProperty("class", "statLabel")
        label_widget.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        label_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        value = QLabel("—")
        value.setProperty("class", "statValue")
        value.setMinimumWidth(90)
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        value.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)

        layout.addWidget(label_widget, 1)
        layout.addWidget(value)
        return frame, value

    def _build_ui(self) -> None:
        super()._build_ui()

        for label in self.findChildren(QLabel):
            if label.text() == "Keep unused quota":
                label.setText("Stop with at least")
                break

        self.quota_reserve.setSuffix(" calls remaining")
        self.quota_reserve.setToolTip(
            "The scan stops and saves partial results before either daily quota "
            "would fall below this number of remaining calls. Set it to 0 to "
            "disable the safety buffer."
        )


__all__ = ["CredentialsDialog", "MainWindow", "ScanWorker"]
