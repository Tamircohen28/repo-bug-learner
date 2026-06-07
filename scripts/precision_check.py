#!/usr/bin/env python3
"""Run precision corpora checks for Scalafix emulators and Opengrep YAML rules."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN = ROOT / "scripts" / "scan_repo.py"
TESTS = ROOT / "rule-validator" / "rules" / "tests"
OPENGREP = ROOT / "rule-validator" / "rules" / "opengrep"

SCALA_RULES = [
    "UnclampedOpenSpots",
    "MissingDollarInInterpolation",
    "BrokenInterpolationFieldAccess",
]
YAML_RULES = [
    "ts-array-sort-numbers-without-comparator",
    "form-payload-direct-access-without-validation",
    "ts-staff-query-missing-appdefid",
    "calendar-scheduled-time-without-explicit-timezone",
    "py-mutable-default-arg",
    "py-bare-except",
    "go-ignored-error",
    "go-defer-in-loop",
]
EXT = {
    "py-mutable-default-arg": ".py",
    "py-bare-except": ".py",
    "go-ignored-error": ".go",
    "go-defer-in-loop": ".go",
}


def main() -> None:
    os.environ.setdefault("SEMGREP_HOME", str(ROOT / ".semgrep"))
    failures: list[tuple[str, float]] = []

    for rule in SCALA_RULES:
        out = Path("/tmp/_precision_scala.json")
        subprocess.run(
            [
                sys.executable,
                str(SCAN),
                "--repo-path",
                str(TESTS),
                "--rules-dir",
                str(ROOT / "rule-validator" / "rules"),
                "--output",
                str(out),
                "--include-tests",
                "--paths",
                f"**/{rule}.scala",
            ],
            check=True,
            capture_output=True,
        )
        data = json.loads(out.read_text())
        hits = [f for f in data["findings"] if f["rule"] == rule]
        tp = sum(1 for f in hits if "positive" in f["file"])
        fp = sum(1 for f in hits if "negative" in f["file"])
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        print(f"  {rule:50s} TP={tp:2d} FP={fp:2d} precision={prec:.1%}")
        if prec < 0.75:
            failures.append((rule, prec))

    semgrep = ROOT / ".venv" / "bin" / "semgrep"
    if not semgrep.exists():
        semgrep = Path("semgrep")

    for rule in YAML_RULES:
        yaml = OPENGREP / f"{rule}.yaml"
        ext = EXT.get(rule, ".ts")
        pos = TESTS / "positive" / f"{rule}{ext}"
        neg = TESTS / "negative" / f"{rule}{ext}"
        proc = subprocess.run(
            [str(semgrep), "--config", str(yaml), "--quiet", "--json", str(pos), str(neg)],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            data = json.loads(proc.stdout)
        except Exception:
            print(f"  {rule}: semgrep failed:\n{proc.stderr}")
            failures.append((rule, 0.0))
            continue
        tp = sum(1 for r in data.get("results", []) if "positive" in r["path"])
        fp = sum(1 for r in data.get("results", []) if "negative" in r["path"])
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        print(f"  {rule:50s} TP={tp:2d} FP={fp:2d} precision={prec:.1%}")
        if prec < 0.75:
            failures.append((rule, prec))

    if failures:
        print("\nFAIL: rule(s) below 75% precision:")
        for rule, prec in failures:
            print(f"  - {rule}: {prec:.1%}")
        sys.exit(1)
    print("\nAll rules ≥75% precision on their test corpora.")


if __name__ == "__main__":
    main()
