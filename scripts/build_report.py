#!/usr/bin/env python3
"""Build a self-contained HTML dashboard summarizing the repo-bug-learner pipeline state."""
from __future__ import annotations

import argparse
import collections
import html
import json
import os
import pathlib
import subprocess
import sys
import datetime as dt
import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEDULER_REPO = pathlib.Path("/Users/tamirc/IdeaProjects/scheduler")
DEFAULT_OUTPUT = PROJECT_ROOT / "out" / "report" / "index.html"


# ---------- data loading ----------

def load_corpus(path: pathlib.Path) -> list[dict]:
    entries = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def pick_clusters_dir(out_dir: pathlib.Path) -> tuple[pathlib.Path, str]:
    v2 = out_dir / "clusters_v2"
    if v2.exists():
        return v2, "v2"
    return out_dir / "clusters", "v1"


def load_clusters(clusters_dir: pathlib.Path) -> list[dict]:
    clusters = []
    if not clusters_dir.exists():
        return clusters
    # v2 may have Scala/ TypeScript subdirs
    subdirs = [d for d in clusters_dir.iterdir() if d.is_dir() and d.name in ("Scala", "TypeScript", "scala", "typescript")]
    if subdirs:
        for sub in sorted(subdirs):
            for cdir in sorted(sub.iterdir()):
                if cdir.is_dir() and cdir.name.startswith("cluster_"):
                    b = cdir / "bundle.json"
                    if b.exists():
                        try:
                            data = json.loads(b.read_text())
                            data["_dir"] = cdir
                            data["_language_group"] = sub.name
                            clusters.append(data)
                        except json.JSONDecodeError:
                            pass
    else:
        for cdir in sorted(clusters_dir.iterdir()):
            if cdir.is_dir() and cdir.name.startswith("cluster_"):
                b = cdir / "bundle.json"
                if b.exists():
                    try:
                        data = json.loads(b.read_text())
                        data["_dir"] = cdir
                        data["_language_group"] = data.get("language", "scala")
                        clusters.append(data)
                    except json.JSONDecodeError:
                        pass
    return clusters


def load_candidates(cand_dir: pathlib.Path) -> list[dict]:
    rules = []
    if not cand_dir.exists():
        return rules
    for cdir in sorted(cand_dir.iterdir()):
        if not cdir.is_dir():
            continue
        skip = cdir / "skip.md"
        rule_scala = cdir / "Rule.scala"
        rationale_md = cdir / "rationale.md"
        status = "skipped" if skip.exists() else ("rule" if rule_scala.exists() else "unknown")
        rationale_text = rationale_md.read_text() if rationale_md.exists() else (skip.read_text() if skip.exists() else "")
        name = "?"
        if rule_scala.exists():
            for line in rule_scala.read_text().splitlines():
                if line.strip().startswith("class ") and " extends " in line:
                    name = line.strip().split("class ", 1)[1].split(" ", 1)[0]
                    break
        rules.append({
            "cluster_id": cdir.name,
            "status": status,
            "rule_path": str(rule_scala.relative_to(PROJECT_ROOT)) if rule_scala.exists() else None,
            "rationale_path": str(rationale_md.relative_to(PROJECT_ROOT)) if rationale_md.exists() else None,
            "skip_path": str(skip.relative_to(PROJECT_ROOT)) if skip.exists() else None,
            "rule_name": name,
            "rationale_snippet": (rationale_text[:500] + "…") if len(rationale_text) > 500 else rationale_text,
        })
    return rules


