# Architecture

## Flow

1. **Ingest** (`ingest/`). A mail source yields raw RFC 822 messages. `store_email` parses
   them, extracts attachment text and skips anything already seen (by Message-ID).
2. **Propose** (`pipeline.propose`). Pure function of the database and the email; nothing is
   written. Used by both drafting and evaluation, so the shadow test measures exactly what
   production does.
   - Identify the customer from the sender domain.
   - Build the context: catalog, and for a known sender only their aliases, notes and last
     three orders.
   - Extract lines with the configured extractor.
   - Match each line with `CatalogMatcher`, then apply `rules.apply_rules`.
3. **Save** (`pipeline.save_draft`). Writes the draft and its lines; lines marked `ok` start
   resolved, everything else waits for a person.
4. **Review** (`review.py`). Confirm, correct product or quantity, add lines, set the
   customer. Every action writes an `AuditEvent`.
5. **Approve.** Blocked until a customer is set and every line is resolved. Sends an
   `OrderPayload` to the ERP connector, records review time, adjusts local stock and learns
   aliases from corrections.

## Status per line

| Status | Meaning | Reviewer action |
|---|---|---|
| `ok` | Alias hit, or model and catalog agree | None |
| `check` | An interpretation, a low-similarity match, a stock or quantity warning | Confirm or correct |
| `unknown` | No product chosen | Pick a product |

The final status is the strictest of what the model said, what the matcher found and what
the rules flagged.

## Data model

Master data (copied from the ERP): `products`, `customers`, `customer_aliases`,
`past_order_lines`. Tickwell data: `emails`, `attachments`, `drafts`, `draft_lines`,
`audit_events`.

`draft_lines.match_method` records how a product was found (`alias`, `llm`, `fuzzy`, `none`,
`manual`). Together with the audit log this gives per-client accuracy numbers over time.

## Why these choices

- **SQLite first.** One small deployment per client is simpler to run and to explain to a
  client's IT person. SQLAlchemy keeps the move to Postgres a configuration change.
- **One schema, three extractors.** Claude (forced tool call), the local Ollama extractor
  (JSON-schema constrained output) and the heuristic all return the same `Extraction`. The
  matcher, rules, review screen and evaluation do not know or care which one ran, so a client
  can move between cloud and local by changing one setting.
- **Forced tool call for extraction.** The model must answer through the `record_order` schema,
  so the output is always structured. Pydantic validates it again before use.
- **Plain HTML/JS review screen.** No build step, easy to brand per client.
- **CSV before API.** Every ERP imports CSV. It is the fastest safe go-live while the API
  integration is tested.
