from ledger.merge import merge_totals
def test_merge(): assert merge_totals({'a': 1}, {'a': 2, 'b': 3}) == {'a': 3, 'b': 3}
