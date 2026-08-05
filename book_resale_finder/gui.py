"""Book Resale Finder desktop interface with resilient stats and quota reporting."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy

from . import runner as _runner
from .ebay_v118 import EbayClient as _QuotaAwareEbayClient
from .models import RunSummary

# run_scan resolves EbayClient from the runner module at call time. Replace the
# older quota parser without duplicating the scan implementation.
_runner.EbayClient = _QuotaAwareEbayClient

from .gui_v115 import CredentialsDialog, MainWindow as _MainWindow, ScanWorker


class MainWindow(_MainWindow):
    """Apply presentation and quota-reporting fixes to the main interface."""

    def _stat(self, label: str, tooltip: str) -> tuple[QFrame, QLabel]:
        # Keep each label and value on one line so every result remains visible
        # at all supported window sizes.
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

        if not hasattr(self, "_stat_frames"):
            self._stat_frames: dict[QLabel, QFrame] = {}
        self._stat_frames[value] = frame
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

    def _set_quota_cards_visible(self, search_visible: bool, item_visible: bool) -> None:
        self._stat_frames[self.search_quota_value].setVisible(search_visible)
        self._stat_frames[self.item_quota_value].setVisible(item_visible)

    def _start_scan(self) -> None:
        # Show both quota cards while a new lookup is running. Each card is
        # hidden after completion only when eBay supplied no value for it.
        self._set_quota_cards_visible(True, True)
        super()._start_scan()

    @staticmethod
    def _remove_unavailable_quota_lines(text: str) -> str:
        hidden = {
            "Daily search quota remaining: unavailable",
            "Daily item-detail quota remaining: unavailable",
        }
        lines = [line for line in text.splitlines() if line.strip() not in hidden]
        compact: list[str] = []
        for line in lines:
            if line or not compact or compact[-1]:
                compact.append(line)
        return "\n".join(compact).strip()

    def _quota_safety_warnings(self, summary: RunSummary) -> list[str]:
        reserve = self.quota_reserve.value()
        if reserve <= 0:
            return []

        warnings: list[str] = []
        if summary.quota.remaining is None:
            warnings.append(
                f"eBay did not provide search-quota data, so the {reserve:,}-call safety buffer could not be enforced."
            )
        if self.shipping_toggle.isChecked() and summary.item_quota.remaining is None:
            warnings.append(
                f"eBay did not provide item-detail quota data, so the {reserve:,}-call shipping safety buffer could not be enforced."
            )
        return warnings

    def _on_completed(self, summary: RunSummary) -> None:
        super()._on_completed(summary)

        # A quota card must remain a quota card. If eBay supplies no quota
        # value, hide that card rather than relabeling it with an unrelated
        # scan statistic.
        self._set_quota_cards_visible(
            summary.quota.remaining is not None,
            summary.item_quota.remaining is not None,
        )

        cleaned = self._remove_unavailable_quota_lines(self.summary_box.toPlainText())
        warnings = self._quota_safety_warnings(summary)
        if warnings:
            lines = cleaned.splitlines()
            result_index = next(
                (
                    index
                    for index, line in enumerate(lines)
                    if line.startswith("Result saved to:") or line == "Results saved to:"
                ),
                len(lines),
            )
            before = lines[:result_index]
            while before and not before[-1]:
                before.pop()
            after = lines[result_index:]
            lines = before + [""] + warnings + ([""] if after else []) + after
            cleaned = "\n".join(lines)
        self.summary_box.setPlainText(cleaned)


__all__ = ["CredentialsDialog", "MainWindow", "ScanWorker"]
