# Development workflow

```bash
uv sync --extra dev
make lint
make test
```

Iterate on synthesis prompts in `src/stage4_synthesize/` without re-mining using `--skip-mining`.

Rule changes: edit under `rule-validator/rules/` and run precision corpora via `make test`.

---

<p align="center"><a href="https://github.com/Tamircohen28">Have a Question?</a>&nbsp;·&nbsp;<a href="https://github.com/Tamircohen28/repo-bug-learner/issues/new/choose">Open an Issue</a></p>
