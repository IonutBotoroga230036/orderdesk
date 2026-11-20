"""Shapes passed between pipeline steps (not database tables)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["ok", "check", "unknown"]
SEVERITY = {"ok": 0, "check": 1, "unknown": 2}


def worst(*statuses: str) -> str:
    return max(statuses, key=lambda s: SEVERITY.get(s, 1))


class ExtractedLine(BaseModel):
    source_text: str = ""
    description: str = ""
    quantity: int = 0
    product_code: str | None = None
    status: Status = "check"
    reason: str = ""
    alternatives: list[str] = Field(default_factory=list)


class ExtractedRemoval(BaseModel):
    source_text: str = ""
    product_code: str
    quantity: int = 0
    reason: str = ""


class Extraction(BaseModel):
    customer_id: str | None = None
    delivery_date: date | None = None
    delivery_text: str = ""
    lines: list[ExtractedLine] = Field(default_factory=list)
    removed: list[ExtractedRemoval] = Field(default_factory=list)


class ProposedLine(BaseModel):
    source_text: str = ""
    description: str = ""
    quantity: int = 0
    product_code: str | None = None
    status: Status = "check"
    reason: str = ""
    alternatives: list[str] = Field(default_factory=list)
    removed: bool = False
    match_method: str = ""


class Proposal(BaseModel):
    customer_id: str | None = None
    delivery_date: date | None = None
    delivery_text: str = ""
    extractor: str = ""
    lines: list[ProposedLine] = Field(default_factory=list)
