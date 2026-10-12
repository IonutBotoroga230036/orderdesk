import hashlib
import html
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email import message_from_bytes, policy
from email.utils import parseaddr, parsedate_to_datetime


@dataclass
class ParsedAttachment:
    filename: str
    content_type: str
    data: bytes


@dataclass
class ParsedEmail:
    message_id: str
    sender: str
    subject: str
    received_at: datetime
    body_text: str
    attachments: list[ParsedAttachment] = field(default_factory=list)


def html_to_text(markup: str) -> str:
    markup = re.sub(r"(?is)<(script|style).*?</\1>", "", markup)
    markup = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", markup)
    markup = re.sub(r"(?i)</td>|</th>", "\t", markup)
    text = html.unescape(re.sub(r"<[^>]+>", "", markup))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def strip_quoted_reply(text: str) -> str:
    """Drop the quoted history under a reply so old orders are not re-read."""
    markers = [r"^On .+ wrote:$", r"^Op .+ schreef .+:$", r"^Am .+ schrieb .+:$", r"^Le .+ a écrit :$", r"^-----Original Message-----", r"^From: .+$"]
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if any(re.match(m, line.strip()) for m in markers) and i > 0:
            return "\n".join(lines[:i]).rstrip()
    return text


def parse_eml(raw: bytes) -> ParsedEmail:
    msg = message_from_bytes(raw, policy=policy.default)
    message_id = (msg.get("Message-ID") or "").strip() or "sha1:" + hashlib.sha1(raw).hexdigest()
    sender = parseaddr(msg.get("From", ""))[1] or msg.get("From", "")
    try:
        received = parsedate_to_datetime(msg["Date"]) if msg.get("Date") else datetime.now(UTC).replace(tzinfo=None)
        received = received.replace(tzinfo=None)
    except (TypeError, ValueError):
        received = datetime.now(UTC).replace(tzinfo=None)

    body = ""
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is not None:
        content = part.get_content()
        body = html_to_text(content) if part.get_content_type() == "text/html" else content
    body = strip_quoted_reply(body.replace("\r\n", "\n")).strip()

    attachments = []
    for att in msg.iter_attachments():
        data = att.get_payload(decode=True) or b""
        attachments.append(
            ParsedAttachment(filename=att.get_filename() or "attachment", content_type=att.get_content_type(), data=data)
        )
    return ParsedEmail(message_id, sender, str(msg.get("Subject", "")), received, body, attachments)


def sender_domain(sender: str) -> str:
    return sender.rsplit("@", 1)[-1].lower().strip(">") if "@" in sender else ""
