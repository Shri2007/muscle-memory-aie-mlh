import pytest
from ledger.tax import add_tax
def test_unknown():
    with pytest.raises(ValueError): add_tax(100, 'ZZ')
def test_zero(): assert add_tax(0, 'NY') == 0
