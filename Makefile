.PHONY: install demo serve test lint eval eval-local eval-offline

install:
	pip install -e ".[dev]"

demo:
	tickwell init --reset
	tickwell ingest
	tickwell draft
	tickwell serve

serve:
	tickwell serve --reload

test:
	pytest -q

lint:
	ruff check src tests scripts

eval:
	tickwell evaluate --truth data/sample/ground_truth.json

eval-local:
	tickwell evaluate --truth data/sample/ground_truth.json --extractor local

eval-offline:
	tickwell evaluate --truth data/sample/ground_truth.json --extractor heuristic
