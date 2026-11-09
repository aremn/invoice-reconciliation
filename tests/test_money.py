import pytest

from app.money import format_cents, parse_cents


@pytest.mark.parametrize("text, cents", [
    ("120.00", 12000),
    ("20", 2000),
    ("$1,200.50", 120050),
    ("USD 24.00", 2400),
    (" 0.05 ", 5),
])
def test_parse_cents(text, cents):
    assert parse_cents(text) == cents


@pytest.mark.parametrize("text", ["12.345", "abc", "", "-5.00", "NaN"])
def test_parse_cents_rejects_invalid(text):
    with pytest.raises(ValueError):
        parse_cents(text)


def test_format_cents():
    assert format_cents(12000) == "$120.00"
    assert format_cents(-2005) == "-$20.05"
    assert format_cents(123456789) == "$1,234,567.89"
