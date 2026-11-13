from datetime import date
from ledger.monthly import monthly_totals
def test_empty(): assert monthly_totals([]) == {}
def test_two_months(): assert monthly_totals([(date(2026, 1, 5), 1), (date(2026, 2, 1), 2)]) == {'2026-01': 1, '2026-02': 2}
