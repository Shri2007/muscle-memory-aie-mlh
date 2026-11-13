from ledger.fmt import format_amount
def test_fmt(): assert format_amount(123450) == '$1,234.50'
