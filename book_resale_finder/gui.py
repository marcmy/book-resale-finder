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

        if not hasattr(self, "_stat_labels"):
            self._stat_labels: dict[QLabel, tuple[QLabel, str]] = {}
        self._stat_labels[value] = (label_widget, label)
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

    def _set_stat_card(self, value_widget: QLabel, label: str, value: str) -> None:
        label_widget, _ = self._stat_labels[value_widget]
        label_widget.setText(label)
        value_widget.setText(value)

    def _restore_quota_card_labels(self) -> None:
        for value_widget in (self.search_quota_value, self.item_quota_value):
            label_widget, original = self._stat_labels[value_widget]
            label_widget.setText(original)

    def _start_scan(self) -> None:
        self._restore_quota_card_labels()
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
        if self.quota_reserve.value() <= 0:
            return []
        warnings: list[str] = []
        if summary.quota.remaining is None:
            warnings.append(
                "Quota safety buffer was not enforced because eBay did not return search-quota data."
            )
        if self.shipping_toggle.isChecked() and summary.item_quota.remaining is None:
            warnings.append(
                "Shipping quota safety was not enforced because eBay did not return item-detail quota data."
            )
        return warnings

    def _on_completed(self, summary: RunSummary) -> None:
        super()._on_completed(summary)

        # Never waste two prominent cards on the word “Unavailable.” When eBay
        # omits quota data, replace those cards with useful run results.
        if summary.quota.remaining is None:
            self._set_stat_card(self.search_quota_value, "No matches", f"{summary.no_match:,}")
        else:
            label_widget, original = self._stat_labels[self.search_quota_value]
            label_widget.setText(original)

        if summary.item_quota.remaining is None:
            if summary.skipped:
                self._set_stat_card(
                    self.item_quota_value,
                    "Failed / not scanned",
                    f"{summary.failed:,} / {summary.skipped:,}",
                )
            else:
                self._set_stat_card(self.item_quota_value, "Failed", f"{summary.failed:,}")
        else:
            label_widget, original = self._stat_labels[self.item_quota_value]
            label_widget.setText(original)

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
