from ledger.safe import safe_parse
def test_empty(): assert safe_parse("") is None