def load_opengrep_rules(rules_root: pathlib.Path) -> list[dict]:
    """Find all opengrep YAML rule files; extract id/severity/languages/message without yaml dep."""
    entries: list[dict] = []
    if not rules_root.exists():
        return entries
    for yf in sorted(rules_root.rglob("*.yaml")):
        try:
            text = yf.read_text()
        except Exception:
            continue
        # extract first `- id:` line (simple parser, opengrep rules are flat)
        rid = None
        severity = None
        langs: list[str] = []
        msg_lines: list[str] = []
        in_msg = False
        msg_indent = None
        in_languages = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("- id:") and rid is None:
                rid = stripped.split("- id:", 1)[1].strip()
            elif stripped.startswith("id:") and rid is None:
                rid = stripped.split("id:", 1)[1].strip()
            elif stripped.startswith("severity:") and severity is None:
                severity = stripped.split("severity:", 1)[1].strip()
            elif stripped.startswith("languages:"):
                in_languages = True
                continue
            elif in_languages:
                if stripped.startswith("- "):
                    langs.append(stripped[2:].strip())
                    continue
                else:
                    in_languages = False
            if in_msg:
                cur_indent = len(line) - len(line.lstrip())
                if line.strip() == "" or (msg_indent is not None and cur_indent >= msg_indent):
                    msg_lines.append(line.strip())
                else:
                    in_msg = False
            if stripped.startswith("message:") and not in_msg:
                rest = stripped.split("message:", 1)[1].strip()
                if rest and not rest.startswith(">") and not rest.startswith("|"):
                    msg_lines.append(rest.strip("'\""))
                else:
                    in_msg = True
                    msg_indent = (len(line) - len(line.lstrip())) + 2
        message = " ".join(m for m in msg_lines if m).strip()
        entries.append({
            "id": rid or yf.stem,
            "severity": severity or "?",
            "languages": langs,
            "message": message,
            "path": str(yf.relative_to(PROJECT_ROOT)),
            "format": "opengrep",
        })
    return entries


def load_scalafix_rules(src_root: pathlib.Path) -> list[dict]:
    """Find scalafix rule class files under src/main/scala/fix/*.scala."""
    entries: list[dict] = []
    if not src_root.exists():
        return entries
    for sf in sorted(src_root.rglob("*.scala")):
        if "/fix/" not in str(sf):
            continue
        try:
            text = sf.read_text()
        except Exception:
            continue
        # class Name extends SemanticRule(...) or SyntacticRule(...)
        m = re.search(r"class\s+(\w+)\s+extends\s+(\w+)", text)
        if not m:
            continue
        name = m.group(1)
        entries.append({
            "id": name,
            "severity": "medium",
            "languages": ["scala"],
            "message": "",
            "path": str(sf.relative_to(PROJECT_ROOT)),
            "format": "scalafix",
        })
    return entries


