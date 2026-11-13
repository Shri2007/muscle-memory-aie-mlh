from datetime import date
from ledger.csvline import parse_line
def test_parse(): assert parse_line('2026-11-13,food,$12.50') == (date(2026, 11, 13), 'food', 1250)
