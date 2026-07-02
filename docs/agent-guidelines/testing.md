# Testing guidelines

Referenced from [AGENTS.md](../../AGENTS.md).

## Running tests

```bash
make test        # precision check + regression scan + pytest
make precision   # precision_check.py (semgrep) only
```

`make test` first runs the precision gate, then a regression path scan
(`scripts/test_scan_repo_paths.py`), then `pytest -q` if pytest is installed.

## Expectations

- A change to synthesis or validation logic must keep the precision gate passing.
  Run `make precision` and cite the reported precision/recall before claiming done.
- Add a regression test when fixing a bug in the scanner or rule harness.
- Do not weaken precision/recall thresholds to make a change pass — investigate the
  root cause instead.
