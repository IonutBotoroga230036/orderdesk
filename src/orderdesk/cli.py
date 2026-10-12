"""Command line: orderdesk init | ingest | draft | serve | worker | evaluate."""

import argparse
import json
import logging
import time
from datetime import datetime
from pathlib import Path

from .config import get_settings
from .db import init_db, session_scope

log = logging.getLogger("orderdesk")


def cmd_init(args):
    from .seed import load_master_data

    init_db(drop=args.reset)
    with session_scope() as s:
        counts = load_master_data(s, Path(args.data))
    print("Database ready. Loaded:", ", ".join(f"{v} {k}" for k, v in counts.items()))


def cmd_ingest(args):
    from .ingest import get_mail_source, ingest

    init_db()
    with session_scope() as s:
        new = ingest(s, get_mail_source(args.source))
        print(f"Fetched {len(new)} new email(s).")


def cmd_draft(args):
    from .extraction import get_extractor
    from .pipeline import draft_pending

    init_db()
    extractor = get_extractor(args.extractor)
    with session_scope() as s:
        drafts = draft_pending(s, extractor)
        for d in drafts:
            review_n = sum(1 for line in d.lines if line.needs_review)
            print(f"  Draft {d.id}: {d.email.subject[:50]!r}, {len(d.lines)} lines, {review_n} to check")
        print(f"Drafted {len(drafts)} email(s) with the {extractor.name} extractor.")


def cmd_serve(args):
    import uvicorn

    uvicorn.run("orderdesk.api.app:app", host=args.host, port=args.port, reload=args.reload)


def cmd_worker(args):
    from .extraction import get_extractor
    from .ingest import get_mail_source, ingest
    from .pipeline import draft_pending

    init_db()
    extractor = get_extractor(args.extractor)
    every = args.every or get_settings().poll_seconds
    log.info("Worker started: polling every %ss with the %s extractor", every, extractor.name)
    while True:
        try:
            with session_scope() as s:
                new = ingest(s, get_mail_source())
                drafts = draft_pending(s, extractor) if new else []
                if new:
                    log.info("Fetched %d, drafted %d", len(new), len(drafts))
        except Exception:
            log.exception("Worker cycle failed")
        if args.once:
            break
        time.sleep(every)


def cmd_evaluate(args):
    from .evaluate import evaluate, format_report
    from .extraction import get_extractor

    init_db()
    extractor = get_extractor(args.extractor)
    with session_scope() as s:
        report = evaluate(s, Path(args.truth), extractor)
        s.rollback()  # evaluation never changes data
    print(format_report(report))
    out = Path("reports")
    out.mkdir(exist_ok=True)
    path = out / f"eval-{extractor.name}-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nFull report: {path}")


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="orderdesk", description="Order emails in, reviewed draft orders out.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="Create the database and load master data from CSV files")
    sp.add_argument("--data", default="data/sample", help="Folder with products.csv, customers.csv, aliases.csv, past_orders.csv")
    sp.add_argument("--reset", action="store_true", help="Drop all tables first (deletes emails and drafts)")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("ingest", help="Fetch new emails from the configured mail source")
    sp.add_argument("--source", choices=["folder", "imap", "graph"])
    sp.set_defaults(func=cmd_ingest)

    sp = sub.add_parser("draft", help="Draft orders for all new emails")
    sp.add_argument("--extractor", choices=["claude", "heuristic"])
    sp.set_defaults(func=cmd_draft)

    sp = sub.add_parser("serve", help="Run the review screen and API")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8000)
    sp.add_argument("--reload", action="store_true")
    sp.set_defaults(func=cmd_serve)

    sp = sub.add_parser("worker", help="Poll the mailbox and draft new orders continuously")
    sp.add_argument("--extractor", choices=["claude", "heuristic"])
    sp.add_argument("--every", type=int, help="Seconds between polls")
    sp.add_argument("--once", action="store_true", help="Run one cycle and exit")
    sp.set_defaults(func=cmd_worker)

    sp = sub.add_parser("evaluate", help="Shadow test: compare drafts with known correct orders")
    sp.add_argument("--truth", required=True, help="Ground truth JSON")
    sp.add_argument("--extractor", choices=["claude", "heuristic"])
    sp.set_defaults(func=cmd_evaluate)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
