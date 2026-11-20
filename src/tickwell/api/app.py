import secrets
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import review
from ..config import get_settings
from ..db import init_db, new_session
from ..erp import ERPError, get_erp
from ..extraction import ExtractionError, get_extractor
from ..ingest import get_mail_source, ingest
from ..models import Customer, Draft, DraftLine, Email, Product
from ..pipeline import draft_email, mark_viewed

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
basic = HTTPBasic(auto_error=False)


def get_session() -> Iterator[Session]:
    session = new_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def require_auth(creds: HTTPBasicCredentials | None = Depends(basic)) -> None:
    s = get_settings()
    if not s.ui_password:
        return
    ok = creds is not None and secrets.compare_digest(creds.username, s.ui_user or "") and \
        secrets.compare_digest(creds.password, s.ui_password)
    if not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required", headers={"WWW-Authenticate": "Basic"})


class LinePatch(BaseModel):
    product_code: str | None = None
    quantity: int | None = None
    resolved: bool | None = None
    clear_product: bool = False


class DraftPatch(BaseModel):
    customer_id: str | None = None


class NewLine(BaseModel):
    product_code: str
    quantity: int


def email_summary(e: Email) -> dict:
    return {"id": e.id, "sender": e.sender, "subject": e.subject, "received_at": e.received_at.isoformat(),
            "status": e.status, "has_attachments": bool(e.attachments),
            "customer_name": None}


def draft_dict(d: Draft, session: Session) -> dict:
    customer = session.get(Customer, d.customer_id) if d.customer_id else None
    return {
        "id": d.id, "customer_id": d.customer_id, "customer_name": customer.name if customer else None,
        "delivery_date": d.delivery_date.isoformat() if d.delivery_date else None, "delivery_text": d.delivery_text,
        "extractor": d.extractor, "approved_at": d.approved_at.isoformat() if d.approved_at else None,
        "review_seconds": d.review_seconds, "erp_reference": d.erp_reference,
        "blocking_issues": review.blocking_issues(d),
        "lines": [{
            "id": line.id, "position": line.position, "source_text": line.source_text, "description": line.description,
            "quantity": line.quantity, "product_code": line.product_code, "status": line.status, "reason": line.reason,
            "alternatives": line.alternatives or [], "resolved": line.resolved, "removed": line.removed,
            "needs_review": line.needs_review,
        } for line in d.lines],
    }


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db()
        yield

    app = FastAPI(title="Tickwell", version="0.1.0", lifespan=lifespan)
    auth = [Depends(require_auth)]

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/emails", dependencies=auth)
    def list_emails(session: Session = Depends(get_session)):
        emails = session.scalars(select(Email).order_by(Email.received_at.desc())).all()
        out = []
        for e in emails:
            row = email_summary(e)
            if e.draft and e.draft.customer_id:
                c = session.get(Customer, e.draft.customer_id)
                row["customer_name"] = c.name if c else None
            out.append(row)
        return out

    @app.get("/api/emails/{email_id}", dependencies=auth)
    def get_email(email_id: int, session: Session = Depends(get_session)):
        e = session.get(Email, email_id) or _404("Email")
        if e.draft:
            mark_viewed(e.draft)
        return {**email_summary(e), "body_text": e.body_text, "error": e.error,
                "attachments": [{"filename": a.filename, "text": a.text} for a in e.attachments],
                "draft": draft_dict(e.draft, session) if e.draft else None}

    @app.post("/api/emails/{email_id}/draft", dependencies=auth)
    def make_draft(email_id: int, extractor: str | None = None, session: Session = Depends(get_session)):
        e = session.get(Email, email_id) or _404("Email")
        if e.draft and e.draft.approved_at:
            raise HTTPException(409, "This order is already approved.")
        try:
            ex = get_extractor(extractor)
        except ExtractionError as exc:
            raise HTTPException(400, str(exc)) from exc
        d = draft_email(session, e, ex)
        session.flush()
        if d is None:
            raise HTTPException(502, e.error or "Drafting failed.")
        mark_viewed(d)
        return draft_dict(d, session)

    @app.patch("/api/drafts/{draft_id}", dependencies=auth)
    def patch_draft(draft_id: int, body: DraftPatch, session: Session = Depends(get_session)):
        d = session.get(Draft, draft_id) or _404("Draft")
        if body.customer_id is not None:
            if body.customer_id and not session.get(Customer, body.customer_id):
                raise HTTPException(400, "Unknown customer.")
            d.customer_id = body.customer_id or None
        return draft_dict(d, session)

    @app.patch("/api/drafts/{draft_id}/lines/{line_id}", dependencies=auth)
    def patch_line(draft_id: int, line_id: int, body: LinePatch, session: Session = Depends(get_session)):
        d = session.get(Draft, draft_id) or _404("Draft")
        line = session.get(DraftLine, line_id)
        if not line or line.draft_id != d.id:
            _404("Line")
        try:
            review.update_line(session, d, line, product_code=body.product_code, quantity=body.quantity,
                               resolved=body.resolved, clear_product=body.clear_product)
        except review.ReviewError as exc:
            raise HTTPException(400, str(exc)) from exc
        session.flush()
        return draft_dict(d, session)

    @app.post("/api/drafts/{draft_id}/lines", dependencies=auth)
    def post_line(draft_id: int, body: NewLine, session: Session = Depends(get_session)):
        d = session.get(Draft, draft_id) or _404("Draft")
        try:
            review.add_line(session, d, body.product_code, body.quantity)
        except review.ReviewError as exc:
            raise HTTPException(400, str(exc)) from exc
        session.flush()
        return draft_dict(d, session)

    @app.post("/api/drafts/{draft_id}/approve", dependencies=auth)
    def approve(draft_id: int, session: Session = Depends(get_session)):
        d = session.get(Draft, draft_id) or _404("Draft")
        if d.approved_at:
            raise HTTPException(409, "Already approved.")
        try:
            review.approve(session, d, get_erp())
        except (review.ReviewError, ERPError) as exc:
            raise HTTPException(400, str(exc)) from exc
        session.flush()
        return draft_dict(d, session)

    @app.post("/api/ingest", dependencies=auth)
    def run_ingest(session: Session = Depends(get_session)):
        try:
            new = ingest(session, get_mail_source())
        except (OSError, ValueError, RuntimeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"new_emails": len(new)}

    @app.get("/api/products", dependencies=auth)
    def products(session: Session = Depends(get_session)):
        return [{"code": p.code, "name": p.name, "pot": p.pot, "label": p.label, "price": p.price, "stock": p.stock}
                for p in session.scalars(select(Product).order_by(Product.name))]

    @app.get("/api/customers", dependencies=auth)
    def customers(session: Session = Depends(get_session)):
        return [{"id": c.id, "name": c.name} for c in session.scalars(select(Customer).order_by(Customer.name))]

    @app.get("/api/stats", dependencies=auth)
    def stats(session: Session = Depends(get_session)):
        approved = session.scalar(select(func.count(Draft.id)).where(Draft.approved_at.is_not(None))) or 0
        avg = session.scalar(select(func.avg(Draft.review_seconds)).where(Draft.review_seconds.is_not(None)))
        open_ = session.scalar(select(func.count(Email.id)).where(Email.status.in_(["new", "drafted", "failed"]))) or 0
        return {"approved": approved, "open": open_, "avg_review_seconds": round(avg) if avg else None}

    @app.get("/", include_in_schema=False, dependencies=auth)
    def index():
        return FileResponse(WEB_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
    return app


def _404(what: str):
    raise HTTPException(404, f"{what} not found")


app = create_app()
