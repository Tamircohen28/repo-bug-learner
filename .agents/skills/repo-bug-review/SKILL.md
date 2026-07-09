---
name: repo-bug-review
description: Review code (file, directory, GitHub PR, or pasted snippet) against the repo-bug-learner rule set — finds known anti-patterns from past bug fixes and reports issues with severity + citations. Triggers when the user asks to review/check/scan/audit code for known bug patterns, timezone issues, error-handling gaps, or similar.
---

# repo-bug-review

Review code against rules synthesized from historical fix commits.

## When to trigger

The user wants to lint/review/audit code against known anti-patterns from the rule corpus.

## Step 1 — Run the review orchestrator

```bash
cd /path/to/repo-bug-learner
.venv/bin/python scripts/review.py \
    --file /absolute/path/to/file \
    --dir /absolute/path/to/dir \
    --pr 12345 --repo your-org/backend \
    --snippet-text "..." --language python
```

`--repo` is required when using `--pr`.

## Step 2 — Review each bundle

Read `out/review/<timestamp>/bundles/*.md` and classify TP / FP / SUSPICIOUS with suggested fixes.

## Step 3 — Report

Summarize findings by severity with origin-bug citations when available.
