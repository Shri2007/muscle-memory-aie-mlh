from ledger.tax import add_tax
def test_ca(): assert add_tax(10000, 'CA') == 10725
