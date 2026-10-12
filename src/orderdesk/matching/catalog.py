"""Deterministic matching between what a customer wrote and the catalog.

The LLM proposes a product code, but this module has the final word: a code must exist,
a customer alias always wins, and when the catalog text barely resembles what the
customer wrote, the line goes to a person instead of being trusted.
"""

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .normalize import normalize, parse_pot, strip_sizes


@dataclass
class CatalogItem:
    code: str
    name: str
    pot: str | None


@dataclass
class MatchResult:
    code: str | None
    status: str  # ok | check | unknown
    method: str  # alias | llm | fuzzy | none
    score: float
    reason: str = ""
    alternatives: list[str] = field(default_factory=list)


class CatalogMatcher:
    def __init__(self, items: list[CatalogItem], aliases: dict[str, dict[str, str]] | None = None):
        self.items = items
        self.by_code = {i.code: i for i in items}
        self.aliases = aliases or {}  # customer_id -> {normalized alias: code}
        self._names = {i.code: normalize(i.name.replace("'", " ")) for i in items}

    # -- scoring -------------------------------------------------------------
    def text_score(self, description: str, code: str) -> float:
        """Name similarity only, ignoring pot sizes."""
        words = strip_sizes(description)
        if not words:
            return 0.0
        s = fuzz.token_set_ratio(words, self._names[code]) / 100
        return 0.7 * s + 0.3 * fuzz.partial_ratio(words, self._names[code]) / 100

    def score(self, description: str, code: str, pot: str | None = None) -> float:
        s = self.text_score(description, code)
        item_pot = self.by_code[code].pot
        if pot and item_pot:
            s += 0.12 if pot == item_pot else -0.2
        return round(max(0.0, min(1.0, s)), 3)

    def ranked(self, description: str) -> list[tuple[float, str]]:
        pot = parse_pot(description)
        return sorted(((self.score(description, c, pot), c) for c in self.by_code), reverse=True)

    def alias_for(self, description: str, customer_id: str | None) -> str | None:
        if not customer_id:
            return None
        norm = normalize(description)
        for alias, code in sorted(self.aliases.get(customer_id, {}).items(), key=lambda kv: -len(kv[0])):
            if alias == norm or re.search(rf"(?<![\w-]){re.escape(alias)}(?![\w-])", norm):
                return code
        return None

    # -- main entry ----------------------------------------------------------
    def match(self, description: str, customer_id: str | None = None, llm_code: str | None = None,
              llm_alternatives: list[str] | None = None) -> MatchResult:
        llm_alternatives = [c for c in (llm_alternatives or []) if c in self.by_code]

        alias_code = self.alias_for(description, customer_id)
        if alias_code and alias_code in self.by_code:
            return MatchResult(alias_code, "ok", "alias", 1.0, "Matched with this customer's own product name.")

        ranked = self.ranked(description)
        fuzzy_alts = [c for _, c in ranked[:3]]

        if llm_code and llm_code in self.by_code:
            s = next(sc for sc, c in ranked if c == llm_code)
            pot, item_pot = parse_pot(description), self.by_code[llm_code].pot
            pot_conflict = bool(pot and item_pot and pot != item_pot)
            if self.text_score(description, llm_code) >= 0.55 and not pot_conflict:
                return MatchResult(llm_code, "ok", "llm", s)
            alts = _dedupe(llm_alternatives + fuzzy_alts, exclude=llm_code)
            return MatchResult(llm_code, "check", "llm", s,
                               "Catalog name looks different from what the customer wrote. Confirm the product.", alts)

        if llm_alternatives:
            return MatchResult(None, "unknown", "llm", 0.0, "Several products fit. Pick one.",
                               _dedupe(llm_alternatives + fuzzy_alts))

        if not ranked or ranked[0][0] < 0.6:
            return MatchResult(None, "unknown", "none", ranked[0][0] if ranked else 0.0,
                               "No confident catalog match. Pick a product.", fuzzy_alts)
        top_score, top_code = ranked[0]
        second = ranked[1][0] if len(ranked) > 1 else 0.0
        if top_score >= 0.85 and top_score - second >= 0.08:
            return MatchResult(top_code, "ok", "fuzzy", top_score)
        return MatchResult(top_code, "check", "fuzzy", top_score, "Closest catalog match. Confirm the product.",
                           _dedupe(fuzzy_alts, exclude=top_code))


def _dedupe(codes: list[str], exclude: str | None = None) -> list[str]:
    out: list[str] = []
    for c in codes:
        if c != exclude and c not in out:
            out.append(c)
    return out[:4]
