# Local deployment

Some clients will not let order data leave their building: no cloud AI, no API keys. Tickwell
supports this with the `local` extractor, which sends the prompt to an Ollama server on the same
machine or local network instead of to Claude.

## What runs where

| Step | Cloud setup | Local setup |
|---|---|---|
| Reading the mailbox | Client's own Microsoft 365 / IMAP | Same |
| Parsing emails, PDFs, Excel | Tickwell machine | Same |
| **Reading the order (extraction)** | **Claude API** | **Ollama on the Tickwell machine** |
| Catalog matching, rules, review, database | Tickwell machine | Same |
| Sending to the ERP | Tickwell machine to client's ERP | Same |

Only one row changes. That is the whole privacy story, and it fits on one slide.

## Setup on a single machine (simplest, good for a pilot)

1. Install Ollama from ollama.com (Windows, macOS, Linux).
2. Pull a model: `ollama pull <model>`. Check that it answers: `ollama run <model> "hello"`.
3. In `.env`:

   ```
   TICKWELL_EXTRACTOR=local
   TICKWELL_OLLAMA_MODEL=<model>
   TICKWELL_OLLAMA_NUM_CTX=16384
   TICKWELL_LOCAL_ONLY=true
   ```

4. Measure before promising anything:

   ```bash
   tickwell init --reset && tickwell ingest
   tickwell evaluate --truth data/sample/ground_truth.json --extractor local
   ```

5. Run as usual: `tickwell worker` in one terminal, `tickwell serve` in another.

## Setup with Docker

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
docker compose exec ollama ollama pull <model>
```

Set `TICKWELL_OLLAMA_MODEL` in `.env` and restart. With an NVIDIA GPU, uncomment the `deploy`
block in `docker-compose.local.yml`.

## Choosing a model

Open-weight model families change quickly, so do not pick one from a blog post: pick it with
`tickwell evaluate`. Pull two or three current instruction-tuned models (for example from the
Qwen, Llama, Mistral and Gemma families) in sizes the hardware can run, evaluate each on the
client's historical emails, and choose on these numbers, in this order:

1. **Lines marked "ok" that were wrong.** Must stay near zero. If a model is confidently wrong,
   it is out, however good its recall.
2. **Line recall.** How much of the order it gets without help.
3. **Time per email.** Anything under a minute is fine, because the worker drafts in the
   background.

Expect local models to be weaker than Claude on vague emails ("same as last week but double
the salvias"), and close to it on tidy lists and PDF tables. The matcher and rules don't trust
any model, so weaker extraction shows up as more yellow lines to check, not as wrong orders.
Report this honestly to the client: "fully local, slightly more checking" is a fair trade for
many of them.

## Context window

The prompt contains the catalog and the customer's recent orders. Ollama's default context
window is small and **cuts long prompts without an error**, which looks like a model that
ignores half the catalog. Tickwell sets `num_ctx` to 16384 by default and logs a warning when a
prompt gets close. A larger window needs more memory. For catalogs with thousands of articles,
send only the top candidates per email (see the roadmap in the README).

## Hardware

Rules of thumb, not guarantees. Always check speed on the client's own emails.

- **Pilot:** a recent laptop or desktop. CPU-only works for small models; slow, but fine to
  prove the idea.
- **Production in the client's office:** a small machine with a GPU that has enough memory for
  the chosen model, or a Mac with plenty of unified memory. It runs Tickwell, Ollama and the
  database together.
- Price the hardware into the setup fee and the upkeep into the monthly fee. "A box in your
  building that I manage, and your data never leaves it" is a product in itself.

## Checklist before telling a client "nothing leaves your network"

- `TICKWELL_LOCAL_ONLY=true` is set, and `tickwell draft` starts without errors.
- `TICKWELL_OLLAMA_BASE_URL` points at localhost, a private IP, or the Docker service name.
- The mailbox connection goes to the client's own Microsoft 365 tenant or mail server.
- The ERP connector writes CSV files locally or talks to the client's own ERP.
- No `ANTHROPIC_API_KEY` in `.env` on that machine.
