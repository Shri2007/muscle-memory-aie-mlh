import pytest
from ledger.discount import apply_discount
def test_bounds():
    for p in (150, -1):
        with pytest.raises(ValueError): apply_discount(1000, p)
def test_zero(): assert apply_discount(0, 50) == 0
