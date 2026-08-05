import csv
from pathlib import Path

from openpyxl import load_workbook
import pytest

from book_resale_finder.models import SearchResult
from book_resale_finder.workbook import (
    ebay_search_url,
    inches_to_excel_width,
    write_results_csv,
    write_results_xlsx,
)


def test_csv_output_is_plain_values(tmp_path: Path):
    output = tmp_path / "results.csv"
    write_results_csv(
        [
            SearchResult(
                asin="9780306406157",
                title="A test book",
                best_price=12.34,
                condition="Very Good",
                listing_url="https://www.ebay.com/itm/123",
            )
        ],
        output,
    )
    with output.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["ASIN", "Title", "Best Price", "Condition", "Listing URL"]
    assert rows[1] == [
        "9780306406157",
        "A test book",
        "12.34",
        "Very Good",
        "https://www.ebay.com/itm/123",
    ]


def test_workbook_headers_widths_and_links(tmp_path: Path):
    output = tmp_path / "results.xlsx"
    write_results_xlsx(
        [
            SearchResult(
                asin="9780306406157",
                title="A test book",
                best_price=12.34,
                condition="Very Good",
                listing_url="https://www.ebay.com/itm/123",
            )
        ],
        output,
    )
    workbook = load_workbook(output)
    sheet = workbook["Results"]
    assert [sheet.cell(1, col).value for col in range(1, 6)] == [
        "ASIN",
        "Title",
        "Best Price",
        "Condition",
        "Listing URL",
    ]
    assert sheet.column_dimensions["A"].width == pytest.approx(inches_to_excel_width(1.5))
    assert sheet.column_dimensions["B"].width == pytest.approx(inches_to_excel_width(5.0))
    assert sheet.column_dimensions["E"].width == pytest.approx(inches_to_excel_width(8.0))
    assert sheet["A2"].hyperlink.target == ebay_search_url("9780306406157")
    assert sheet["C2"].number_format == "$0.00"
    assert sheet["E2"].hyperlink.target == "https://www.ebay.com/itm/123"
    assert sheet.freeze_panes == "A2"
