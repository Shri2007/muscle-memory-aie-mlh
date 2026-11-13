from ledger.top import top_categories
def test_top(): assert top_categories([('food', 5), ('rent', 9), ('food', 6)], 1) == ['food']
