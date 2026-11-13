import pytest
from ledger.money import parse_amount, round_half_up


def test_parse_amount():
    assert parse_amount("$1,234.50") == 123450
    assert parse_amount("7") == 700


def test_parse_amount_bad():
    with pytest.raises(ValueError):
        parse_amount("abc")


def test_round_half_up():
    assert round_half_up(2.5) == 3
