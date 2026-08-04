from book_resale_finder.identifiers import (
    isbn10_to_isbn13,
    is_valid_isbn10,
    is_valid_isbn13,
    normalize_identifier,
)


def test_isbn_conversion():
    assert is_valid_isbn10("0-306-40615-2")
    assert isbn10_to_isbn13("0-306-40615-2") == "9780306406157"
    assert is_valid_isbn13("9780306406157")


def test_normalizes_amazon_url_and_asin():
    result = normalize_identifier("https://www.amazon.com/dp/B000HCWBCG/ref=something")
    assert result.asin == "B000HCWBCG"
    assert result.isbn13 is None


def test_normalizes_isbn10_to_isbn13():
    result = normalize_identifier("0306406152")
    assert result.isbn13 == "9780306406157"
