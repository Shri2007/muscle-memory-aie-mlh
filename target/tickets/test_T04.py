import json
from ledger.rates import load_rates
def test_load(tmp_path):
    p = tmp_path / 'r.json'; p.write_text(json.dumps({'EUR': 0.9}))
    assert load_rates(str(p)) == {'EUR': 0.9}