def load_iter_scans(iter_dir: pathlib.Path, pattern: str = "scan_iter*_*.json") -> list[dict]:
    """Load scan_iter*.json files. Group by latest 'iter' tag using filename mtime."""
    if not iter_dir.exists():
        return []
    files = sorted(iter_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    # find the highest iter index among filenames
    iter_re = re.compile(r"scan_iter(\d+)([a-z]?)_?([a-z_]*)\.json")
    by_iter: dict[int, list[pathlib.Path]] = {}
    for f in files:
        m = iter_re.match(f.name)
        if not m:
            continue
        n = int(m.group(1))
        by_iter.setdefault(n, []).append(f)
    if not by_iter:
        return []
    latest = max(by_iter)
    scans = []
    for f in by_iter[latest]:
        try:
            scans.append(json.loads(f.read_text()))
        except json.JSONDecodeError:
            continue
    return scans


def aggregate_findings(scans: list[dict]) -> tuple[list[dict], dict]:
    """Merge findings; return all_findings plus repo -> rule -> count map."""
    all_findings = []
    coverage: dict[str, dict[str, int]] = collections.defaultdict(lambda: collections.defaultdict(int))
    for s in scans:
        repo = pathlib.Path(s.get("repo", "?")).name or s.get("repo", "?")
        for fnd in s.get("findings", []) or []:
            fnd_copy = dict(fnd)
            fnd_copy["_repo"] = repo
            all_findings.append(fnd_copy)
            rule = fnd.get("rule") or fnd.get("check_id") or "?"
            coverage[rule][repo] += 1
    return all_findings, coverage


def load_recent_iterations(iter_dir: pathlib.Path, n: int = 3) -> list[pathlib.Path]:
    if not iter_dir.exists():
        return []
    files = sorted(iter_dir.glob("iteration_*.md"), key=lambda p: p.name, reverse=True)
    return files[:n]


def get_top_authors(repo: pathlib.Path, shas: list[str], top_n: int = 10) -> list[tuple[str, int]]:
    if not repo.exists() or not shas:
        return []
    # batch: use --stdin-batch? simpler: pipe shas to git log with --no-walk
    # actually use git show --no-patch --format=%an for each sha; but 4887 invocations slow.
    # Use single git log with multiple SHAs via xargs equivalent.
    counter: collections.Counter = collections.Counter()
    # chunk shas; pass to `git show --no-patch --format=%an SHA1 SHA2 ...`
    CHUNK = 200
    for i in range(0, len(shas), CHUNK):
        chunk = shas[i:i + CHUNK]
        try:
            r = subprocess.run(
                ["git", "-C", str(repo), "show", "--no-patch", "--format=%an"] + chunk,
                capture_output=True, text=True, timeout=120
            )
            for line in r.stdout.splitlines():
                line = line.strip()
                if line:
                    counter[line] += 1
        except Exception as e:
            print(f"[warn] git show chunk failed: {e}", file=sys.stderr)
    return counter.most_common(top_n)


# ---------- charts (no plotly install needed; emit JSON for CDN plotly) ----------

def build_time_series(entries: list[dict]) -> dict:
    bucket: collections.Counter = collections.Counter()
    for e in entries:
        ts = e.get("committed_at")
        if not ts:
            continue
        try:
            d = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            key = f"{d.year:04d}-{d.month:02d}"
            bucket[key] += 1
        except Exception:
            continue
    keys = sorted(bucket)
    return {"x": keys, "y": [bucket[k] for k in keys]}


def build_scatter(entries: list[dict], cluster_assignments: dict[str, int]) -> dict:
    """Compute TF-IDF + TruncatedSVD(2) on fix_diff+bug_summary; color by cluster id."""
    # Deduplicate entries by bug_key + file_path for speed
    seen = set()
    samples = []
    for e in entries:
        k = (e.get("bug_key"), e.get("file_path"))
        if k in seen:
            continue
        seen.add(k)
        samples.append(e)
    # cap to 3000 for HTML size
    if len(samples) > 3000:
        step = len(samples) // 3000 + 1
        samples = samples[::step]
    docs = [(e.get("bug_summary", "") + "\n" + (e.get("fix_diff") or "")[:2000]) for e in samples]
    if not docs:
        return {"x": [], "y": [], "text": [], "color": []}
    vec = TfidfVectorizer(max_features=2000, stop_words="english", ngram_range=(1, 2))
    X = vec.fit_transform(docs)
    svd = TruncatedSVD(n_components=2, random_state=42)
    coords = svd.fit_transform(X)
    xs = coords[:, 0].tolist()
    ys = coords[:, 1].tolist()
    texts = []
    colors = []
    for e in samples:
        s = (e.get("bug_summary") or "")[:120]
        bk = e.get("bug_key", "")
        texts.append(html.escape(f"{bk}: {s}"))
        cid = cluster_assignments.get(e.get("bug_key", ""), -1)
        colors.append(cid)
    return {"x": xs, "y": ys, "text": texts, "color": colors}


# ---------- HTML ----------

CSS = """
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 0; background: #f6f8fa; color: #1f2328; }
header { background: #24292f; color: #fff; padding: 20px 32px; }
header h1 { margin: 0; font-size: 22px; }
header .subtitle { color: #9da7b1; font-size: 13px; margin-top: 4px; }
main { max-width: 1200px; margin: 0 auto; padding: 24px; }
section { background: #fff; border: 1px solid #d0d7de; border-radius: 6px; padding: 20px; margin-bottom: 24px; }
section h2 { margin-top: 0; font-size: 18px; border-bottom: 1px solid #d0d7de; padding-bottom: 8px; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
.card { background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px; padding: 14px; }
.card .label { font-size: 12px; color: #57606a; text-transform: uppercase; letter-spacing: 0.5px; }
.card .value { font-size: 22px; font-weight: 600; margin-top: 4px; color: #0969da; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #d0d7de; }
th { background: #f6f8fa; font-weight: 600; }
.cluster-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
.cluster-card { border: 1px solid #d0d7de; border-radius: 6px; padding: 14px; background: #fff; }
.cluster-card h3 { margin: 0 0 6px 0; font-size: 14px; }
.cluster-card .meta { font-size: 12px; color: #57606a; margin-bottom: 8px; }
.cluster-card ul { padding-left: 18px; margin: 6px 0; font-size: 12px; }
.cluster-card .summaries { font-size: 12px; color: #1f2328; }
.cluster-card .summaries li { margin-bottom: 4px; word-break: break-word; }
.tag { display: inline-block; background: #ddf4ff; color: #0969da; border-radius: 10px; padding: 2px 8px; font-size: 11px; margin-right: 4px; }
.tag.rule { background: #dafbe1; color: #1a7f37; }
.tag.skip { background: #fff8c5; color: #9a6700; }
.tag.unvalidated { background: #ffebe9; color: #cf222e; }
pre.ascii { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; background: #f6f8fa; border-radius: 6px; padding: 12px; overflow-x: auto; }
footer { padding: 24px 32px; color: #57606a; font-size: 12px; text-align: center; }
a { color: #0969da; text-decoration: none; }
a:hover { text-decoration: underline; }
.lang-scala { color: #c0382b; }
.lang-typescript { color: #2980b9; }
.muted { color: #57606a; font-size: 12px; }
"""

ASCII_PIPELINE = """\
  ┌────────┐    ┌──────────┐    ┌──────────────────┐    ┌──────────┐    ┌──────────┐
  │ Jira   │───▶│ 1. Mine  │───▶│ 2. Corpus + SZZ  │───▶│ 3.Cluster│───▶│ 4.Synth. │
  │ GitHub │    │          │    │                  │    │          │    │          │
  └────────┘    └──────────┘    └──────────────────┘    └──────────┘    └─────┬────┘
                                                                              │
                                  ┌────────────────────────────────────────┐  │
                                  │  Rules Repo (static-analysis-rules)       │◀─┤
                                  └────────────────────────────────────────┘  │
                                              ▲                               │
                          ┌──────────┐        │       ┌──────────┐            │
                          │ 6. Ship  │◀───────┴───────│ 5. Valid.│◀───────────┘
                          └──────────┘                └──────────┘
"""


def render(out_path: pathlib.Path, ctx: dict) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # --- cards ---
    cards_html = "".join(
        f'<div class="card"><div class="label">{html.escape(lbl)}</div><div class="value">{html.escape(str(val))}</div></div>'
        for lbl, val in ctx["overview_cards"]
    )

    # --- time series ---
    ts = ctx["time_series"]
    ts_json = json.dumps([{"x": ts["x"], "y": ts["y"], "type": "scatter", "mode": "lines+markers", "line": {"color": "#0969da"}, "name": "fix-commits"}])
    ts_layout = json.dumps({"margin": {"t": 10, "r": 10, "b": 40, "l": 40}, "height": 280, "xaxis": {"title": "month"}, "yaxis": {"title": "fix commits"}})

    # --- authors table ---
    authors_rows = "".join(
        f"<tr><td>{i+1}</td><td>{html.escape(name)}</td><td>{count}</td></tr>"
        for i, (name, count) in enumerate(ctx["top_authors"])
    ) or '<tr><td colspan="3" class="muted">No author data available.</td></tr>'

    # --- scatter ---
    sc = ctx["scatter"]
    sc_data = json.dumps([{
        "x": sc["x"], "y": sc["y"], "text": sc["text"], "mode": "markers", "type": "scatter",
        "marker": {"color": sc["color"], "colorscale": "Viridis", "size": 6, "opacity": 0.7, "showscale": True, "colorbar": {"title": "cluster"}},
        "hovertemplate": "%{text}<extra></extra>",
    }])
    sc_layout = json.dumps({"margin": {"t": 10, "r": 10, "b": 30, "l": 30}, "height": 520, "xaxis": {"title": "dim 1"}, "yaxis": {"title": "dim 2"}})

    # --- cluster cards ---
    cluster_cards_html_parts = []
    for c in ctx["clusters"]:
        cid = c.get("cluster_id", "?")
        size = c.get("size", len(c.get("entries", [])))
        lang = c.get("_language_group", "scala")
        top_files = c.get("top_files") or []
        files_html = "".join(f"<li><code>{html.escape(str(fn))}</code> ({n})</li>" for fn, n in top_files[:5])
        summaries = (c.get("bug_summaries") or [])[:3]
        sum_html = "".join(f"<li>{html.escape(s)}</li>" for s in summaries) or '<li class="muted">no summaries</li>'
        n_distinct = len({e.get("commit_sha") or e.get("bug_key") for e in c.get("entries", [])})
        prompt_path = c["_dir"] / "prompt.md"
        prompt_link = ""
        if prompt_path.exists():
            rel = os.path.relpath(prompt_path, out_path.parent)
            prompt_link = f'<a href="{rel}">prompt.md</a>'
        rule_link = ""
        cand_dir = PROJECT_ROOT / "out" / "candidates" / f"cluster_{int(cid):03d}" if isinstance(cid, int) else None
        if cand_dir and cand_dir.exists():
            rs = cand_dir / "Rule.scala"
            if rs.exists():
                rel = os.path.relpath(rs, out_path.parent)
                rule_link = f' &middot; <a href="{rel}">Rule.scala</a>'
        cluster_cards_html_parts.append(f"""
        <div class="cluster-card">
          <h3>Cluster {cid} <span class="tag lang-{html.escape(str(lang).lower())}">{html.escape(str(lang))}</span></h3>
          <div class="meta">size={size} &middot; distinct commits={n_distinct}</div>
          <div><strong>Top files</strong><ul>{files_html or '<li class="muted">none</li>'}</ul></div>
          <div><strong>Sample bugs</strong><ul class="summaries">{sum_html}</ul></div>
          <div class="meta">{prompt_link}{rule_link}</div>
        </div>
        """)
    clusters_html = '<div class="cluster-grid">' + "".join(cluster_cards_html_parts) + "</div>" if cluster_cards_html_parts else '<p class="muted">No clusters found.</p>'

    # --- rules table ---
    rule_rows = []
    for r in ctx["rules"]:
        status = r["status"]
        status_tag = f'<span class="tag {"rule" if status=="rule" else "skip"}">{status}</span>'
        validation_tag = '<span class="tag unvalidated">unvalidated</span>'
        rationale_link = ""
        if r.get("rationale_path"):
            rel = os.path.relpath(PROJECT_ROOT / r["rationale_path"], out_path.parent)
            rationale_link = f'<a href="{rel}">rationale</a>'
        elif r.get("skip_path"):
            rel = os.path.relpath(PROJECT_ROOT / r["skip_path"], out_path.parent)
            rationale_link = f'<a href="{rel}">skip note</a>'
        rule_path_link = ""
        if r.get("rule_path"):
            rel = os.path.relpath(PROJECT_ROOT / r["rule_path"], out_path.parent)
            rule_path_link = f'<a href="{rel}">{html.escape(r["rule_name"])}</a>'
        else:
            rule_path_link = '<span class="muted">—</span>'
        snippet = html.escape((r.get("rationale_snippet") or "").replace("\n", " ").strip()[:200])
        rule_rows.append(
            f"<tr><td>{rule_path_link}</td><td>scalafix</td><td>{html.escape(r['cluster_id'])}</td>"
            f"<td>{status_tag}</td><td>{validation_tag}</td><td>{rationale_link}</td><td class='muted'>{snippet}</td></tr>"
        )
    rules_table_html = (
        "<table><thead><tr><th>Rule</th><th>Target</th><th>Origin cluster</th>"
        "<th>Status</th><th>Validation</th><th>Doc</th><th>Rationale</th></tr></thead>"
        f"<tbody>{''.join(rule_rows) or '<tr><td colspan=7 class=muted>No candidates.</td></tr>'}</tbody></table>"
    )

    # --- active rules table (opengrep + scalafix discovered on disk) ---
    active_rule_rows = []
    coverage = ctx.get("coverage", {})
    for r in ctx.get("active_rules", []):
        rid = r["id"]
        per_repo = coverage.get(rid, {})
        total = sum(per_repo.values())
        per_repo_str = ", ".join(f"{rp}: {n}" for rp, n in sorted(per_repo.items())) or '<span class="muted">0</span>'
        rel = os.path.relpath(PROJECT_ROOT / r["path"], out_path.parent)
        langs = ", ".join(r.get("languages") or []) or "?"
        active_rule_rows.append(
            f"<tr><td><a href='{rel}'>{html.escape(rid)}</a></td>"
            f"<td>{html.escape(r['format'])}</td>"
            f"<td>{html.escape(langs)}</td>"
            f"<td>{html.escape(r.get('severity') or '?')}</td>"
            f"<td>{total}</td>"
            f"<td>{per_repo_str}</td></tr>"
        )
    active_rules_html = (
        "<table><thead><tr><th>Rule id</th><th>Format</th><th>Languages</th>"
        "<th>Severity</th><th>Total findings</th><th>Per-repo</th></tr></thead>"
        f"<tbody>{''.join(active_rule_rows) or '<tr><td colspan=6 class=muted>No active rules.</td></tr>'}</tbody></table>"
    )

    # --- cross-repo coverage matrix ---
    repos = sorted({rp for per in coverage.values() for rp in per})
    if repos and coverage:
        header = "<tr><th>Rule</th>" + "".join(f"<th>{html.escape(r)}</th>" for r in repos) + "<th>Total</th></tr>"
        rows_html = []
        for r in ctx.get("active_rules", []):
            rid = r["id"]
            per = coverage.get(rid, {})
            cells = []
            total = 0
            for rp in repos:
                n = per.get(rp, 0)
                total += n
                cell = f"<td>{n}</td>" if n else '<td class="muted">0</td>'
                cells.append(cell)
            rows_html.append(f"<tr><td>{html.escape(rid)}</td>{''.join(cells)}<td><strong>{total}</strong></td></tr>")
        coverage_html = f"<table><thead>{header}</thead><tbody>{''.join(rows_html)}</tbody></table>"
    else:
        coverage_html = '<p class="muted">No cross-repo coverage data.</p>'

    # --- recent iterations ---
    iter_links = []
    for p in ctx.get("recent_iterations", []):
        rel = os.path.relpath(p, out_path.parent)
        # extract first H1 as description
        title = p.stem
        try:
            for line in p.read_text().splitlines()[:5]:
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
        except Exception:
            pass
        iter_links.append(f'<li><a href="{rel}">{html.escape(p.name)}</a> — {html.escape(title)}</li>')
    iter_html = f'<ul>{"".join(iter_links)}</ul>' if iter_links else '<p class="muted">No iteration notes found.</p>'

    total_findings = sum(sum(per.values()) for per in coverage.values())

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>repo-bug-learner — dashboard</title>
<style>{CSS}</style>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
</head>
<body>
<header>
  <h1>repo-bug-learner — pipeline dashboard</h1>
  <div class="subtitle">Generated {html.escape(ctx['build_timestamp'])} &middot; last-mined commit <code>{html.escape(ctx['last_commit_sha'][:12])}</code> &middot; clusters source: <code>{html.escape(ctx['clusters_source'])}</code></div>
</header>
<main>

<section>
  <h2>Overview</h2>
  <div class="cards">{cards_html}</div>
</section>

<section>
  <h2>Active ruleset ({len(ctx.get('active_rules', []))} rules &middot; {total_findings} findings)</h2>
  {active_rules_html}
</section>

<section>
  <h2>Cross-repo coverage</h2>
  <div class="muted">Number of findings per (rule, repo) from the latest iteration scans.</div>
  {coverage_html}
</section>

<section>
  <h2>Recent iterations</h2>
  {iter_html}
</section>

<section>
  <h2>Corpus over time (fix-commits per month)</h2>
  <div id="ts-chart"></div>
</section>

<section>
  <h2>Top fix-commit authors</h2>
  <table><thead><tr><th>#</th><th>Author</th><th>Fix commits</th></tr></thead>
  <tbody>{authors_rows}</tbody></table>
</section>

<section>
  <h2>Cluster scatter (TF-IDF &rarr; TruncatedSVD(2))</h2>
  <div class="muted">Each point is one fix entry. Color = cluster id (-1 = unassigned).</div>
  <div id="scatter-chart"></div>
</section>

<section>
  <h2>Clusters</h2>
  {clusters_html}
</section>

<section>
  <h2>Candidate rules</h2>
  {rules_table_html}
</section>

<section>
  <h2>Pipeline</h2>
  <pre class="ascii">{html.escape(ASCII_PIPELINE)}</pre>
</section>

</main>
<footer>
  Built {html.escape(ctx['build_timestamp'])} &middot; repo-bug-learner
</footer>
<script>
Plotly.newPlot('ts-chart', {ts_json}, {ts_layout}, {{displayModeBar: false, responsive: true}});
Plotly.newPlot('scatter-chart', {sc_data}, {sc_layout}, {{displayModeBar: true, responsive: true}});
</script>
</body>
</html>
"""
    out_path.write_text(html_doc)


# ---------- main ----------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=str(DEFAULT_OUTPUT))
    ap.add_argument("--corpus", default=str(PROJECT_ROOT / "out" / "corpus" / "corpus_full.jsonl"))
    ap.add_argument("--out-dir", default=str(PROJECT_ROOT / "out"))
    ap.add_argument("--candidates", default=str(PROJECT_ROOT / "out" / "candidates"))
    ap.add_argument("--scheduler-repo", default=str(SCHEDULER_REPO))
    args = ap.parse_args()

    out_path = pathlib.Path(args.output)
    out_dir = pathlib.Path(args.out_dir)
    corpus_path = pathlib.Path(args.corpus)
    cand_dir = pathlib.Path(args.candidates)
    repo = pathlib.Path(args.scheduler_repo)

    print(f"[info] loading corpus from {corpus_path}", file=sys.stderr)
    entries = load_corpus(corpus_path)
    print(f"[info] {len(entries)} corpus entries", file=sys.stderr)

    clusters_dir, clusters_src = pick_clusters_dir(out_dir)
    print(f"[info] clusters from {clusters_dir} ({clusters_src})", file=sys.stderr)
    clusters = load_clusters(clusters_dir)
    print(f"[info] {len(clusters)} clusters", file=sys.stderr)

    rules = load_candidates(cand_dir)
    print(f"[info] {len(rules)} candidate slots", file=sys.stderr)

    # active rules (opengrep + scalafix)
    rv_root = PROJECT_ROOT / "rule-validator" / "rules"
    opengrep_rules = load_opengrep_rules(rv_root)
    scalafix_rules = load_scalafix_rules(rv_root / "src")
    active_rules = scalafix_rules + opengrep_rules
    print(f"[info] {len(active_rules)} active rules ({len(scalafix_rules)} scalafix + {len(opengrep_rules)} opengrep)", file=sys.stderr)

    # latest iter scans + coverage
    iter_dir = PROJECT_ROOT / "out" / "iterations"
    scans = load_iter_scans(iter_dir)
    all_findings, coverage = aggregate_findings(scans)
    print(f"[info] merged {len(all_findings)} findings from {len(scans)} scan files", file=sys.stderr)

    recent_iters = load_recent_iterations(iter_dir, n=3)

    # overview
    unique_commits = {e.get("commit_sha") for e in entries if e.get("commit_sha")}
    unique_prs = {e.get("pr_url") for e in entries if e.get("pr_url")}
    unique_repos = {e.get("repo") for e in entries if e.get("repo")}
    langs = collections.Counter(e.get("language", "?") for e in entries)
    dates = [e.get("committed_at") for e in entries if e.get("committed_at")]
    dates_parsed = []
    for d in dates:
        try:
            dates_parsed.append(dt.datetime.fromisoformat(d.replace("Z", "+00:00")))
        except Exception:
            pass
    if dates_parsed:
        date_range = f"{min(dates_parsed).date()} → {max(dates_parsed).date()}"
    else:
        date_range = "unknown"

    lang_str = ", ".join(f"{lang}: {n}" for lang, n in langs.most_common())

    total_findings_count = sum(sum(per.values()) for per in coverage.values())
    overview_cards = [
        ("Corpus entries", len(entries)),
        ("Unique commits", len(unique_commits)),
        ("Unique PRs", len(unique_prs)),
        ("Repos", len(unique_repos)),
        ("Date range", date_range),
        ("Languages", lang_str or "n/a"),
        ("Clusters", len(clusters)),
        ("Rule candidates", sum(1 for r in rules if r["status"] == "rule")),
        ("Active rules", len(active_rules)),
        ("Live findings", total_findings_count),
    ]

    # time series
    ts = build_time_series(entries)

    # top authors
    print("[info] computing top authors from git…", file=sys.stderr)
    shas = sorted({e["commit_sha"] for e in entries if e.get("commit_sha")})
    top_authors = get_top_authors(repo, shas, top_n=10)
    print(f"[info] top author top-1: {top_authors[:1]}", file=sys.stderr)

    # cluster assignments for scatter: map bug_key -> cluster_id
    assignments: dict[str, int] = {}
    for c in clusters:
        cid = c.get("cluster_id")
        if cid is None:
            continue
        for e in c.get("entries", []) or []:
            bk = e.get("bug_key")
            if bk:
                assignments[bk] = int(cid)

    print("[info] building scatter…", file=sys.stderr)
    scatter = build_scatter(entries, assignments)

    last_sha = ""
    if shas:
        # pick the most recent by committed_at
        latest = max((e for e in entries if e.get("commit_sha")), key=lambda x: x.get("committed_at") or "")
        last_sha = latest.get("commit_sha", "")

    ctx = {
        "overview_cards": overview_cards,
        "time_series": ts,
        "top_authors": top_authors,
        "scatter": scatter,
        "clusters": clusters,
        "rules": rules,
        "build_timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "last_commit_sha": last_sha or "n/a",
        "clusters_source": clusters_src,
        "active_rules": active_rules,
        "coverage": coverage,
        "recent_iterations": recent_iters,
    }

    render(out_path, ctx)
    size_kb = out_path.stat().st_size // 1024
    print(f"[ok] wrote {out_path} ({size_kb} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
