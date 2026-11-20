"""Extraction with Claude, using a forced tool call so the output is always structured JSON."""

import logging

import anthropic

from ..schemas import Extraction
from .base import ExtractionContext, ExtractionError, parse_extraction
from .prompt import ORDER_SCHEMA, SYSTEM, build_prompt

log = logging.getLogger(__name__)

RECORD_ORDER_TOOL = {
    "name": "record_order",
    "description": "Record the draft sales order read from the email.",
    "input_schema": ORDER_SCHEMA,
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
                return parse_extraction(dict(block.input))
        raise ExtractionError("Model did not return an order.")
