"""The local (Ollama) extractor, tested against a simulated Ollama server."""

import json

import httpx
import pytest
from conftest import email_by_subject

from orderdesk.extraction import ExtractionError, get_extractor
from orderdesk.extraction.base import is_private_host
from orderdesk.extraction.ollama import OllamaExtractor
from orderdesk.pipeline import draft_email

BRIGHTWELL = {
    "customer_id": "C1177", "delivery_date": "2026-10-20", "delivery_text": "Tuesday the 20th",
    "lines": [
        {"source_text": "double the Salvias", "description": "Salvia Caradonna", "quantity": 300,
         "product_code": "SAL-CAR-P13", "status": "ok", "reason": "Last week 150, doubled."},
        {"source_text": "10 olive trees, the big ones", "description": "olive trees", "quantity": 10,
         "product_code": "OLE-EUR-C10", "status": "check", "reason": "Largest size assumed."},
    ],
    "removed": [{"source_text": "drop the roses", "product_code": "ROS-ICE-C3", "quantity": 40, "reason": "Dropped."}],
}


def fake_ollama(*answers, status=200):
    """An httpx client whose /api/chat replies with the given answers in turn, recording each request."""
    seen, queue = [], list(answers)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        content = queue.pop(0) if queue else ""
        if status != 200:
            return httpx.Response(status, text=content)
        if not isinstance(content, str):
            content = json.dumps(content)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": content}, "done_reason": "stop"})

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_local_extraction_through_the_pipeline(session):
    client, seen = fake_ollama(BRIGHTWELL)
    extractor = OllamaExtractor(model="test-model", client=client)
    draft = draft_email(session, email_by_subject(session, "Repeat order + olives"), extractor)
    session.flush()

    req = seen[0]
    assert req["model"] == "test-model" and req["stream"] is False
    assert req["format"]["required"] == ["customer_id", "delivery_date", "delivery_text", "lines"]
    assert req["options"] == {"temperature": 0, "num_ctx": 16384}
    assert "JSON object" in req["messages"][1]["content"] and "record_order" not in req["messages"][1]["content"]

    by_code = {line.product_code: line for line in draft.lines}
    assert draft.extractor == "local"
    assert by_code["SAL-CAR-P13"].quantity == 300 and by_code["OLE-EUR-C10"].status == "check"
    assert by_code["ROS-ICE-C3"].removed


def test_code_fenced_json_is_accepted(session):
    client, _ = fake_ollama("```json\n" + json.dumps(BRIGHTWELL) + "\n```")
    draft = draft_email(session, email_by_subject(session, "Repeat order + olives"), OllamaExtractor(model="m", client=client))
    assert draft is not None and len(draft.lines) == 3


def test_invalid_json_is_retried_once(session):
    client, seen = fake_ollama("{not json", BRIGHTWELL)
    draft = draft_email(session, email_by_subject(session, "Repeat order + olives"), OllamaExtractor(model="m", client=client))
    assert draft is not None and len(seen) == 2


def test_gives_up_with_a_clear_error(session):
    client, _ = fake_ollama("nope", "still nope")
    email = email_by_subject(session, "grassen")
    assert draft_email(session, email, OllamaExtractor(model="m", client=client)) is None
    assert email.status == "failed" and "invalid JSON" in email.error


def test_missing_model_message():
    client, _ = fake_ollama('{"error":"model \\"m\\" not found, try pulling it first"}', status=404)
    with pytest.raises(ExtractionError, match="ollama pull m"):
        OllamaExtractor(model="m", client=client)._chat("hi")


def test_ollama_not_running():
    def refuse(request):
        raise httpx.ConnectError("refused")

    ex = OllamaExtractor(model="m", client=httpx.Client(transport=httpx.MockTransport(refuse)))
    with pytest.raises(ExtractionError, match="Is it running"):
        ex._chat("hi")


def test_private_host_detection():
    for url in ["http://localhost:11434", "http://127.0.0.1:11434", "http://ollama:11434",
                "http://192.168.1.20:11434", "http://10.0.0.5", "http://orderbox.local:11434"]:
        assert is_private_host(url), url
    for url in ["https://api.example.com", "http://8.8.8.8:11434", ""]:
        assert not is_private_host(url), url


def settings_with(monkeypatch, **env):
    from orderdesk.config import get_settings

    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()


def test_local_only_mode_blocks_cloud(env, monkeypatch):
    settings_with(monkeypatch, ORDERDESK_LOCAL_ONLY="true", ANTHROPIC_API_KEY="sk-test",
                  ORDERDESK_OLLAMA_MODEL="m", ORDERDESK_OLLAMA_BASE_URL="https://ollama.example.com")
    with pytest.raises(ExtractionError, match="Claude extractor is disabled"):
        get_extractor("claude")
    with pytest.raises(ExtractionError, match="not on this machine"):
        get_extractor("local")
    settings_with(monkeypatch, ORDERDESK_OLLAMA_BASE_URL="http://ollama:11434")
    assert get_extractor("local").name == "local"
    assert get_extractor("heuristic").name == "heuristic"


def test_local_needs_a_model_name(env, monkeypatch):
    settings_with(monkeypatch, ORDERDESK_OLLAMA_MODEL="")
    with pytest.raises(ExtractionError, match="ORDERDESK_OLLAMA_MODEL"):
        get_extractor("local")
