"""Database tables.

The catalog, customers, aliases and order history are copied from the client's ERP.
Emails, drafts and audit events are Tickwell's own data. Every correction a reviewer
makes is logged, which is how accuracy is measured and how aliases are learned.
"""

from datetime import UTC, date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    """Naive UTC timestamp (SQLite has no time zones)."""
    return datetime.now(UTC).replace(tzinfo=None)


class Product(Base):
    __tablename__ = "products"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    pot: Mapped[str | None] = mapped_column(String(16), nullable=True)
    price: Mapped[float] = mapped_column(default=0.0)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    erp_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    @property
    def label(self) -> str:
        return f"{self.name} {self.pot}" if self.pot else self.name


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    email_domain: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    erp_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CustomerAlias(Base):
    """A customer's own word for a product, e.g. 'lavendel blauw 19' or article no. 'H-20931'."""

    __tablename__ = "customer_aliases"
    __table_args__ = (UniqueConstraint("customer_id", "alias"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    alias: Mapped[str] = mapped_column(String(255))  # stored normalized
    product_code: Mapped[str] = mapped_column(ForeignKey("products.code"))
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual | learned


class PastOrderLine(Base):
    __tablename__ = "past_order_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    order_date: Mapped[date] = mapped_column(Date)
    product_code: Mapped[str] = mapped_column(ForeignKey("products.code"))
    quantity: Mapped[int] = mapped_column(Integer)


class Email(Base):
    __tablename__ = "emails"
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[str] = mapped_column(String(512), unique=True)
    sender: Mapped[str] = mapped_column(String(512))
    subject: Mapped[str] = mapped_column(String(1024), default="")
    received_at: Mapped[datetime] = mapped_column(DateTime)
    body_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="new")  # new | drafted | approved | failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="email", cascade="all, delete-orphan")
    draft: Mapped["Draft | None"] = relationship(back_populates="email", uselist=False, cascade="all, delete-orphan")

    def full_text(self) -> str:
        parts = [self.body_text]
        for a in self.attachments:
            if a.text:
                parts.append(f"\n--- Attachment: {a.filename} ---\n{a.text}")
        return "\n".join(parts)


class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("emails.id"))
    filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(128), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    email: Mapped[Email] = relationship(back_populates="attachments")


class Draft(Base):
    __tablename__ = "drafts"
    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("emails.id"), unique=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivery_text: Mapped[str] = mapped_column(String(255), default="")
    extractor: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    first_viewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    erp_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    email: Mapped[Email] = relationship(back_populates="draft")
    lines: Mapped[list["DraftLine"]] = relationship(
        back_populates="draft", cascade="all, delete-orphan", order_by="DraftLine.position"
    )


class DraftLine(Base):
    __tablename__ = "draft_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("drafts.id"))
    position: Mapped[int] = mapped_column(Integer)
    source_text: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(String(512), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    product_code: Mapped[str | None] = mapped_column(ForeignKey("products.code"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="check")  # ok | check | unknown
    reason: Mapped[str] = mapped_column(Text, default="")
    alternatives: Mapped[list] = mapped_column(JSON, default=list)
    resolved: Mapped[bool] = mapped_column(default=False)
    removed: Mapped[bool] = mapped_column(default=False)
    edited: Mapped[bool] = mapped_column(default=False)
    product_corrected: Mapped[bool] = mapped_column(default=False)
    match_method: Mapped[str] = mapped_column(String(16), default="")  # alias | llm | fuzzy | none | manual
    draft: Mapped[Draft] = relationship(back_populates="lines")

    @property
    def needs_review(self) -> bool:
        return not self.removed and self.quantity > 0 and (self.product_code is None or (self.status != "ok" and not self.resolved))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[int | None] = mapped_column(ForeignKey("drafts.id"), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    kind: Mapped[str] = mapped_column(String(32))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
