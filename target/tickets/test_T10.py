from datetime import date
from ledger.monthly import monthly_totals
def test_monthly(): assert monthly_totals([(date(2026, 1, 5), 100), (date(2026, 1, 9), 50)]) == {'2026-01': 150}
