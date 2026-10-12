from conftest import SAMPLE

from orderdesk.parsing import extract_attachment_text, parse_eml, sender_domain
from orderdesk.parsing.email_parser import html_to_text, strip_quoted_reply


def test_parse_eml_with_pdf():
    parsed = parse_eml((SAMPLE / "emails" / "03-hoffmann.eml").read_bytes())
    assert parsed.sender == "einkauf@gc-hoffmann.de"
    assert "KW 43" in parsed.body_text
    assert parsed.attachments[0].filename == "Bestellung_4471.pdf"
    text = extract_attachment_text(parsed.attachments[0].filename, parsed.attachments[0].content_type, parsed.attachments[0].data)
    assert "H-20931" in text and "Fächerahorn" in text


def test_sender_domain():
    assert sender_domain("inkoop@DeLinde.nl") == "delinde.nl"
    assert sender_domain("nobody") == ""


def test_html_and_quotes():
    assert html_to_text("<p>200 Photinia</p><p>50 laurier</p>") == "200 Photinia\n50 laurier"
    text = "Please send 20 more.\n\nOn Mon, 5 Oct 2026, GreenLine wrote:\n> old order 500 buxus"
    assert strip_quoted_reply(text) == "Please send 20 more."


def test_broken_attachment_is_ignored():
    assert extract_attachment_text("order.pdf", "application/pdf", b"not a pdf") == ""
