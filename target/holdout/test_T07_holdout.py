from ledger.merge import merge_totals
def test_no_mutation():
    a = {'a': 1}; merge_totals(a, {'a': 5}); assert a == {'a': 1}
