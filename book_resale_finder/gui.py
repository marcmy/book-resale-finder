"""Book Resale Finder desktop interface with shared Browse-quota reporting."""

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
    """Apply presentation and shared Browse-quota fixes to the interface."""

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
            elif label.text() == "Search quota remaining":
                label.setText("Browse quota remaining")

        self.shipping_toggle.setText(
            "Include shipping when choosing the best price (may use additional Browse API calls)"
        )
        self.shipping_toggle.setToolTip(
            "Shipping already returned in search results is reused without another call. "
            "When it is missing, the app can make item-detail calls. Search and item-detail "
            "calls both consume the same daily eBay Browse quota."
        )

        self.quota_reserve.setSuffix(" calls remaining")
        self.quota_reserve.setToolTip(
            "The scan stops and saves partial results before the shared daily eBay Browse "
            "quota would fall below this number of remaining calls. Set it to 0 to disable "
            "the safety buffer."
        )

        self._stat_frames[self.search_quota_value].setToolTip(
            "Remaining calls in eBay's shared buy.browse daily quota. Searches and item-detail "
            "shipping lookups both consume this quota."
        )
        # buy.browse.item.bulk is a separate quota for getItems, which this app
        # does not use. Do not present it as an item-detail quota.
        self._stat_frames[self.item_quota_value].setVisible(False)

    def _refresh_estimate(self) -> None:
        super()._refresh_estimate()
        text = self.estimate_label.text()
        marker = ". The scan keeps"
        if marker in text and "shared Browse quota" not in text:
            text = text.replace(
                marker,
                ". All listed calls consume one shared Browse quota. The scan keeps",
                1,
            )
            self.estimate_label.setText(text)

    def _set_quota_cards_visible(self, browse_visible: bool, item_visible: bool = False) -> None:
        del item_visible
        self._stat_frames[self.search_quota_value].setVisible(browse_visible)
        self._stat_frames[self.item_quota_value].setVisible(False)

    def _start_scan(self) -> None:
        self._set_quota_cards_visible(True)
        super()._start_scan()

    @staticmethod
    def _clean_quota_lines(text: str) -> str:
        lines: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped in {
                "Daily search quota remaining: unavailable",
                "Daily Browse quota remaining: unavailable",
                "Daily item-detail quota remaining: unavailable",
            }:
                continue
            if stripped.startswith("Daily item-detail quota remaining:"):
                continue
            if stripped.startswith("Item-detail quota reset:"):
                continue
            line = line.replace(
                "Daily search quota remaining:",
                "Daily Browse quota remaining:",
            ).replace("Search quota reset:", "Browse quota reset:")
            lines.append(line)

        compact: list[str] = []
        for line in lines:
            if line or not compact or compact[-1]:
                compact.append(line)
        return "\n".join(compact).strip()

    def _quota_safety_warnings(self, summary: RunSummary) -> list[str]:
        reserve = self.quota_reserve.value()
        if reserve <= 0 or summary.quota.remaining is not None:
            return []
        return [
            f"eBay did not provide shared Browse-quota data, so the {reserve:,}-call safety buffer could not be enforced."
        ]

    def _on_completed(self, summary: RunSummary) -> None:
        super()._on_completed(summary)

        self._set_quota_cards_visible(summary.quota.remaining is not None)

        cleaned = self._clean_quota_lines(self.summary_box.toPlainText())
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
