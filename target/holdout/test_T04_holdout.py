import pytest
from ledger.rates import load_rates
def test_missing(tmp_path):
    with pytest.raises(FileNotFoundError): load_rates(str(tmp_path / 'nope.json'))
def test_bad_json(tmp_path):
    p = tmp_path / 'r.json'; p.write_text('{oops')
    with pytest.raises(ValueError): load_rates(str(p))
