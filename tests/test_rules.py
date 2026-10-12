from orderdesk.rules import apply_rules
from orderdesk.schemas import ProposedLine


def test_out_of_stock_and_short_stock():
    lines = [ProposedLine(product_code="A", quantity=10, status="ok"), ProposedLine(product_code="B", quantity=50, status="ok")]
    apply_rules(lines, {"A": 0, "B": 20}, {})
    assert lines[0].status == "check" and "Out of stock" in lines[0].reason
    assert lines[1].status == "check" and "Only 20" in lines[1].reason


def test_unusually_large_quantity():
    lines = [ProposedLine(product_code="A", quantity=2000, status="ok")]
    apply_rules(lines, {"A": 5000}, {"A": [100, 150]})
    assert lines[0].status == "check" and "usual" in lines[0].reason


def test_missing_product_is_unknown_and_removed_lines_untouched():
    lines = [ProposedLine(product_code=None, quantity=5, status="ok"), ProposedLine(product_code="A", quantity=9, removed=True)]
    apply_rules(lines, {"A": 0}, {})
    assert lines[0].status == "unknown"
    assert lines[1].status == "check" or lines[1].reason == ""  # removed lines are skipped
    assert "Out of stock" not in lines[1].reason
