#!/usr/bin/env python3
"""Continuous loop: for one newly-closed bug, run stages 2-5.

Trigger options (pick one for your env):
  a) Jira webhook on "Issue Resolved" → POST to a small HTTP server that runs this
  b) Daily cron that polls Jira for bugs resolved in the last 24h
  c) Manual invocation: ./scripts/continuous_loop.py SCHED-12453

Behavior:
  1. Fetch the bug + its linked PR(s) from Jira/GitHub (stage 1)
  2. SZZ-label the bug-inducing commit
  3. Build a single-row CorpusEntry
  4. Embed it; query pgvector for the nearest existing cluster
  5a. If the new bug clusters with an existing pattern AND a rule already
      exists for that cluster: skip — the existing rule should have caught
      this. File a Jira ticket noting "rule X should have caught SCHED-N; why didn't it?"
  5b. If the new bug clusters but no rule yet exists for that cluster, AND the
      cluster now has >= min_cluster_size members: trigger synthesis (stage 4)
      for that one cluster, validate (stage 5), open PR (stage 6).
  5c. If the new bug doesn't cluster with anything: add to corpus and wait.
      Once enough siblings accumulate, the batch re-clustering (monthly) will
      pick them up.

This file is a skeleton — the wiring to your event source goes in main().
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console

from src.config import Config
from src.stage1_mine.jira_pr_miner import JiraPRMiner
from src.stage1_mine.szz_labeler import SZZLabeler
from src.stage2_corpus.corpus_builder import CorpusBuilder
from src.stage3_cluster.clusterer import Clusterer
from src.stage3_cluster.embedder import build_embedder
from src.stage4_synthesize.base import ClaudeClient
from src.stage4_synthesize.opengrep_synthesizer import OpengrepSynthesizer
from src.stage4_synthesize.scalafix_synthesizer import ScalafixSynthesizer
from src.stage5_validate.validator import Validator
from src.stage6_ship.pr_creator import PRShipper

console = Console()


@click.command()
@click.argument("bug_key")                              # e.g. SCHED-12453
@click.option("--config-path", default="config/config.toml", type=click.Path(exists=True))
@click.option("--repos-root", default="./repos", type=click.Path())
@click.option("--auto-ship", is_flag=True)
def main(bug_key: str, config_path: str, repos_root: str, auto_ship: bool) -> None:
    asyncio.run(_run(bug_key, Path(config_path), Path(repos_root), auto_ship))


async def _run(bug_key: str, config_path: Path, repos_root: Path, auto_ship: bool) -> None:
    config = Config.load(config_path)

    # Stage 1: fetch this one bug + its fixes
    miner = JiraPRMiner(config)
    bugs = miner._fetch_jira_bugs_by_key([bug_key])           # type: ignore[attr-defined]
    if not bugs:
        console.log(f"[red]Bug {bug_key} not found or not resolved[/red]")
        sys.exit(1)
    bug = bugs[0]
    fixing = miner._find_fixing_commits(bug)                  # type: ignore[attr-defined]
    if not fixing:
        console.log(f"[yellow]No fixing PR found for {bug_key}; cannot learn from it[/yellow]")
        sys.exit(0)

    # SZZ-label
    labeler = SZZLabeler(repos_root=repos_root, strategy="ra-szz")
    bug_inducing = []
    for fc in fixing:
        bug_inducing.extend(labeler.label(fc, bug.summary))
    if not bug_inducing:
        console.log(f"[yellow]SZZ couldn't identify bug-inducing commits for {bug_key}[/yellow]")
        sys.exit(0)

    # Build the single corpus entry
    builder = CorpusBuilder(output_dir=Path("./out/continuous"))
    entries = builder.build([bug], fixing, bug_inducing)
    if not entries:
        console.log("[yellow]No usable corpus rows generated[/yellow]")
        sys.exit(0)

    # Embed and find nearest cluster
    embedder = build_embedder(config)
    new_entry = entries[0]
    matrix = embedder.embed([
        f"{new_entry.bug_summary}\n{new_entry.buggy_code}\n{new_entry.fix_diff[:1500]}"
    ])
    new_entry.embedding = matrix[0].tolist()

    clusterer = Clusterer(config)
    cluster_id = clusterer.find_cluster_for_new_entry(
        new_entry.embedding,
        threshold=float(config["clustering"]["similarity_threshold"]),
    )

    if cluster_id is None:
        console.log(f"[blue]{bug_key}: doesn't match an existing cluster. Adding to corpus.[/blue]")
        clusterer.persist([new_entry], [])
        console.log("[blue]Run monthly re-clustering to pick this up.[/blue]")
        sys.exit(0)

    console.log(f"[green]{bug_key} clusters with cluster {cluster_id}[/green]")

    # Check whether we already have a shipped rule for this cluster
    if _rule_exists_for_cluster(config, cluster_id):
        console.log(
            f"[yellow]A rule already exists for cluster {cluster_id}, "
            f"but {bug_key} still slipped through. File a regression ticket.[/yellow]"
        )
        sys.exit(0)

    # No rule yet — synthesize, validate, optionally ship
    clusterer.persist([new_entry], [])
    cluster = _hydrate_cluster_from_pg(clusterer, cluster_id)
    if cluster is None:
        console.log("[red]Couldn't rehydrate cluster from Postgres[/red]")
        sys.exit(1)

    claude = ClaudeClient(config)
    scala_share = sum(1 for e in cluster.entries if e.language == "scala") / len(cluster.entries)
    synth = ScalafixSynthesizer(claude) if scala_share >= 0.5 else OpengrepSynthesizer(claude)
    candidate = await synth.synthesize(cluster)
    if candidate is None:
        console.log("[yellow]Synthesis returned nothing usable[/yellow]")
        sys.exit(0)

    validator = Validator(config, cluster.entries, repos_root)
    result = await validator.validate(candidate)
    if not result.ship:
        console.log(
            f"[yellow]Candidate {candidate.rule_id} below thresholds "
            f"(precision={result.precision:.2%}, recall={result.recall_in_cluster:.2%}). "
            f"Queueing for human review.[/yellow]"
        )
        sys.exit(0)

    if not auto_ship:
        console.log(f"[green]{candidate.rule_id} validated. Rerun with --auto-ship to open PR.[/green]")
        sys.exit(0)

    shipper = PRShipper(config)
    shipper.ship_validated([candidate], [result])


def _rule_exists_for_cluster(config: Config, cluster_id: int) -> bool:
    """Check the rules repos for an existing rule referencing this cluster.

    Implementation hint: each shipped rule has cluster_id in its metadata
    block. List rule files via the GitHub API and grep, OR maintain a small
    `clusters_to_rules` table in Postgres updated by the PR shipper.
    """
    # TODO: implement once first rules ship. For now, assume no rule exists.
    return False


def _hydrate_cluster_from_pg(clusterer: Clusterer, cluster_id: int):
    """Pull all corpus entries for a cluster back from Postgres into a Cluster object."""
    from src.types import Cluster, CorpusEntry
    with clusterer.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT bug_key, repo, file_path, language, buggy_code, fix_diff,
                   bug_summary, jira_labels, szz_confidence, embedding, cluster_id
            FROM corpus_entries
            WHERE cluster_id = %s
            """,
            (cluster_id,),
        )
        rows = cur.fetchall()
        if not rows:
            return None
        entries = [CorpusEntry(**dict(r)) for r in rows]

        cur.execute("SELECT centroid, description FROM clusters WHERE cluster_id = %s", (cluster_id,))
        meta = cur.fetchone()
        centroid = meta["centroid"] if meta else [0.0] * 1024
        description = meta["description"] if meta else None

        return Cluster(
            cluster_id=cluster_id,
            entries=entries,
            centroid_embedding=list(centroid),
            description=description,
        )


if __name__ == "__main__":
    main()
