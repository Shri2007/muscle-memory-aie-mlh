from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def parse_amount(text: str) -> int:
    cleaned = text.strip().replace("$", "").replace(",", "")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"not an amount: {text!r}")
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def round_half_up(value: float) -> int:
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
