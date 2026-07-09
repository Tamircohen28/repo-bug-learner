.PHONY: help install update uninstall test lint clean schema precision \
	agent\:check agent-polish-gate repo-standards-gate assert-contract \
	check-agent-drift check-feature-equivalence check-platform-targets \
	platform-targets-sync platform-targets-assert

TAMIRS_CONTRACT ?= $(HOME)/Projects/tamirs-superpowers/skills/repo/_contract

help:
	@echo "install update uninstall test lint agent:check agent-polish-gate repo-standards-gate"

install:
	uv sync --extra dev

update:
	uv sync --extra dev --upgrade

uninstall:
	rm -rf .venv
	$(MAKE) clean

agent\:check: check-agent-drift check-feature-equivalence check-platform-targets

check-agent-drift:
	bash scripts/check-agent-drift.sh .

check-feature-equivalence:
	bash scripts/check-feature-equivalence.sh .

check-platform-targets:
	bash scripts/check-platform-targets.sh .

platform-targets-sync:
	bash scripts/check-platform-targets.sh . --sync

platform-targets-assert:
	bash scripts/check-platform-targets.sh . --assert-current

agent-polish-gate: platform-targets-sync platform-targets-assert agent\:check

assert-contract:
	@bash "$(TAMIRS_CONTRACT)/scripts/assert-contract.sh" . app-gold

repo-standards-gate: agent-polish-gate assert-contract

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
