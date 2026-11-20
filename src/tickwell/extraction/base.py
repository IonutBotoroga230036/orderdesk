import ipaddress
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol
from urllib.parse import urlparse

from pydantic import ValidationError

from ..schemas import Extraction

log = logging.getLogger(__name__)


class ExtractionError(RuntimeError):
    pass


@dataclass
class CatalogEntry:
    code: str
    name: str
    pot: str | None
    price: float


@dataclass
class CustomerContext:
    id: str
    name: str
    notes: str = ""
    aliases: dict[str, str] = field(default_factory=dict)
    recent_orders: list[tuple[date, list[tuple[str, int]]]] = field(default_factory=list)


@dataclass
class ExtractionContext:
    today: date
    sender: str
    catalog: list[CatalogEntry]
    customers: list[CustomerContext]
    known_customer_id: str | None = None


class Extractor(Protocol):
    name: str

    def extract(self, text: str, ctx: ExtractionContext) -> Extraction: ...


def parse_extraction(data: dict) -> Extraction:
    """Validate a model's answer. A malformed date is dropped instead of failing the whole email."""
    data = dict(data)
    if not data.get("delivery_date"):
        data["delivery_date"] = None
    try:
        return Extraction.model_validate(data)
    except ValidationError as exc:
        log.warning("Invalid extraction from model: %s", exc)
        data["delivery_date"] = None
        try:
            return Extraction.model_validate(data)
        except ValidationError as exc2:
            raise ExtractionError(f"Model returned an invalid order: {exc2}") from exc2


def is_private_host(url: str) -> bool:
    """True for localhost, private network addresses and bare container names such as 'ollama'."""
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local") or "." not in host:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback


def get_extractor(name: str | None = None) -> Extractor:
    from ..config import get_settings

    settings = get_settings()
    name = name or settings.extractor
    if name == "heuristic":
        from .heuristic import HeuristicExtractor

        return HeuristicExtractor()
    if name in ("local", "ollama"):
        from .ollama import OllamaExtractor

        if not settings.ollama_model:
            raise ExtractionError(
                "TICKWELL_OLLAMA_MODEL is not set. Pull a model with `ollama pull <model>` and put its name in .env."
            )
        if settings.local_only and not is_private_host(settings.ollama_base_url):
            raise ExtractionError(
                f"Local-only mode is on, but TICKWELL_OLLAMA_BASE_URL ({settings.ollama_base_url}) is not on this "
                "machine or the local network."
            )
        return OllamaExtractor(base_url=settings.ollama_base_url, model=settings.ollama_model,
                               num_ctx=settings.ollama_num_ctx, timeout=settings.ollama_timeout)
    if name == "claude":
        from .claude import ClaudeExtractor

        if settings.local_only:
            raise ExtractionError("Local-only mode is on (TICKWELL_LOCAL_ONLY=true): the Claude extractor is disabled.")

        if not settings.anthropic_api_key:
            raise ExtractionError("ANTHROPIC_API_KEY is not set. Add it to .env or use --extractor heuristic.")
        return ClaudeExtractor(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
    raise ExtractionError(f"Unknown extractor: {name}")
