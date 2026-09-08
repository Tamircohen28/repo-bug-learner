#!/usr/bin/env python3
"""Find recurring fix-commit themes that appear in BOTH two configured repos.

Cross-language pattern recurrence implies deep system properties — strong rule targets.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "out/iterations/cross_repo_patterns.md"

STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "into", "have",
    "has", "was", "were", "are", "but", "not", "you", "your", "all", "any",
    "can", "will", "should", "would", "could", "its", "his", "her", "him",
    "their", "they", "them", "our", "out", "off", "over", "under", "than",
    "then", "when", "where", "what", "which", "who", "why", "how", "been",
    "being", "does", "did", "doing", "done", "had", "having", "get", "got",
    "getting", "let", "lets", "via", "per", "due", "etc", "also", "such",
    "some", "more", "less", "most", "least", "much", "many", "few", "one",
    "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "first", "second", "third", "last", "next", "prev", "previous",
    "fix", "fixes", "fixed", "fixing", "add", "added", "adding", "adds",
    "update", "updated", "updating", "updates", "remove", "removed",
    "removing", "removes", "use", "used", "using", "uses", "make", "made",
    "making", "makes", "new", "old", "set", "sets", "setting", "change",
    "changed", "changes", "changing", "support", "supports", "supported",
    "refactor", "refactoring", "feat", "feature", "chore", "test", "tests",
    "testing", "tested", "wip", "draft", "minor", "major", "small", "big",
    "automerge", "merge", "merged", "pr", "prs", "commit", "commits",
    "bump", "bumps", "bumped", "rename", "renamed", "move", "moved",
    "moving", "cleanup", "clean", "improve", "improved", "improvement",
    "improvements", "improving", "allow", "allows", "allowed", "enable",
    "enabled", "enables", "disable", "disabled", "disables", "revert",
    "reverted", "reverts", "release", "releases", "released",
    "version", "versions", "deps", "dep", "dependency", "dependencies",
    "now", "yet", "still", "just", "only", "even", "ever", "never",
    "always", "sometimes", "often", "rarely", "really", "very", "quite",
    "rather", "almost", "nearly", "about", "around", "above", "below",
    "after", "before", "during", "while", "until", "since",
    "between", "among", "through", "across", "along", "behind", "beyond",
    "inside", "outside", "near", "far", "here", "there", "everywhere",
    "anywhere", "nowhere", "somewhere", "wix", "fixup", "do", "to",
    "in", "on", "at", "by", "of", "as", "is", "be", "or", "if", "an",
    "we", "us", "it", "so", "no",
    # generic action words found in many summaries
    "implement", "implementation", "implemented", "create", "created",
    "creating", "creates", "build", "built", "building", "builds",
    "log", "logs", "logging", "logged", "print", "console",
    "handle", "handles", "handled", "handling", "handler", "handlers",
    "show", "shows", "shown", "showing", "hide", "hides", "hidden",
    "open", "opened", "opens", "close", "closed", "closes", "closing",
    "send", "sends", "sent", "sending", "receive", "received",
    "todo", "draftpr", "drafts", "click", "clicks", "clicked", "tap", "tapped", "press", "pressed",
    "screen", "screens", "page", "pages", "view", "views", "viewed",
    "back", "front", "main", "secondary", "primary",
}

NON_DOMAIN = {
    "fix", "add", "update", "remove", "use", "make", "new", "support",
    "refactor", "feat", "chore", "test", "improve", "allow", "enable",
    "disable", "revert", "release", "version", "deps", "bump", "rename",
    "move", "cleanup", "clean", "implement", "create", "build", "log",
    "handle", "show", "hide", "open", "close", "send", "receive",
}

TOKEN_RE = re.compile(r"[A-Za-z]+")


def tokenize(text: str) -> list[str]:
    if not text:
        return []
    tokens = TOKEN_RE.findall(text.lower())
    out = []
    for t in tokens:
        if len(t) < 3:
            continue
        if t in STOPWORDS:
            continue
        if t.isdigit():
            continue
        out.append(t)
    return out


def load_corpus(path: Path) -> list[dict]:
    entries = []
    with path.open() as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def build_token_stats(entries: list[dict]) -> tuple[Counter, dict[str, set[int]]]:
    """Return (token_counts, token -> set of summary indices)."""
    token_counts: Counter = Counter()
    token_to_summaries: dict[str, set[int]] = defaultdict(set)
    # Deduplicate by bug_summary (per-PR) so multi-file fixes don't inflate counts.
    seen_summaries: dict[str, int] = {}
    summary_index = 0
    summary_list: list[str] = []
    for e in entries:
        summary = e.get("bug_summary") or ""
        if summary in seen_summaries:
            idx = seen_summaries[summary]
        else:
            idx = summary_index
            seen_summaries[summary] = idx
            summary_list.append(summary)
            summary_index += 1
        tokens = set(tokenize(summary))
        for t in tokens:
            token_to_summaries[t].add(idx)
    for t, idxs in token_to_summaries.items():
        token_counts[t] = len(idxs)
    return token_counts, token_to_summaries, summary_list


def top_examples(entries: list[dict], token: str, k: int = 5) -> list[tuple[str, str]]:
    """Return up to k (pr_url_or_sha, summary) tuples for fix commits mentioning token."""
    seen_summaries: set[str] = set()
    results = []
    for e in entries:
        summary = e.get("bug_summary") or ""
        if summary in seen_summaries:
            continue
        if token in set(tokenize(summary)):
            seen_summaries.add(summary)
            pr_url = e.get("pr_url") or ""
            if pr_url:
                m = re.search(r"/pull/(\d+)", pr_url)
                pr_id = f"PR-{m.group(1)}" if m else pr_url
            else:
                pr_id = (e.get("commit_sha") or "")[:10]
            results.append((pr_id, summary))
            if len(results) >= k:
                break
    return results


RULE_SHAPES = {
    "timezone": "Static check that any DateTime/ZonedDateTime construction or arithmetic explicitly passes a ZoneId/timezone argument; flag implicit system-default timezone (`new Date()`, `LocalDateTime.now()`, `dayjs()` without `.tz()`).",
    "null": "Flag dereferences of values whose type is nullable/Option without an explicit guard; in Scala flag `.get` on `Option`, in TS flag non-null assertions (`!`) or property access on `T | null | undefined`.",
    "error": "Require that catch blocks either rethrow, log with structured context, or return a typed Result; flag empty catch blocks and `catch (e) {}` swallowing.",
    "type": "Flag `any`/`as any` casts in TS and `asInstanceOf`/`isInstanceOf` chains in Scala; enforce discriminated-union exhaustiveness checks.",
    "async": "Flag promise-returning calls that are not awaited and not explicitly `.catch()`-handled (TS) and `Future` values discarded without `recover`/`onComplete` (Scala).",
    "session": "Require session/auth context to be passed explicitly through call chains; flag any service call that pulls session from a thread-local/global instead of an argument.",
    "translation": "Flag hardcoded user-facing strings in components/JSX (TS) and Scala message-builders; require keys go through the i18n lookup helper.",
    "permission": "Require every external-facing endpoint declares a permission/role guard; flag controllers/resolvers missing `@RequiresPermission`/`assertPermission(...)`.",
    "currency": "Flag arithmetic on raw `Double`/`number` amounts; require Money/BigDecimal types and explicit currency code propagation across function boundaries.",
    "validation": "Require request DTOs run through a declared validator before use; flag direct field access on a request object that wasn't validated.",
    "duration": "Require explicit time-unit types (`Duration`, `FiniteDuration`) instead of raw `Int`/`Long`; flag numeric literals passed to time-related APIs.",
    "calendar": "Require calendar boundary calls (recurrence expansion, slot generation) to receive an explicit timezone + DST-safe date arithmetic; flag naive day arithmetic.",
    "booking": "Require booking mutations to check current status against an allowed-transition map; flag direct status field assignments.",
    "payment": "Require payment operations to be idempotent (idempotency-key argument or check); flag payment APIs called without one.",
    "notification": "Require notification dispatch to include locale + channel + dedup key; flag fire-and-forget notification calls missing any.",
    "cache": "Require cache writes to set explicit TTL and invalidation keys to be derived from a shared helper; flag manual key string concatenation.",
    "retry": "Require retries on remote calls to use a bounded backoff policy from a shared helper; flag ad-hoc `while`/`for` retry loops.",
    "filter": "Require list endpoints to apply tenant/business filter before any other criteria; flag queries missing the tenant predicate.",
    "redux": "Flag selectors that recompute on every store change without memoization; require `createSelector`/equivalent for derived state.",
    "navigation": "Flag direct navigation calls inside reducers/services; require navigation through a typed router helper that records breadcrumbs.",
}


def suggest_rule_shape(token: str) -> str:
    if token in RULE_SHAPES:
        return RULE_SHAPES[token]
    return (
        f"Investigate fix titles mentioning `{token}` to derive a specific anti-pattern; "
        "candidate shape: a lint that flags direct use of the underlying primitive without "
        "going through the project's helper module."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find recurring fix themes shared across two repo corpora.",
    )
    parser.add_argument(
        "--repos",
        nargs=2,
        metavar="NAME:CORPUS",
        help=(
            "Two repo corpora as name:path pairs, e.g. "
            "backend:out/corpus/backend.jsonl frontend:out/corpus/frontend.jsonl"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Markdown report path (default: {DEFAULT_OUT})",
    )
    args = parser.parse_args()

    if args.repos:
        (name_a, path_a), (name_b, path_b) = args.repos
        corpus_a = ROOT / path_a if not Path(path_a).is_absolute() else Path(path_a)
        corpus_b = ROOT / path_b if not Path(path_b).is_absolute() else Path(path_b)
        repo_a_name, repo_b_name = name_a, name_b
    else:
        corpus_a = ROOT / "out/corpus/corpus_alltime.jsonl"
        corpus_b = ROOT / "out/corpus/corpus_mobile.jsonl"
        repo_a_name, repo_b_name = "repo-a", "repo-b"

    out_path = args.output if args.output.is_absolute() else ROOT / args.output

    scheduler = load_corpus(corpus_a)
    mobile = load_corpus(corpus_b)
    print(f"Loaded {repo_a_name}={len(scheduler)} {repo_b_name}={len(mobile)}")

    sched_counts, _, sched_summaries = build_token_stats(scheduler)
    mob_counts, _, mob_summaries = build_token_stats(mobile)

    sched_total = len(sched_summaries)
    mob_total = len(mob_summaries)
    print(f"Unique summaries: {repo_a_name}={sched_total} {repo_b_name}={mob_total}")

    # Drop tokens that appear in >30% of summaries (per-repo too generic).
    sched_generic = {t for t, c in sched_counts.items() if sched_total and c / sched_total > 0.30}
    mob_generic = {t for t, c in mob_counts.items() if mob_total and c / mob_total > 0.30}
    generic = sched_generic | mob_generic | NON_DOMAIN

    # Cross-repo tokens: >=20 in one repo and >=5 in the other.
    candidates = []
    all_tokens = set(sched_counts) | set(mob_counts)
    for t in all_tokens:
        if t in generic:
            continue
        s = sched_counts.get(t, 0)
        m = mob_counts.get(t, 0)
        if (s >= 20 and m >= 5) or (m >= 20 and s >= 5):
            candidates.append((t, s, m))

    # Rank by combined count, then by min (cross-repo balance bonus).
    candidates.sort(key=lambda x: (x[1] + x[2], min(x[1], x[2])), reverse=True)

    lines = ["# Cross-repo patterns",
             "",
             (f"_{repo_a_name} unique summaries: {sched_total}; "
             f"{repo_b_name} unique summaries: {mob_total}._"),
             f"_Candidate cross-repo tokens: {len(candidates)}_",
             ""]

    top10 = candidates[:10]
    lines.append("## Top 10 cross-repo tokens (with suggested rule shape)")
    lines.append("")
    for rank, (token, s, m) in enumerate(top10, 1):
        lines.append(f"### {rank}. `{token}` — {repo_a_name}: {s} PRs, {repo_b_name}: {m} PRs")
        lines.append("")
        lines.append(f"**Suggested rule shape:** {suggest_rule_shape(token)}")
        lines.append("")
        lines.append(f"{repo_a_name} examples:")
        for pr_id, summary in top_examples(scheduler, token, 5):
            lines.append(f"  - {pr_id} {summary}")
        lines.append("")
        lines.append(f"{repo_b_name} examples:")
        for pr_id, summary in top_examples(mobile, token, 5):
            lines.append(f"  - {pr_id} {summary}")
        lines.append("")

    if len(candidates) > 10:
        lines.append("## Remaining cross-repo tokens")
        lines.append("")
        for token, s, m in candidates[10:]:
            lines.append(f"### `{token}` — {repo_a_name}: {s} PRs, {repo_b_name}: {m} PRs")
            lines.append("")
            lines.append(f"{repo_a_name} examples:")
            for pr_id, summary in top_examples(scheduler, token, 5):
                lines.append(f"  - {pr_id} {summary}")
            lines.append("")
            lines.append(f"{repo_b_name} examples:")
            for pr_id, summary in top_examples(mobile, token, 5):
                lines.append(f"  - {pr_id} {summary}")
            lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines))
    print(f"Wrote {out_path}")
    print("Top 10 tokens:")
    for t, s, m in top10:
        print(f"  {t}: {repo_a_name}={s} {repo_b_name}={m}")


if __name__ == "__main__":
    main()
