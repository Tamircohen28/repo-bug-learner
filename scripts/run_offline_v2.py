"""Offline orchestrator v2: clustering at scale (~10k corpus).

Changes vs run_offline.py:
  * Per-commit downsampling (MAX_ENTRIES_PER_COMMIT=2) so a single big PR can't
    dominate the embedding space.
  * Split by language (scala / typescript) and cluster each separately — a Scala
    anti-pattern and a TS anti-pattern are not the same rule.
  * Tuned HDBSCAN: min_cluster_size=8, min_samples=3.
  * Post-filter: drop clusters whose entries come from < MIN_DISTINCT_COMMITS=3
    distinct commits (these are "one big PR scattered across files").
  * Same per-cluster prompt.md format as v1.

Usage:
  python scripts/run_offline_v2.py --corpus out/corpus/corpus_full.jsonl \
                                   --output out/clusters_v2
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

import hdbscan
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize


MAX_ENTRIES_PER_COMMIT = 2
MIN_DISTINCT_COMMITS = 3
MIN_CLUSTER_SIZE = 8
MIN_SAMPLES = 3
RANDOM_SEED = 13


def load_corpus(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open()]


def downsample_per_commit(entries: list[dict], cap: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    by_commit: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_commit[e["bug_key"]].append(e)
    kept: list[dict] = []
    for _commit, group in by_commit.items():
        if len(group) <= cap:
            kept.extend(group)
        else:
            kept.extend(rng.sample(group, cap))
    return kept


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
        token_pattern=r"[A-Za-z_][A-Za-z0-9_]+|[+\-=!<>]+",
        min_df=2,
        sublinear_tf=True,
    )
    matrix = vec.fit_transform(texts).toarray()
    return normalize(matrix).astype(np.float32)


def cluster(embeddings: np.ndarray) -> np.ndarray:
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=MIN_CLUSTER_SIZE,
        min_samples=MIN_SAMPLES,
        metric="euclidean",
        cluster_selection_method="eom",
    )
    return clusterer.fit_predict(embeddings)


def _build_prompt(bundle: dict, fence_lang: str) -> str:
    cid = bundle["cluster_id"]
    parts = [
        f"# Cluster {cid} — {bundle['size']} bug fixes ({bundle['n_commits']} distinct commits)\n",
        "## Top files\n" + "\n".join(f"- `{f}` ({n})" for f, n in bundle["top_files"]),
        "\n## Top directories\n" + "\n".join(f"- `{d}` ({n})" for d, n in bundle["top_dirs"]),
        "\n## Bug summaries\n" + "\n".join(f"- {s}" for s in bundle["bug_summaries"]),
        "\n## Bug examples (buggy code that the fix removed)\n",
    ]
    for i, e in enumerate(bundle["entries"][:8], 1):
        parts.append(f"\n### Example {i}: {e['bug_key']} — `{e['file_path']}`")
        parts.append(f"**Summary:** {e['bug_summary']}")
        parts.append(f"**PR:** {e.get('pr_url', '')}")
        parts.append(f"**Buggy code (removed by the fix):**\n```{fence_lang}")
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
        "if it needs type info) — or an ESLint rule for TypeScript — that flags the "
        "anti-pattern. Include:\n"
        f"  1. Rule source (one fenced ```{fence_lang} block).\n"
        "  2. A 1-line `rationale` explaining what bug class it catches.\n"
        "  3. A minimal input and expected output for testing.\n"
        "If no rule generalizes (e.g. these are all one-off bugs), say so explicitly."
    )
    return "\n".join(parts)


def write_cluster_bundles(
    entries: list[dict],
    labels: np.ndarray,
    out_dir: Path,
    fence_lang: str,
) -> dict:
    by_cluster: dict[int, list[dict]] = defaultdict(list)
    for entry, label in zip(entries, labels, strict=True):
        by_cluster[int(label)].append(entry)

    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "n_entries": len(entries),
        "min_cluster_size": MIN_CLUSTER_SIZE,
        "min_samples": MIN_SAMPLES,
        "min_distinct_commits": MIN_DISTINCT_COMMITS,
        "clusters": [],
        "dropped_clusters": [],
    }

    for cid, group in sorted(by_cluster.items()):
        if cid == -1:
            continue
        commits = {e["bug_key"] for e in group}
        files = Counter(e["file_path"].split("/")[-1] for e in group)
        dirs = Counter("/".join(e["file_path"].split("/")[:3]) for e in group)
        summaries = [e["bug_summary"] for e in group]

        cluster_info = {
            "cluster_id": cid,
            "size": len(group),
            "n_commits": len(commits),
            "top_files": files.most_common(5),
        }

        if len(commits) < MIN_DISTINCT_COMMITS:
            cluster_info["reason"] = (
                f"only {len(commits)} distinct commits (< {MIN_DISTINCT_COMMITS})"
            )
            summary["dropped_clusters"].append(cluster_info)
            continue

        cdir = out_dir / f"cluster_{cid:03d}"
        cdir.mkdir(exist_ok=True)

        bundle = {
            "cluster_id": cid,
            "size": len(group),
            "n_commits": len(commits),
            "top_files": files.most_common(5),
            "top_dirs": dirs.most_common(5),
            "bug_summaries": summaries,
            "entries": group,
        }
        (cdir / "bundle.json").write_text(json.dumps(bundle, indent=2))
        (cdir / "prompt.md").write_text(_build_prompt(bundle, fence_lang))

        summary["clusters"].append(cluster_info)

    summary["noise_count"] = int((labels == -1).sum())
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def run_for_language(
    entries: list[dict],
    language: str,
    out_dir: Path,
    fence_lang: str,
) -> dict:
    print(f"\n=== {language} ===")
    print(f"  raw entries: {len(entries)}")
    capped = downsample_per_commit(entries, MAX_ENTRIES_PER_COMMIT, RANDOM_SEED)
    print(f"  after per-commit cap (<= {MAX_ENTRIES_PER_COMMIT}): {len(capped)}")
    if len(capped) < MIN_CLUSTER_SIZE:
        print("  too few entries to cluster")
        return {"language": language, "n_entries": len(capped), "clusters": [], "dropped_clusters": [], "noise_count": 0}

    embeddings = embed(capped)
    print(f"  embedded: shape {embeddings.shape}")
    labels = cluster(embeddings)
    n_raw_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    noise = int((labels == -1).sum())
    print(f"  raw clusters: {n_raw_clusters}, noise: {noise} ({noise/len(capped):.1%})")

    summary = write_cluster_bundles(capped, labels, out_dir, fence_lang)
    summary["language"] = language
    summary["raw_cluster_count"] = n_raw_clusters
    summary["raw_entries"] = len(entries)
    summary["capped_entries"] = len(capped)
    print(f"  surviving clusters (>= {MIN_DISTINCT_COMMITS} commits): {len(summary['clusters'])}")
    print(f"  dropped clusters: {len(summary['dropped_clusters'])}")
    for c in summary["clusters"]:
        print(f"    cluster_{c['cluster_id']:03d}: size={c['size']:3d} commits={c['n_commits']:3d} top={c['top_files'][:2]}")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, default=Path("out/corpus/corpus_full.jsonl"))
    ap.add_argument("--output", type=Path, default=Path("out/clusters_v2"))
    args = ap.parse_args()

    entries = load_corpus(args.corpus)
    print(f"Loaded {len(entries)} corpus entries")
    by_lang: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_lang[e["language"]].append(e)
    print("By language:", {k: len(v) for k, v in by_lang.items()})

    overall = {"per_language": {}}
    targets = [
        ("scala", "scala", "scala"),
        ("typescript", "typescript", "ts"),
    ]
    for lang_key, subdir, fence in targets:
        lang_entries = by_lang.get(lang_key, [])
        sub_out = args.output / subdir
        summary = run_for_language(lang_entries, lang_key, sub_out, fence)
        overall["per_language"][lang_key] = {
            "raw_entries": summary.get("raw_entries", 0),
            "capped_entries": summary.get("capped_entries", 0),
            "raw_cluster_count": summary.get("raw_cluster_count", 0),
            "surviving_cluster_count": len(summary.get("clusters", [])),
            "dropped_cluster_count": len(summary.get("dropped_clusters", [])),
            "noise_count": summary.get("noise_count", 0),
        }

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(json.dumps(overall, indent=2))
    print("\n=== overall ===")
    print(json.dumps(overall, indent=2))


if __name__ == "__main__":
    main()
