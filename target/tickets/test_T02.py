from ledger.split import split_bill
def test_split(): assert split_bill(100, 3) == [34, 33, 33]
