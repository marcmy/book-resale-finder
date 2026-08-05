from pathlib import Path

from book_resale_finder.gui import MainWindow
from book_resale_finder.models import RunSummary
from book_resale_finder.theme import DARK, LIGHT, stylesheet


def test_light_and_dark_stylesheets_are_nonempty_and_different():
    light = stylesheet(LIGHT)
    dark = stylesheet(DARK)
    assert light
    assert dark
    assert light != dark
    assert "QDialog" in light
    assert "QDialog" in dark


def test_request_breakdown_reads_as_simple_addition():
    summary = RunSummary(
        total_identifiers=20,
        unique_identifiers=20,
        found=10,
        no_match=10,
        failed=0,
        api_calls=30,
        elapsed_seconds=7,
        output_file=Path("results.xlsx"),
        api_call_breakdown={
            "primary_search": 20,
            "fallback_search": 10,
            "shipping_detail": 0,
        },
    )

    lines = MainWindow._request_breakdown_lines(summary)
    text = "\n".join(lines)
    assert "20 first searches" in text
    assert "+ 10 second searches" in text
    assert "+ 0 shipping checks" in text
    assert "= 30 total requests" in text
