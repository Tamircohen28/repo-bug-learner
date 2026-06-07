"""Offline orchestrator v3-tuned: targeted Scala tuning for the all-time corpus.

Changes vs run_offline_v2.py:
  * Pre-clustering noise filter: drop entries whose bug_summary matches common
    noise commit verbs (merge / chore / refactor / rename / cleanup / formatting
    / imports) which wreck cluster centroids on the pre-2020 corpus.
  * TF-IDF tuning: ngram_range=(1,3), max_features=8192, min_df=3, sublinear_tf=True.
  * Optional character n-gram vectorizer hstacked alongside word n-grams.
  * HDBSCAN tuning: min_cluster_size=5, min_samples=2, cluster_selection_method="leaf"
    (more, smaller clusters - better at fragmenting a mega-cluster).
  * Optional per-era split (--per-era) as a last resort.

Usage:
  python scripts/run_offline_v3.py \\
    --corpus out/corpus/corpus_alltime.jsonl \\
    --output out/clusters_v3_tuned
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

import hdbscan
import numpy as np
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize


MAX_ENTRIES_PER_COMMIT = 2
MIN_DISTINCT_COMMITS = 3
MIN_CLUSTER_SIZE = 5
MIN_SAMPLES = 2
CLUSTER_SELECTION_METHOD = "leaf"
RANDOM_SEED = 13

NOISE_SUMMARY_RE = re.compile(
    r"(merge pull request|^merge\b|\bchore\b|\brefactor(ing)?\b|\brename(d|s|ing)?\b"
    r"|\bcleanup\b|\bformatting\b|\bimports?\b|\bbump\b|\bversion bump\b"
    r"|\breorganize\b|\bmove (file|files|folder)\b)",
    re.IGNORECASE,
)


def load_corpus(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open()]


def filter_noise_summaries(entries: list[dict]) -> tuple[list[dict], int]:
    kept = []
    dropped = 0
    for e in entries:
        s = e.get("bug_summary") or ""
        if NOISE_SUMMARY_RE.search(s):
            dropped += 1
            continue
        kept.append(e)
    return kept, dropped


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


def embed(entries: list[dict], use_char_ngrams: bool = True) -> np.ndarray:
    def to_text(e: dict) -> str:
        return "\n".join([
            e["bug_summary"],
            e["language"],
            e["buggy_code"],
            e["fix_diff"][:2000],
            " ".join(e.get("jira_labels") or []),
        ])
    texts = [to_text(e) for e in entries]
    word_vec = TfidfVectorizer(
        max_features=8192,
        ngram_range=(1, 3),
        token_pattern=r"[A-Za-z_][A-Za-z0-9_]+|[+\-=!<>]+",
        min_df=3,
        sublinear_tf=True,
    )
    word_m = word_vec.fit_transform(texts)
    if use_char_ngrams:
        char_vec = TfidfVectorizer(
            max_features=4096,
            analyzer="char_wb",
            ngram_range=(3, 5),
            min_df=3,
            sublinear_tf=True,
        )
        char_m = char_vec.fit_transform(texts)
        matrix = hstack([word_m, char_m]).toarray()
    else:
        matrix = word_m.toarray()
    return normalize(matrix).astype(np.float32)


def cluster(embeddings: np.ndarray,
            min_cluster_size: int = MIN_CLUSTER_SIZE,
            min_samples: int = MIN_SAMPLES,
            method: str = CLUSTER_SELECTION_METHOD) -> np.ndarray:
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="euclidean",
        cluster_selection_method=method,
    )
    return clusterer.fit_predict(embeddings)


def _build_prompt(bundle: dict, fence_lang: str) -> str:
    cid = bundle["cluster_id"]
    parts = [
        f"# Cluster {cid} - {bundle['size']} bug fixes ({bundle['n_commits']} distinct commits)\n",
        "## Top files\n" + "\n".join(f"- `{f}` ({n})" for f, n in bundle["top_files"]),
        "\n## Top directories\n" + "\n".join(f"- `{d}` ({n})" for d, n in bundle["top_dirs"]),
        "\n## Bug summaries\n" + "\n".join(f"- {s}" for s in bundle["bug_summaries"]),
        "\n## Bug examples (buggy code that the fix removed)\n",
    ]
    for i, e in enumerate(bundle["entries"][:8], 1):
        parts.append(f"\n### Example {i}: {e['bug_key']} - `{e['file_path']}`")
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
        "if it needs type info) - or an ESLint rule for TypeScript - that flags the "
        "anti-pattern."
    )
    return "\n".join(parts)


def write_cluster_bundles(
    entries: list[dict],
    labels: np.ndarray,
    out_dir: Path,
    fence_lang: str,
    cluster_id_offset: int = 0,
) -> dict:
    by_cluster: dict[int, list[dict]] = defaultdict(list)
    for entry, label in zip(entries, labels, strict=True):
        by_cluster[int(label)].append(entry)

    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "n_entries": len(entries),
        "min_cluster_size": MIN_CLUSTER_SIZE,
        "min_samples": MIN_SAMPLES,
        "cluster_selection_method": CLUSTER_SELECTION_METHOD,
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

        adj_cid = cid + cluster_id_offset
        cluster_info = {
            "cluster_id": adj_cid,
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

        cdir = out_dir / f"cluster_{adj_cid:03d}"
        cdir.mkdir(exist_ok=True)

        bundle = {
            "cluster_id": adj_cid,
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
    return summary


def era_of(entry: dict) -> str:
    # bug_key is typically of form <sha>:<date> or contains a commit date.
    # Fall back to fields if present.
    for fld in ("commit_date", "date", "authored_date"):
        v = entry.get(fld)
        if isinstance(v, str) and len(v) >= 4 and v[:4].isdigit():
            year = int(v[:4])
            break
    else:
        # try jira_labels / pr_url heuristics fallback - default bucket
        year = 2022
    if year <= 2018:
        return "2014-2018"
    if year <= 2022:
        return "2019-2022"
    return "2023-2026"


def run_for_language(
    entries: list[dict],
    language: str,
    out_dir: Path,
    fence_lang: str,
    per_era: bool = False,
) -> dict:
    print(f"\n=== {language} ===")
    print(f"  raw entries: {len(entries)}")
    filtered, dropped = filter_noise_summaries(entries)
    print(f"  after noise-summary filter: {len(filtered)} (dropped {dropped})")
    capped = downsample_per_commit(filtered, MAX_ENTRIES_PER_COMMIT, RANDOM_SEED)
    print(f"  after per-commit cap (<= {MAX_ENTRIES_PER_COMMIT}): {len(capped)}")
    if len(capped) < MIN_CLUSTER_SIZE:
        print("  too few entries to cluster")
        return {
            "language": language,
            "n_entries": len(capped),
            "clusters": [],
            "dropped_clusters": [],
            "noise_count": 0,
        }

    if not per_era:
        embeddings = embed(capped)
        print(f"  embedded: shape {embeddings.shape}")
        labels = cluster(embeddings)
        n_raw = len(set(labels)) - (1 if -1 in labels else 0)
        noise = int((labels == -1).sum())
        print(f"  raw clusters: {n_raw}, noise: {noise} ({noise/len(capped):.1%})")
        summary = write_cluster_bundles(capped, labels, out_dir, fence_lang)
        summary["language"] = language
        summary["raw_cluster_count"] = n_raw
        summary["raw_entries"] = len(entries)
        summary["filtered_entries"] = len(filtered)
        summary["capped_entries"] = len(capped)
    else:
        # per-era split
        by_era: dict[str, list[dict]] = defaultdict(list)
        for e in capped:
            by_era[era_of(e)].append(e)
        combined = {
            "language": language,
            "raw_entries": len(entries),
            "filtered_entries": len(filtered),
            "capped_entries": len(capped),
            "clusters": [],
            "dropped_clusters": [],
            "noise_count": 0,
            "per_era": {},
        }
        offset = 0
        for era, eras_entries in sorted(by_era.items()):
            if len(eras_entries) < MIN_CLUSTER_SIZE:
                continue
            print(f"  -- era {era}: {len(eras_entries)} entries --")
            emb = embed(eras_entries)
            labels = cluster(emb)
            n_raw = len(set(labels)) - (1 if -1 in labels else 0)
            noise = int((labels == -1).sum())
            print(f"     raw clusters: {n_raw}, noise: {noise}")
            era_out = out_dir
            era_summary = write_cluster_bundles(
                eras_entries, labels, era_out, fence_lang,
                cluster_id_offset=offset,
            )
            combined["clusters"].extend(era_summary["clusters"])
            combined["dropped_clusters"].extend(era_summary["dropped_clusters"])
            combined["noise_count"] += era_summary["noise_count"]
            combined["per_era"][era] = {
                "entries": len(eras_entries),
                "raw_cluster_count": n_raw,
                "surviving_cluster_count": len(era_summary["clusters"]),
            }
            offset += 1000
        summary = combined

    print(f"  surviving clusters (>= {MIN_DISTINCT_COMMITS} commits): "
          f"{len(summary['clusters'])}")
    sizes = [c["size"] for c in summary["clusters"]]
    if sizes:
        sizes_sorted = sorted(sizes)
        med = sizes_sorted[len(sizes_sorted) // 2]
        print(f"  size dist: min={min(sizes)} median={med} max={max(sizes)}")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path,
                    default=Path("out/corpus/corpus_alltime.jsonl"))
    ap.add_argument("--output", type=Path,
                    default=Path("out/clusters_v3_tuned"))
    ap.add_argument("--per-era", action="store_true",
                    help="Split corpus by era before clustering (last-resort).")
    ap.add_argument("--languages", nargs="+", default=["scala"],
                    help="Which languages to cluster (default: scala only).")
    args = ap.parse_args()

    entries = load_corpus(args.corpus)
    print(f"Loaded {len(entries)} corpus entries")
    by_lang: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_lang[e["language"]].append(e)
    print("By language:", {k: len(v) for k, v in by_lang.items()})

    overall = {"per_language": {}}
    fence_map = {"scala": "scala", "typescript": "ts"}
    for lang_key in args.languages:
        lang_entries = by_lang.get(lang_key, [])
        sub_out = args.output / lang_key
        summary = run_for_language(
            lang_entries, lang_key, sub_out,
            fence_map.get(lang_key, lang_key),
            per_era=args.per_era,
        )
        overall["per_language"][lang_key] = {
            "raw_entries": summary.get("raw_entries", 0),
            "filtered_entries": summary.get("filtered_entries", 0),
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
