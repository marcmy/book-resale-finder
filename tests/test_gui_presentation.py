import inspect

from book_resale_finder.gui import MainWindow
from book_resale_finder.theme import DARK, LIGHT, stylesheet


def test_light_and_dark_stylesheets_are_nonempty_and_different():
    light = stylesheet(LIGHT)
    dark = stylesheet(DARK)
    assert light
    assert dark
    assert light != dark
    assert "QDialog" in light
    assert "QDialog" in dark


def test_completion_output_keeps_results_without_repeating_tutorial():
    source = inspect.getsource(MainWindow._on_completed)
    assert "How that total was calculated" not in source
    assert "first searches" not in source
    assert "eBay requests used" in source
    assert "Elapsed time" in source
    assert "Results saved to" in source
