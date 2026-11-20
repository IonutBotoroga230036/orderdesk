"""What a reviewer can do with a draft: correct lines, set the customer, approve."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .erp import ERPConnector, OrderLinePayload, OrderPayload
from .matching import normalize
from .models import AuditEvent, Customer, CustomerAlias, Draft, DraftLine, Product, utcnow


class ReviewError(ValueError):
    pass


def update_line(session: Session, draft: Draft, line: DraftLine, *, product_code: str | None = None,
                quantity: int | None = None, resolved: bool | None = None, clear_product: bool = False) -> DraftLine:
    if draft.approved_at:
        raise ReviewError("This order is already approved.")
    before = {"product_code": line.product_code, "quantity": line.quantity}
    if clear_product:
        line.product_code, line.resolved = None, False
    if product_code is not None:
        if not session.get(Product, product_code):
            raise ReviewError(f"Unknown product {product_code}.")
        if product_code != line.product_code:
            line.product_corrected = True
        line.product_code, line.resolved = product_code, True
    if quantity is not None:
        if quantity < 0:
            raise ReviewError("Quantity cannot be negative.")
        line.quantity = quantity
    if resolved is not None:
        line.resolved = resolved
    changed = before != {"product_code": line.product_code, "quantity": line.quantity}
    line.edited = line.edited or changed
    session.add(AuditEvent(draft_id=draft.id, kind="line_edited" if changed else "line_confirmed",
                           detail={"line_id": line.id, "before": before,
                                   "after": {"product_code": line.product_code, "quantity": line.quantity}}))
    return line


def add_line(session: Session, draft: Draft, product_code: str, quantity: int) -> DraftLine:
    if not session.get(Product, product_code):
        raise ReviewError(f"Unknown product {product_code}.")
    line = DraftLine(position=len(draft.lines), product_code=product_code, quantity=quantity, status="ok",
                     resolved=True, edited=True, reason="Added by reviewer.", alternatives=[], match_method="manual")
    draft.lines.append(line)
    session.add(AuditEvent(draft_id=draft.id, kind="line_added", detail={"product_code": product_code, "quantity": quantity}))
    return line


def blocking_issues(draft: Draft) -> list[str]:
    issues = []
    if not draft.customer_id:
        issues.append("Choose a customer.")
    open_lines = [line for line in draft.lines if line.needs_review]
    if open_lines:
        issues.append(f"{len(open_lines)} line(s) still need a check.")
    if not any(not line.removed and line.quantity > 0 and line.product_code for line in draft.lines):
        issues.append("The order has no lines.")
    return issues


def approve(session: Session, draft: Draft, erp: ERPConnector) -> str:
    issues = blocking_issues(draft)
    if issues:
        raise ReviewError(" ".join(issues))
    customer = session.get(Customer, draft.customer_id)
    lines = [line for line in draft.lines if not line.removed and line.quantity > 0 and line.product_code]
    products = {p.code: p for p in session.scalars(select(Product).where(Product.code.in_([line.product_code for line in lines])))}

    payload = OrderPayload(
        draft_id=draft.id, customer_id=customer.id, customer_name=customer.name, customer_erp_id=customer.erp_id,
        delivery_date=draft.delivery_date, reference=draft.email.subject[:60],
        lines=[OrderLinePayload(code=line.product_code, erp_id=products[line.product_code].erp_id,
                                description=products[line.product_code].label, quantity=line.quantity,
                                unit_price=products[line.product_code].price) for line in lines],
    )
    reference = erp.create_order(payload)

    now = utcnow()
    draft.approved_at = now
    draft.erp_reference = reference
    if draft.first_viewed_at:
        draft.review_seconds = max(1, int((now - draft.first_viewed_at).total_seconds()))
    draft.email.status = "approved"
    for line in lines:
        products[line.product_code].stock = max(0, products[line.product_code].stock - line.quantity)

    learned = learn_aliases(session, draft)
    session.add(AuditEvent(draft_id=draft.id, kind="approved",
                           detail={"erp_reference": reference, "review_seconds": draft.review_seconds, "learned_aliases": learned}))
    return reference


def learn_aliases(session: Session, draft: Draft) -> list[str]:
    """Remember the customer's wording for next time, when a reviewer corrected a product
    or confirmed a match the system was unsure about (fuzzy or low-similarity matches)."""
    learned = []
    for line in draft.lines:
        if line.removed or not line.product_code or not line.description:
            continue
        confirmed_guess = line.resolved and line.status != "ok" and line.match_method in ("llm", "fuzzy", "none")
        if not (line.product_corrected or confirmed_guess):
            continue
        alias = normalize(line.description)
        if len(alias) < 3 or len(alias) > 40 or alias.isdigit():
            continue
        exists = session.scalar(select(CustomerAlias).where(CustomerAlias.customer_id == draft.customer_id,
                                                           CustomerAlias.alias == alias))
        if not exists:
            session.add(CustomerAlias(customer_id=draft.customer_id, alias=alias, product_code=line.product_code, source="learned"))
            learned.append(alias)
    return learned
