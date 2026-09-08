"""Offline orchestrator: stages 3-4 without ANTHROPIC_API_KEY or Postgres.

Embeds with sklearn TF-IDF (good enough for syntactic clustering of Scala code).
Clusters in-memory with HDBSCAN. Writes per-cluster prompt bundles to
out/clusters/cluster_<id>/ — those bundles are what a synthesizer (LLM session or
human) reads to produce a Scalafix rule.

Usage:
  python scripts/run_offline.py --corpus out/corpus/corpus.jsonl --output out/clusters
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import hdbscan
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize


def load_corpus(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open()]


def embed(entries: list[dict]) -> np.ndarray:
    def to_text(e: dict) -> str:
        return "\n".join([
            e["bug_summary"],
            e["language"],
            e["buggy_code"],
            e["fix_diff"][:2000],
            " ".join(e.get("jira_labels") or []),
        ])
    texts = [to_text(e) for e in entries]
    vec = TfidfVectorizer(
        max_features=4096,
        ngram_range=(1, 2),
        token_pattern=r"[A-Za-z_][A-Za-z0-9_]+|[+\-=!<>]+",  # noqa: S106 - sklearn tokenizer regex, not a credential
        min_df=2,
        sublinear_tf=True,
    )
    matrix = vec.fit_transform(texts).toarray()
    return normalize(matrix).astype(np.float32)


def cluster(embeddings: np.ndarray, min_cluster_size: int = 3) -> np.ndarray:
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        metric="euclidean",
        cluster_selection_method="eom",
    )
    return clusterer.fit_predict(embeddings)


def write_cluster_bundles(entries: list[dict], labels: np.ndarray, out_dir: Path) -> dict:
    by_cluster: dict[int, list[dict]] = defaultdict(list)
    for entry, label in zip(entries, labels, strict=True):
        by_cluster[int(label)].append(entry)

    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {"n_entries": len(entries), "clusters": []}

    for cid, group in sorted(by_cluster.items()):
        if cid == -1:
            continue
        cdir = out_dir / f"cluster_{cid:03d}"
        cdir.mkdir(exist_ok=True)

        # Aggregate signals for the synthesizer prompt
        files = Counter(e["file_path"].split("/")[-1] for e in group)
        dirs = Counter("/".join(e["file_path"].split("/")[:3]) for e in group)
        summaries = [e["bug_summary"] for e in group]

        bundle = {
            "cluster_id": cid,
            "size": len(group),
            "top_files": files.most_common(5),
            "top_dirs": dirs.most_common(5),
            "bug_summaries": summaries,
            "entries": group,
        }
        (cdir / "bundle.json").write_text(json.dumps(bundle, indent=2))

        # Human-readable prompt for the synthesizer (Claude session reads this)
        prompt = _build_prompt(bundle)
        (cdir / "prompt.md").write_text(prompt)

        summary["clusters"].append({
            "cluster_id": cid,
            "size": len(group),
            "top_files": files.most_common(3),
        })

    noise = int((labels == -1).sum())
    summary["noise_count"] = noise
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def _build_prompt(bundle: dict) -> str:
    cid = bundle["cluster_id"]
    parts = [
        f"# Cluster {cid} — {bundle['size']} bug fixes\n",
        "## Top files\n" + "\n".join(f"- `{f}` ({n})" for f, n in bundle["top_files"]),
        "\n## Top directories\n" + "\n".join(f"- `{d}` ({n})" for d, n in bundle["top_dirs"]),
        "\n## Bug summaries\n" + "\n".join(f"- {s}" for s in bundle["bug_summaries"]),
        "\n## Bug examples (buggy code that the fix removed)\n",
    ]
    for i, e in enumerate(bundle["entries"][:8], 1):
        parts.append(f"\n### Example {i}: {e['bug_key']} — `{e['file_path']}`")
        parts.append(f"**Summary:** {e['bug_summary']}")
        parts.append(f"**PR:** {e.get('pr_url', '')}")
        parts.append("**Buggy code (removed by the fix):**\n```scala")
        parts.append(e["buggy_code"][:1500])
        parts.append("```")
        parts.append("**Fix diff:**\n```diff")
        parts.append(e["fix_diff"][:2000])
        parts.append("```")
    parts.append(
        "\n---\n"
        "## Task for the synthesizer\n"
        "Look across these examples. Is there a recurring anti-pattern that a static "
        "rule could catch? If yes, produce a Scalafix `SyntacticRule` (or `SemanticRule` "
        "if it needs type info) that flags the anti-pattern. Include:\n"
        "  1. Scala source for the rule (one fenced ```scala block).\n"
        "  2. A 1-line `rationale` explaining what bug class it catches.\n"
        "  3. A minimal `input.scala` and expected `output.scala` for testing.\n"
        "If no rule generalizes (e.g. these are all one-off bugs), say so explicitly."
    )
    return "\n".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, default=Path("out/corpus/corpus.jsonl"))
    ap.add_argument("--output", type=Path, default=Path("out/clusters"))
    ap.add_argument("--min-cluster-size", type=int, default=3)
    args = ap.parse_args()

    entries = load_corpus(args.corpus)
    print(f"Loaded {len(entries)} corpus entries")

    embeddings = embed(entries)
    print(f"Embedded with TF-IDF: shape {embeddings.shape}")

    labels = cluster(embeddings, min_cluster_size=args.min_cluster_size)
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    print(f"Clustered into {n_clusters} groups, {(labels == -1).sum()} noise")

    summary = write_cluster_bundles(entries, labels, args.output)
    print(f"\nWrote {len(summary['clusters'])} cluster bundles to {args.output}")
    for c in summary["clusters"]:
        print(f"  cluster_{c['cluster_id']:03d}: size={c['size']:3d} top={c['top_files']}")


if __name__ == "__main__":
    main()
