.PHONY: install test lint clean schema precision

install:
	uv sync --extra dev

test: precision
	python -m venv .venv 2>/dev/null || true
	.venv/bin/pip install -q semgrep==1.163.0 2>/dev/null || true
	.venv/bin/python scripts/test_scan_repo_paths.py
	@if [ -f .venv/bin/pytest ]; then .venv/bin/pytest -q; fi

precision:
	python -m venv .venv 2>/dev/null || true
	.venv/bin/pip install -q semgrep==1.163.0 2>/dev/null || true
	.venv/bin/python scripts/precision_check.py

lint:
	.venv/bin/ruff check src scripts

clean:
	rm -rf .venv
	find . -type d -name __pycache__ -not -path './out/*' -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf rule-validator/target

schema:
	.venv/bin/python -m src.orchestrator schema
