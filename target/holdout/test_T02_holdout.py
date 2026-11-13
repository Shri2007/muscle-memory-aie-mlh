import pytest
from ledger.split import split_bill
def test_sum(): assert sum(split_bill(1001, 7)) == 1001
def test_bad_n():
    with pytest.raises(ValueError): split_bill(100, 0)
