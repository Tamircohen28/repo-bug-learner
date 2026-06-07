# Architecture overview

## Pipeline stages

| Stage | Module | Output |
|-------|--------|--------|
| 1 Mine | `src/stage1_mine/` | `out/raw/bugs.jsonl` |
| 2 Corpus | `src/stage2_corpus/` | `out/corpus/corpus.jsonl` |
| 3 Cluster | `src/stage3_cluster/` | Postgres embeddings + cluster IDs |
| 4 Synthesize | `src/stage4_synthesize/` | `out/candidates/*.{scala,yaml}` |
| 5 Validate | `src/stage5_validate/` | `out/validated/report.json` |
| 6 Ship | `src/stage6_ship/` | GitHub PRs to rules repos |

## Language routing

The orchestrator picks the dominant language in each cluster:

- **scala** → `ScalafixSynthesizer`
- **typescript, javascript, python, go** → `OpengrepSynthesizer` with language-specific prompt guidance

## Scanner

`scripts/scan_repo.py` runs regex emulators for Scala rules and Semgrep/Opengrep for YAML rules. Used by `scripts/review.py` and CI precision checks.

## Rules repository

Validated rules land in separate Scalafix and Opengrep repos (configured in `[rules_repos]`). Target services copy workflows from `service-integration/.github/workflows/`.
