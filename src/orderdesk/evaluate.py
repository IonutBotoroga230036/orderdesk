"""Shadow test: compare drafted orders with what was actually entered.

Give it past emails plus the orders a person typed for them (ground truth). It reports how
many lines the system gets right, and, most importantly for trust, how often a line it marks
"ok" is actually wrong. Run this on a client's real history before go-live.
"""

import json
from collections import Counter
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .extraction import ExtractionError, Extractor
from .models import Email
from .pipeline import propose


def evaluate(session: Session, truth_path: Path, extractor: Extractor) -> dict:
    truth = json.loads(Path(truth_path).read_text(encoding="utf-8"))
    rows, tot = [], Counter()
    for case in truth["emails"]:
        email = session.scalar(select(Email).where(Email.message_id == case["message_id"]))
        if email is None:
            rows.append({"message_id": case["message_id"], "error": "email not ingested"})
            continue
        expected = Counter((x["product_code"], int(x["quantity"])) for x in case["expected"])
        try:
            proposal = propose(session, email, extractor)
        except ExtractionError as exc:
            rows.append({"message_id": case["message_id"], "subject": email.subject, "error": str(exc)})
            tot["expected"] += sum(expected.values())
            continue
        lines = [line for line in proposal.lines if not line.removed and line.product_code and line.quantity > 0]
        predicted = Counter((line.product_code, line.quantity) for line in lines)
        correct = sum((predicted & expected).values())
        ok_lines = [line for line in lines if line.status == "ok"]
        ok_wrong = sum(1 for line in ok_lines if expected[(line.product_code, line.quantity)] == 0)
        flagged = sum(1 for line in proposal.lines if not line.removed and line.status != "ok")
        row = {
            "message_id": case["message_id"], "subject": email.subject,
            "expected": sum(expected.values()), "predicted": sum(predicted.values()), "correct": correct,
            "flagged_for_review": flagged, "ok_but_wrong": ok_wrong,
            "exact_order": predicted == expected,
        }
        rows.append(row)
        for k in ("expected", "predicted", "correct", "flagged_for_review", "ok_but_wrong"):
            tot[k] += row[k]
        tot["ok_lines"] += len(ok_lines)
        tot["exact"] += int(row["exact_order"])
        tot["evaluated"] += 1

    def ratio(a, b):
        return round(a / b, 3) if b else None

    summary = {
        "extractor": extractor.name,
        "emails": len(truth["emails"]),
        "evaluated": tot["evaluated"],
        "line_recall": ratio(tot["correct"], tot["expected"]),
        "line_precision": ratio(tot["correct"], tot["predicted"]),
        "exact_order_rate": ratio(tot["exact"], len(truth["emails"])),
        "lines_flagged_for_review": tot["flagged_for_review"],
        "ok_lines_that_were_wrong": tot["ok_but_wrong"],
        "ok_line_error_rate": ratio(tot["ok_but_wrong"], tot["ok_lines"]),
    }
    return {"summary": summary, "emails": rows}


def format_report(report: dict) -> str:
    out = []
    for r in report["emails"]:
        if "error" in r:
            out.append(f"  ! {r.get('subject', r['message_id'])[:40]:<40} {r['error']}")
            continue
        mark = "exact" if r["exact_order"] else f"{r['correct']}/{r['expected']} lines"
        out.append(f"  {r['subject'][:40]:<40} {mark:<12} flagged {r['flagged_for_review']}, ok-but-wrong {r['ok_but_wrong']}")
    s = report["summary"]

    def pct(v):
        return "n/a" if v is None else f"{v * 100:.0f}%"

    out += [
        "",
        f"Extractor:             {s['extractor']}",
        f"Line recall:           {pct(s['line_recall'])}  (expected lines found correctly)",
        f"Line precision:        {pct(s['line_precision'])}  (drafted lines that were correct)",
        f"Exact orders:          {pct(s['exact_order_rate'])}",
        f"Flagged for review:    {s['lines_flagged_for_review']} lines",
        f"Marked ok but wrong:   {s['ok_lines_that_were_wrong']}  <- the number that must stay near zero",
    ]
    return "\n".join(out)
