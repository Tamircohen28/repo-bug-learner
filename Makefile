.PHONY: help install update uninstall test lint lint-fix clean schema precision \
	agent\:check agent-polish-gate repo-standards-gate assert-contract \
	check-agent-drift check-feature-equivalence check-platform-targets \
	check-action-pinning \
	skill-bridge skill-bridge-check \
	platform-targets-sync platform-targets-assert

TAMIRS_CONTRACT ?= $(HOME)/Projects/tamirs-superpowers/skills/repo/_contract

# Single source of truth for the linter version: the exact pin in pyproject.toml's
# dev extra. `make lint` and CI both run this exact binary, so a new ruff release
# cannot turn CI red on a repo that has not changed.
RUFF_VERSION := $(shell sed -n 's/.*"ruff==\([0-9][0-9.]*\)".*/\1/p' pyproject.toml)

# The test venv must satisfy pyproject's requires-python (>=3.11). Ambient `python`
# is whatever PATH/pyenv happens to select -- 3.10.4 on at least one dev machine --
# so `python -m venv` silently built a venv below the floor while CI stayed green,
# because setup-python pins 3.12 there. Pick the first interpreter that actually
# clears the floor. Override on the command line: `make test PYTHON=/path/to/python`.
PYTHON := $(shell for p in python3.13 python3.12 python3.11 python3 python; do \
	command -v $$p >/dev/null 2>&1 \
	  && $$p -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null \
	  && { echo $$p; break; }; \
	done)

SEMGREP_VERSION := 1.163.0

help:
	@echo "install update uninstall test lint lint-fix agent:check agent-polish-gate repo-standards-gate"

install:
	uv sync --extra dev

update:
	uv sync --extra dev --upgrade

uninstall:
	rm -rf .venv
	$(MAKE) clean

agent\:check: check-agent-drift check-feature-equivalence check-platform-targets \
	check-action-pinning skill-bridge-check

check-agent-drift:
	bash scripts/check-agent-drift.sh .

check-feature-equivalence:
	bash scripts/check-feature-equivalence.sh .

check-platform-targets:
	bash scripts/check-platform-targets.sh .

# A movable tag (`@v7`) is the action owner's write access to our CI, and to every
# service repo that copies service-integration/. --self-test is not optional: it
# builds a violating workflow and its corrected twin and asserts the detector
# fires on one and stays quiet on the other, so a check that has quietly stopped
# checking fails loudly instead of passing.
check-action-pinning:
	bash scripts/check-action-pinning.sh . --self-test

skill-bridge:
	bash scripts/sync-skill-bridge.sh .

skill-bridge-check:
	bash scripts/sync-skill-bridge.sh . --check

platform-targets-sync:
	bash scripts/check-platform-targets.sh . --sync

platform-targets-assert:
	bash scripts/check-platform-targets.sh . --assert-current

agent-polish-gate: platform-targets-sync platform-targets-assert agent\:check

assert-contract:
	@bash "$(TAMIRS_CONTRACT)/scripts/assert-contract.sh" . app-gold

repo-standards-gate: agent-polish-gate assert-contract

# `.venv` alone is the wrong prerequisite: `make install` runs `uv sync`, which
# creates that same directory WITHOUT semgrep (it is not in pyproject) and on an
# interpreter of uv's choosing. A bare directory target is "up to date" in both
# cases, so the documented `make install && make test` would reach the precision
# check with no .venv/bin/semgrep, and an old 3.10 venv would slip past the floor.
# The stamp records what was actually verified and names the semgrep pin, so
# bumping SEMGREP_VERSION invalidates it on its own.
VENV_STAMP := .venv/.deps-ok-$(SEMGREP_VERSION)

$(VENV_STAMP):
	@if [ -x .venv/bin/python ]; then \
		.venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || { \
			echo ".venv runs $$(.venv/bin/python -V 2>&1), below the >=3.11 floor in pyproject."; \
			echo "Rebuild it on a newer interpreter: make uninstall && make install"; \
			exit 1; \
		}; \
	else \
		[ -n "$(PYTHON)" ] || { \
			echo "No Python >=3.11 on PATH (pyproject requires-python = >=3.11)."; \
			echo "Install one, or point at it: make $(MAKECMDGOALS) PYTHON=/path/to/python3.11"; \
			exit 1; \
		}; \
		$(PYTHON) -m venv .venv; \
	fi
	@# `uv sync` builds .venv WITHOUT pip, so `.venv/bin/pip` is not a thing that
	@# reliably exists. `python -m venv` does ship pip, which is why CI never hit
	@# this. Try uv first, fall back to the venv's own pip, and bootstrap pip only
	@# as a last resort.
	@if command -v uv >/dev/null 2>&1; then \
		uv pip install -q --python .venv/bin/python semgrep==$(SEMGREP_VERSION); \
	elif .venv/bin/python -m pip --version >/dev/null 2>&1; then \
		.venv/bin/python -m pip install -q semgrep==$(SEMGREP_VERSION); \
	else \
		.venv/bin/python -m ensurepip --upgrade >/dev/null && \
		.venv/bin/python -m pip install -q semgrep==$(SEMGREP_VERSION); \
	fi
	@rm -f .venv/.deps-ok-*
	@touch $@

test: precision $(VENV_STAMP)
	.venv/bin/python scripts/test_scan_repo_paths.py
	@if [ -f .venv/bin/pytest ]; then .venv/bin/pytest -q; fi

precision: $(VENV_STAMP)
	.venv/bin/python scripts/precision_check.py

lint:
	uvx ruff@$(RUFF_VERSION) check src scripts

lint-fix:
	uvx ruff@$(RUFF_VERSION) check --fix src scripts

clean:
	rm -rf .venv
	find . -type d -name __pycache__ -not -path './out/*' -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf rule-validator/target

schema: $(VENV_STAMP)
	.venv/bin/python -m src.orchestrator schema
