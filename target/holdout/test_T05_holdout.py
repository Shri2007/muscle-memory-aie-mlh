import pytest
from ledger.convert import convert
def test_half(): assert convert(1, 0.5) == 1
def test_bad_rate():
    with pytest.raises(ValueError): convert(100, 0)
