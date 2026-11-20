"""Extraction with a local open-weight model served by Ollama (https://ollama.com).

Nothing leaves the machine or local network: the prompt goes to the Ollama server the client
runs themselves. Ollama's structured output constrains the answer to ORDER_SCHEMA, the same
shape the Claude extractor returns, so the matcher, rules and review screen work unchanged.
"""

import json
import logging

import httpx

from ..schemas import Extraction
from .base import ExtractionContext, ExtractionError, parse_extraction
from .prompt import JSON_INSTRUCTION, ORDER_SCHEMA, SYSTEM, build_prompt

log = logging.getLogger(__name__)


class OllamaExtractor:
    name = "local"

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "", num_ctx: int = 16384,
                 timeout: float = 300.0, client: httpx.Client | None = None, retries: int = 1):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.num_ctx = num_ctx
        self.retries = retries
        self.client = client or httpx.Client(timeout=timeout)

    def _chat(self, prompt: str) -> str:
        body = {
            "model": self.model,
            "stream": False,
            "format": ORDER_SCHEMA,
            "options": {"temperature": 0, "num_ctx": self.num_ctx},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        }
        try:
            resp = self.client.post(f"{self.base_url}/api/chat", json=body)
        except httpx.HTTPError as exc:
            raise ExtractionError(
                f"Could not reach Ollama at {self.base_url}. Is it running? ({exc.__class__.__name__})"
            ) from exc
        if resp.status_code == 404 and "not found" in resp.text.lower():
            raise ExtractionError(f"Model '{self.model}' is not available in Ollama. Run: ollama pull {self.model}")
        if resp.status_code >= 400:
            raise ExtractionError(f"Ollama returned {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        if data.get("done_reason") == "length":
            log.warning("Ollama hit the token limit; the answer may be cut off. Consider a larger num_ctx.")
        return (data.get("message") or {}).get("content", "")

    def extract(self, text: str, ctx: ExtractionContext) -> Extraction:
        prompt = build_prompt(text, ctx, final_instruction=JSON_INSTRUCTION)
        if len(prompt) / 3.5 > self.num_ctx * 0.8:  # rough characters-per-token estimate
            log.warning("Prompt is close to the %d-token context window; raise TICKWELL_OLLAMA_NUM_CTX.", self.num_ctx)
        last_error = "empty answer"
        for _attempt in range(self.retries + 1):
            content = self._chat(prompt).strip()
            if content.startswith("```"):  # some models wrap JSON in a code fence anyway
                content = content.strip("`").removeprefix("json").strip()
            try:
                data = json.loads(content)
            except json.JSONDecodeError as exc:
                last_error = f"invalid JSON ({exc.msg})"
                log.warning("Local model returned %s; retrying", last_error)
                continue
            if not isinstance(data, dict):
                last_error = "answer was not a JSON object"
                continue
            return parse_extraction(data)
        raise ExtractionError(f"Local model did not return a usable order: {last_error}")
