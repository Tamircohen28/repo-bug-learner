# Development workflow

```bash
uv sync --extra dev
make lint
make test
```

Iterate on synthesis prompts in `src/stage4_synthesize/` without re-mining using `--skip-mining`.

Rule changes: edit under `rule-validator/rules/` and run precision corpora via `make test`.
