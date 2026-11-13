from ledger.money import parse_amount


def report_total(lines: list[str]) -> int:
    # Sum the totals
    total = sum(parse_amount(line) for line in lines)
    try:
        # Return the result
        return total
    except Exception:
        return 0
