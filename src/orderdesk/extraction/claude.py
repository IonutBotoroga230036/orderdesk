"""Extraction with Claude, using a forced tool call so the output is always structured JSON."""

import logging

import anthropic
from pydantic import ValidationError

from ..schemas import Extraction
from .base import ExtractionContext, ExtractionError
from .prompt import SYSTEM, build_prompt

log = logging.getLogger(__name__)

RECORD_ORDER_TOOL = {
    "name": "record_order",
    "description": "Record the draft sales order read from the email.",
    "input_schema": {
        "type": "object",
        "properties": {
            "customer_id": {"type": ["string", "null"]},
            "delivery_date": {"type": ["string", "null"], "description": "ISO date YYYY-MM-DD, or null"},
            "delivery_text": {"type": "string", "description": "The customer's own words for the delivery date"},
            "lines": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_text": {"type": "string"},
                        "description": {"type": "string", "description": "What the customer asked for, in their words"},
                        "quantity": {"type": "integer"},
                        "product_code": {"type": ["string", "null"]},
                        "status": {"type": "string", "enum": ["ok", "check", "unknown"]},
                        "reason": {"type": "string"},
                        "alternatives": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["source_text", "description", "quantity", "product_code", "status", "reason"],
                },
            },
            "removed": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_text": {"type": "string"},
                        "product_code": {"type": "string"},
                        "quantity": {"type": "integer"},
                        "reason": {"type": "string"},
                    },
                    "required": ["product_code"],
                },
            },
        },
        "required": ["customer_id", "delivery_date", "delivery_text", "lines"],
    },
}


class ClaudeExtractor:
    name = "claude"

    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-5-5", client=None, max_tokens: int = 4096):
        self.client = client or anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def extract(self, text: str, ctx: ExtractionContext) -> Extraction:
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM,
                tools=[RECORD_ORDER_TOOL],
                tool_choice={"type": "tool", "name": "record_order"},
                messages=[{"role": "user", "content": build_prompt(text, ctx)}],
            )
        except anthropic.APIError as exc:
            raise ExtractionError(f"Claude API error: {exc}") from exc

        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "record_order":
                data = dict(block.input)
                if not data.get("delivery_date"):
                    data["delivery_date"] = None
                try:
                    return Extraction.model_validate(data)
                except ValidationError as exc:
                    log.warning("Invalid extraction from model: %s", exc)
                    data["delivery_date"] = None  # most common cause: a malformed date
                    try:
                        return Extraction.model_validate(data)
                    except ValidationError as exc2:
                        raise ExtractionError(f"Model returned an invalid order: {exc2}") from exc2
        raise ExtractionError("Model did not return an order.")
