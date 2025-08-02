from decimal import Decimal, ROUND_HALF_UP

from utils.exchange import frankfurter_rate


def convert(amount: Decimal, frm: str, to: str) -> Decimal:
    """Convert ``amount`` from currency ``frm`` to ``to`` using cached rates."""
    if frm == to:
        return amount
    rate = frankfurter_rate(frm, to)
    return (amount * rate).quantize(Decimal("0.01"), ROUND_HALF_UP)