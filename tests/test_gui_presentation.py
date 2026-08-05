import inspect
from datetime import timedelta, timezone
from pathlib import Path

from book_resale_finder.gui import MainWindow
from book_resale_finder.models import QuotaInfo, RunSummary
from book_resale_finder.theme import DARK, LIGHT, stylesheet


def test_light_and_dark_stylesheets_are_nonempty_and_different():
    light = stylesheet(LIGHT)
    dark = stylesheet(DARK)
    assert light
    assert dark
    assert light != dark
    assert "QComboBox" in light
    assert "QSpinBox" in dark


def test_completion_output_keeps_results_without_repeating_tutorial():
    completion_source = inspect.getsource(MainWindow._on_completed)
    assert "How that total was calculated" not in completion_source
    assert "Matches found" in completion_source
    assert "Daily search quota remaining" in completion_source
    assert "Results saved to" in completion_source


def test_stat_cards_keep_labels_and_values_on_one_line():
    stat_source = inspect.getsource(MainWindow._stat)
    assert "QHBoxLayout" in stat_source
    assert "setMinimumWidth(90)" in stat_source
    assert "AlignRight" in stat_source
    assert "QVBoxLayout" not in stat_source


def test_quota_reserve_wording_describes_the_stop_threshold():
    build_source = inspect.getsource(MainWindow._build_ui)
    assert 'label.setText("Stop with at least")' in build_source
    assert 'setSuffix(" calls remaining")' in build_source
    assert "disable the safety buffer" in build_source


def test_quota_reset_is_converted_to_local_12_hour_time():
    eastern_daylight = timezone(timedelta(hours=-4))
    assert MainWindow._format_quota_reset(
        "2026-08-05T07:00:00.000Z", eastern_daylight
    ) == "08-05-2026 3:00 AM"


def test_invalid_quota_reset_is_left_readable():
    assert MainWindow._format_quota_reset("unknown") == "unknown"


def test_request_usage_separates_search_and_item_detail_calls():
    summary = RunSummary(
        total_identifiers=1706,
        unique_identifiers=1706,
        found=1611,
        no_match=95,
        failed=0,
        api_calls=3054,
        elapsed_seconds=0,
        output_file=Path("results.csv"),
        quota=QuotaInfo(remaining=1946),
        item_quota=QuotaInfo(remaining=5000),
        api_call_breakdown={"primary_search": 1706, "fallback_search": 1348},
    )
    assert MainWindow._format_search_usage(summary) == (
        "Search API calls used: 3,054 (1,706 first searches + 1,348 broader retries)"
    )
    assert MainWindow._format_item_usage(summary) == "Item-detail API calls used: 0"


def test_locally_adjusted_quota_is_labeled_as_estimate():
    quota = QuotaInfo(limit=5000, remaining=1946, estimated=True)
    assert "locally adjusted" in MainWindow._quota_line("Daily search quota remaining", quota)
