from types import SimpleNamespace

from conftest import email_by_subject

from tickwell.extraction.claude import ClaudeExtractor
from tickwell.extraction.heuristic import HeuristicExtractor
from tickwell.pipeline import draft_email, propose


def test_heuristic_drafts_tidy_list(session):
    email = email_by_subject(session, "Bestelling donderdag")
    p = propose(session, email, HeuristicExtractor())
    assert p.customer_id == "C1023"
    got = {(line.product_code, line.quantity) for line in p.lines}
    assert got == {("LAV-HID-P19", 240), ("HYD-ANN-C5", 60), ("BUX-SEM-P15", 500), ("GER-ROZ-P13", 120)}


def test_heuristic_reads_pdf_with_customer_article_numbers(session):
    p = propose(session, email_by_subject(session, "Bestellung Nr. 4471"), HeuristicExtractor())
    codes = {line.product_code for line in p.lines}
    assert {"HYD-ANN-C5", "PRU-LAU-C5", "ROS-BON-C3"} <= codes
    bonica = next(line for line in p.lines if line.product_code == "ROS-BON-C3")
    assert bonica.status == "check" and "Out of stock" in bonica.reason


class FakeMessages:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        block = SimpleNamespace(type="tool_use", name="record_order", input=self.payload)
        return SimpleNamespace(content=[block])


def fake_claude(payload):
    client = SimpleNamespace(messages=FakeMessages(payload))
    return ClaudeExtractor(client=client), client


def test_claude_extraction_flow(session):
    payload = {
        "customer_id": "C1177", "delivery_date": "2026-10-20", "delivery_text": "Tuesday the 20th",
        "lines": [
            {"source_text": "double the Salvias", "description": "Salvia Caradonna, doubled", "quantity": 300,
             "product_code": "SAL-CAR-P13", "status": "ok", "reason": "Last week 150, doubled."},
            {"source_text": "repeat last week's order", "description": "Nepeta Walker's Low", "quantity": 100,
             "product_code": "NEP-WAL-P13", "status": "ok", "reason": "From last week."},
            {"source_text": "10 olive trees, the big ones", "description": "olive trees, big", "quantity": 10,
             "product_code": "OLE-EUR-C10", "status": "check", "reason": "Largest size assumed."},
            {"source_text": "x", "description": "made up", "quantity": 5, "product_code": "FAKE-1", "status": "ok", "reason": ""},
        ],
        "removed": [{"source_text": "drop the roses", "product_code": "ROS-ICE-C3", "quantity": 40, "reason": "Dropped."}],
    }
    extractor, client = fake_claude(payload)
    email = email_by_subject(session, "Repeat order + olives")
    draft = draft_email(session, email, extractor)
    session.flush()

    call = client.messages.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": "record_order"}
    assert "C1177" in call["messages"][0]["content"] and "C1023" not in call["messages"][0]["content"]  # no data from other customers

    by_code = {line.product_code: line for line in draft.lines}
    assert by_code["SAL-CAR-P13"].quantity == 300 and by_code["SAL-CAR-P13"].status == "ok"
    assert by_code["OLE-EUR-C10"].status == "check"
    assert by_code["ROS-ICE-C3"].removed
    invented = next(line for line in draft.lines if line.description == "made up")
    assert invented.product_code is None and invented.status == "unknown"  # invented codes are never trusted
    assert str(draft.delivery_date) == "2026-10-20"


def test_bad_date_from_model_does_not_crash(session):
    extractor, _ = fake_claude({"customer_id": None, "delivery_date": "next thursday", "delivery_text": "", "lines": []})
    draft = draft_email(session, email_by_subject(session, "grassen"), extractor)
    assert draft is not None and draft.delivery_date is None
