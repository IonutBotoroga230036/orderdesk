"""Offline fallback: finds simple "quantity + product" lines with regular expressions.

It handles tidy lists and order tables and nothing else. It exists so the system runs
without an API key, and as a baseline in evaluations: the gap between this and Claude
on vague emails ("same as last week, double the salvias") is the product's value.
"""

import re

from ..schemas import ExtractedLine, Extraction
from .base import ExtractionContext

QTY_FIRST = re.compile(r"^\s*(?:[-*•]\s*)?(\d{1,5})\s*(?:x|×|st\.?|stuks|stk\.?|pcs)?\s+([^\d\s].{1,80}?)\s*$", re.I)
QTY_LAST = re.compile(r"^\s*(.{3,80}?)[\s\t]+(\d{1,5})\s*(?:st\.?|stk\.?|pcs)?\s*$", re.I)
SKIP = re.compile(
    r"(tel|phone|fax|kvk|btw|vat|iban|postbus|straat|street|nr\.|order\s*no|bestellung|liefertermin|levering|"
    r"delivery|livraison|\b(kw|wk|week)\s*\d)",
    re.I,
)


class HeuristicExtractor:
    name = "heuristic"

    def extract(self, text: str, ctx: ExtractionContext) -> Extraction:
        lines: list[ExtractedLine] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line or SKIP.search(line):
                continue
            m = QTY_FIRST.match(line)
            if m:
                qty, desc = int(m.group(1)), m.group(2)
            else:
                m = QTY_LAST.match(line)
                if not m or not re.search(r"[A-Za-zÀ-ÿ]{3,}", m.group(1)):
                    continue
                desc, qty = m.group(1), int(m.group(2))
            if qty <= 0 or qty > 50000:
                continue
            lines.append(ExtractedLine(source_text=line, description=desc.strip(" -:\t"), quantity=qty, status="check"))
        return Extraction(customer_id=ctx.known_customer_id, lines=lines)
