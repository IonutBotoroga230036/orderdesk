from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from ..schemas import Extraction


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


def get_extractor(name: str | None = None) -> Extractor:
    from ..config import get_settings

    settings = get_settings()
    name = name or settings.extractor
    if name == "heuristic":
        from .heuristic import HeuristicExtractor

        return HeuristicExtractor()
    if name == "claude":
        from .claude import ClaudeExtractor

        if not settings.anthropic_api_key:
            raise ExtractionError("ANTHROPIC_API_KEY is not set. Add it to .env or use --extractor heuristic.")
        return ClaudeExtractor(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
    raise ExtractionError(f"Unknown extractor: {name}")
