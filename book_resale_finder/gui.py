"""Book Resale Finder desktop interface with shared Browse-quota reporting."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy

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

        # The original 900-pixel window left a large amount of unused horizontal
        # space. Keep the same two-column dashboard while using a more compact,
        # tested default and minimum width.
        self.resize(760, 760)
        self.setMinimumSize(700, 680)
        root_layout = self.centralWidget().layout()
        if root_layout is not None:
            root_layout.setContentsMargins(18, 16, 18, 16)

        # Completion details already live in a scrollable text box. Let that box
        # yield vertical space first so shrinking the window never pushes the
        # scan buttons or version footer below the central widget.
        self.summary_box.setMinimumHeight(80)
        self.summary_box.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        self.retry_toggle.setText("Retry unmatched ISBNs with a broader search (recommended)")
        self.shipping_toggle.setText("Include shipping when choosing the best price")
        self.output_format.setItemText(0, "CSV — best for existing formulas")
        self.output_format.setItemText(1, "XLSX — formatted columns and links")
        self.output_format.setItemText(2, "Both CSV and XLSX")

        for label in self.findChildren(QLabel):
            if label.text() == "Keep unused quota":
                label.setText("Stop with at least")
            elif label.text() == "Search quota remaining":
                label.setText("Browse quota remaining")

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

        browse_frame = self._stat_frames[self.search_quota_value]
        search_calls_frame = self._stat_frames[self.search_calls_value]
        item_calls_frame = self._stat_frames[self.item_calls_value]
        item_quota_frame = self._stat_frames[self.item_quota_value]

        browse_frame.setToolTip(
            "Remaining calls in eBay's shared buy.browse daily quota. Searches and item-detail "
            "shipping lookups both consume this quota."
        )

        # Keep the prominent scan area stable at four metrics: identifiers,
        # matches, search calls, and shared Browse quota. Item-detail calls are
        # a shipping-only diagnostic and belong in the completion text instead.
        stats_layout = next(
            (
                layout
                for layout in self.findChildren(QGridLayout)
                if layout.indexOf(search_calls_frame) >= 0
                and layout.indexOf(item_calls_frame) >= 0
                and layout.indexOf(browse_frame) >= 0
            ),
            None,
        )
        item_calls_frame.setVisible(False)
        item_quota_frame.setVisible(False)
        if stats_layout is not None:
            stats_layout.removeWidget(item_calls_frame)
            stats_layout.removeWidget(item_quota_frame)
            stats_layout.removeWidget(browse_frame)
            stats_layout.addWidget(browse_frame, 1, 1)

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
        self._stat_frames[self.item_calls_value].setVisible(False)
        self._stat_frames[self.item_quota_value].setVisible(False)

    def _start_scan(self) -> None:
        self._set_quota_cards_visible(True)
        super()._start_scan()

    @staticmethod
    def _clean_completion_lines(text: str, *, show_item_detail: bool) -> str:
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
            if not show_item_detail and stripped.startswith("Item-detail API calls used:"):
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

        item_detail_calls = summary.api_call_breakdown.get("shipping_detail", 0)
        show_item_detail = self.shipping_toggle.isChecked() or item_detail_calls > 0
        cleaned = self._clean_completion_lines(
            self.summary_box.toPlainText(),
            show_item_detail=show_item_detail,
        )
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
