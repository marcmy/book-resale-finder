from pathlib import Path

import pytest

from book_resale_finder.csv_input import InputFileError, read_asins


def test_reads_case_insensitive_asin_header(tmp_path: Path):
    path = tmp_path / "masterlist.csv"
    path.write_text("asin,Title\n9780306406157,Test\nB000HCWBCG,Other\n", encoding="utf-8")
    assert read_asins(path) == ["9780306406157", "B000HCWBCG"]


def test_rejects_missing_asin_header(tmp_path: Path):
    path = tmp_path / "masterlist.csv"
    path.write_text("isbn\n9780306406157\n", encoding="utf-8")
    with pytest.raises(InputFileError, match="ASIN"):
        read_asins(path)
