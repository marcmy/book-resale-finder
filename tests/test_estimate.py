from pathlib import Path

from book_resale_finder.estimate import estimate_calls


def test_estimate_accounts_for_retry_and_shipping(tmp_path: Path):
    source = tmp_path / "list.csv"
    source.write_text(
        "ASIN\n9780306406157\n9780306406157\nB000HCWBCG\n",
        encoding="utf-8",
    )
    estimate = estimate_calls(
        source,
        retry_unmatched=True,
        include_shipping=True,
        shipping_item_limit=3,
    )
    assert estimate.total_identifiers == 3
    assert estimate.unique_identifiers == 2
    assert estimate.search_min == 2
    assert estimate.search_max == 3
    assert estimate.item_detail_max == 6


def test_one_pass_estimate_matches_original_tool_behavior(tmp_path: Path):
    source = tmp_path / "list.csv"
    source.write_text("ASIN\n9780306406157\nB000HCWBCG\n", encoding="utf-8")
    estimate = estimate_calls(
        source,
        retry_unmatched=False,
        include_shipping=False,
        shipping_item_limit=3,
    )
    assert estimate.search_min == 2
    assert estimate.search_max == 2
    assert estimate.item_detail_max == 0
