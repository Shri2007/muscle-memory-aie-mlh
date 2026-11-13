import pytest
from ledger.csvline import parse_line
@pytest.mark.parametrize('line', ['bad', '2026-13-01,food,$1', '2026-01-01,food,abc'])
def test_bad(line):
    with pytest.raises(ValueError): parse_line(line)
