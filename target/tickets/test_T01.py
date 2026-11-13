from ledger.discount import apply_discount
def test_basic(): assert apply_discount(1000, 10) == 900
def test_round(): assert apply_discount(999, 50) == 500
