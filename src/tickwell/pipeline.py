"""Email in, draft out: context -> extraction -> catalog matching -> business rules -> saved draft."""

import logging
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from .extraction import ExtractionContext, ExtractionError, Extractor
from .extraction.base import CatalogEntry, CustomerContext
from .matching import CatalogMatcher
from .matching.catalog import CatalogItem
from .models import (
    AuditEvent,
    Customer,
    CustomerAlias,
    Draft,
    DraftLine,
    Email,
    PastOrderLine,
    Product,
    utcnow,
)
from .parsing import sender_domain
from .rules import apply_rules
from .schemas import Proposal, ProposedLine, worst

log = logging.getLogger(__name__)


def identify_customer(session: Session, sender: str) -> str | None:
    domain = sender_domain(sender)
    if not domain:
        return None
    return session.scalar(select(Customer.id).where(Customer.email_domain == domain))


def load_aliases(session: Session) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = defaultdict(dict)
    for a in session.scalars(select(CustomerAlias)):
        out[a.customer_id][a.alias] = a.product_code
    return out


def recent_orders(session: Session, customer_id: str, limit: int = 3):
    rows = session.scalars(
        select(PastOrderLine).where(PastOrderLine.customer_id == customer_id).order_by(PastOrderLine.order_date.desc())
    ).all()
    by_date: dict = defaultdict(list)
    for r in rows:
        by_date[r.order_date].append((r.product_code, r.quantity))
    dates = sorted(by_date, reverse=True)[:limit]
    return [(d, by_date[d]) for d in dates]


def build_context(session: Session, email: Email, customer_id: str | None) -> ExtractionContext:
    products = session.scalars(select(Product).order_by(Product.code)).all()
    aliases = load_aliases(session)
    # Known sender: only their context goes in the prompt (smaller, and no data leaks between customers).
    customers = [session.get(Customer, customer_id)] if customer_id else session.scalars(select(Customer)).all()
    return ExtractionContext(
        today=email.received_at.date(),
        sender=email.sender,
        catalog=[CatalogEntry(p.code, p.name, p.pot, p.price) for p in products],
        customers=[
            CustomerContext(c.id, c.name, c.notes or "", aliases.get(c.id, {}), recent_orders(session, c.id))
            for c in customers
            if c is not None
        ],
        known_customer_id=customer_id,
    )


def propose(session: Session, email: Email, extractor: Extractor) -> Proposal:
    """Run extraction, matching and rules without saving anything (also used by evaluation)."""
    customer_id = identify_customer(session, email.sender)
    ctx = build_context(session, email, customer_id)
    extraction = extractor.extract(email.full_text(), ctx)

    if not customer_id and extraction.customer_id and session.get(Customer, extraction.customer_id):
        customer_id = extraction.customer_id

    products = session.scalars(select(Product)).all()
    matcher = CatalogMatcher([CatalogItem(p.code, p.name, p.pot) for p in products], load_aliases(session))

    lines: list[ProposedLine] = []
    for x in extraction.lines:
        m = matcher.match(x.description or x.source_text, customer_id, x.product_code, x.alternatives)
        reasons = [r for r in (x.reason, m.reason) if r]
        lines.append(ProposedLine(
            source_text=x.source_text, description=x.description or x.source_text, quantity=max(0, x.quantity),
            product_code=m.code, status=worst(x.status if x.product_code else "ok", m.status),
            reason=" ".join(dict.fromkeys(reasons)), alternatives=m.alternatives, match_method=m.method,
        ))
    for r in extraction.removed:
        if session.get(Product, r.product_code):
            lines.append(ProposedLine(source_text=r.source_text, description=r.source_text, quantity=r.quantity,
                                      product_code=r.product_code, status="ok", reason=r.reason, removed=True))

    stock = {p.code: p.stock for p in products}
    history: dict[str, list[int]] = defaultdict(list)
    if customer_id:
        for row in session.scalars(select(PastOrderLine).where(PastOrderLine.customer_id == customer_id)):
            history[row.product_code].append(row.quantity)
    apply_rules(lines, stock, history)

    return Proposal(customer_id=customer_id, delivery_date=extraction.delivery_date,
                    delivery_text=extraction.delivery_text, extractor=extractor.name, lines=lines)


def save_draft(session: Session, email: Email, proposal: Proposal) -> Draft:
    if email.draft is not None:
        session.delete(email.draft)
        session.flush()
    draft = Draft(email_id=email.id, customer_id=proposal.customer_id, delivery_date=proposal.delivery_date,
                  delivery_text=proposal.delivery_text or "", extractor=proposal.extractor)
    for i, p in enumerate(proposal.lines):
        draft.lines.append(DraftLine(
            position=i, source_text=p.source_text, description=p.description, quantity=p.quantity,
            product_code=p.product_code, status=p.status, reason=p.reason, alternatives=p.alternatives,
            resolved=p.status == "ok", removed=p.removed, match_method=p.match_method,
        ))
    session.add(draft)
    email.status = "drafted"
    email.error = None
    session.flush()
    session.add(AuditEvent(draft_id=draft.id, kind="drafted", detail={
        "extractor": proposal.extractor,
        "lines": len([line for line in proposal.lines if not line.removed]),
        "needs_review": len([line for line in proposal.lines if not line.removed and line.status != "ok"]),
    }))
    return draft


def draft_email(session: Session, email: Email, extractor: Extractor) -> Draft | None:
    try:
        proposal = propose(session, email, extractor)
    except ExtractionError as exc:
        email.status, email.error = "failed", str(exc)
        log.error("Drafting email %s failed: %s", email.id, exc)
        return None
    return save_draft(session, email, proposal)


def draft_pending(session: Session, extractor: Extractor) -> list[Draft]:
    emails = session.scalars(select(Email).where(Email.status.in_(["new", "failed"])).order_by(Email.received_at)).all()
    drafts = []
    for e in emails:
        d = draft_email(session, e, extractor)
        if d:
            drafts.append(d)
    session.flush()
    return drafts


def mark_viewed(draft: Draft) -> None:
    if draft.first_viewed_at is None:
        draft.first_viewed_at = utcnow()
