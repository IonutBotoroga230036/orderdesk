import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Attachment, Email
from ..parsing import extract_attachment_text, parse_eml
from .base import MailSource

log = logging.getLogger(__name__)


def store_email(session: Session, raw: bytes) -> Email | None:
    parsed = parse_eml(raw)
    if session.scalar(select(Email.id).where(Email.message_id == parsed.message_id)):
        return None
    email = Email(message_id=parsed.message_id, sender=parsed.sender, subject=parsed.subject,
                  received_at=parsed.received_at, body_text=parsed.body_text)
    for att in parsed.attachments:
        email.attachments.append(Attachment(
            filename=att.filename, content_type=att.content_type,
            text=extract_attachment_text(att.filename, att.content_type, att.data),
        ))
    session.add(email)
    return email


def ingest(session: Session, source: MailSource) -> list[Email]:
    new = []
    for raw in source.fetch():
        try:
            email = store_email(session, raw)
        except Exception as exc:  # one malformed message must not block the inbox
            log.exception("Could not store a message: %s", exc)
            continue
        if email:
            new.append(email)
    session.flush()
    return new
