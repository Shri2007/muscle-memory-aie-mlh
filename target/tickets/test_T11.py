from ledger.safe import safe_parse
def test_ok(): assert safe_parse("$1.50") == 150
def test_bad_returns_none(): assert safe_parse("abc") is None
