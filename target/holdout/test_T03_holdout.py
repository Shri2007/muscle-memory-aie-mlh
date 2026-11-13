from ledger.fmt import format_amount
def test_negative(): assert format_amount(-500) == '-$5.00'
def test_small(): assert format_amount(5) == '$0.05'
