import pytest
from ledger.top import top_categories
def test_ties(): assert top_categories([('b', 1), ('a', 1)], 2) == ['a', 'b']
def test_bad_k():
    with pytest.raises(ValueError): top_categories([], -1)
