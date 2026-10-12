.PHONY: install demo serve test lint eval eval-offline

install:
	pip install -e ".[dev]"

demo:
	orderdesk init --reset
	orderdesk ingest
	orderdesk draft
	orderdesk serve

serve:
	orderdesk serve --reload

test:
	pytest -q

lint:
	ruff check src tests scripts

eval:
	orderdesk evaluate --truth data/sample/ground_truth.json

eval-offline:
	orderdesk evaluate --truth data/sample/ground_truth.json --extractor heuristic
