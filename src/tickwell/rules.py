"""Business checks applied after matching. Each rule can only make a line stricter."""

from collections import defaultdict

from .schemas import ProposedLine, worst


def apply_rules(lines: list[ProposedLine], stock: dict[str, int], history: dict[str, list[int]]) -> list[ProposedLine]:
    """stock: code -> units available. history: code -> past quantities for this customer."""
    wanted: dict[str, int] = defaultdict(int)
    for line in lines:
        if not line.removed and line.product_code:
            wanted[line.product_code] += line.quantity

    for line in lines:
        if line.removed:
            continue
        notes = [line.reason] if line.reason else []
        if line.product_code is None:
            line.status = "unknown"
        if line.quantity <= 0:
            line.status = worst(line.status, "check")
            notes.append("No quantity found.")
        code = line.product_code
        if code:
            available = stock.get(code, 0)
            if available == 0:
                line.status = worst(line.status, "check")
                notes.append("Out of stock. Keep as backorder or swap.")
            elif wanted[code] > available:
                line.status = worst(line.status, "check")
                notes.append(f"Only {available} in stock.")
            past = history.get(code, [])
            if past and line.quantity > 3 * max(past):
                line.status = worst(line.status, "check")
                notes.append(f"Much larger than usual for this customer (max {max(past)} before).")
        line.reason = " ".join(dict.fromkeys(n.strip() for n in notes if n.strip()))
    return lines
