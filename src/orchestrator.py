"""Orchestrator — wires the stages into a coherent batch run.

Subcommands:
  batch     Full pipeline from mining → ship for one repo, one time window.
  ship      Take an existing validated report and open PRs.
  triage    Pretty-print candidate rules for human review without shipping.
  schema    Initialize the pgvector schema in Postgres.
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import click
import numpy as np
from rich.console import Console

from .config import Config
from .stage1_mine.jira_pr_miner import JiraPRMiner, persist_raw
from .stage1_mine.szz_labeler import SZZLabeler
from .stage2_corpus.corpus_builder import CorpusBuilder
from .stage3_cluster.clusterer import Clusterer
from .stage3_cluster.embedder import build_embedder, embed_corpus
from .stage4_synthesize.base import ClaudeClient
from .stage4_synthesize.opengrep_synthesizer import OpengrepSynthesizer
from .stage4_synthesize.scalafix_synthesizer import ScalafixSynthesizer
from .stage5_validate.validator import Validator
from .stage6_ship.pr_creator import PRShipper
from .types import CandidateRule, Cluster, PipelineState, ValidationResult

console = Console()

OPENGREP_LANGUAGES = frozenset({"typescript", "javascript", "python", "go"})


def _dominant_language(cluster: Cluster) -> str:
    counts = Counter(e.language for e in cluster.entries)
    return counts.most_common(1)[0][0]


@click.group()
def cli() -> None:
    """repo-bug-learner CLI."""


@cli.command()
@click.option("--config-path", default="config/config.toml", type=click.Path(exists=True))
@click.option("--repo", required=True, help="GitHub repo name to mine (e.g. backend)")
@click.option("--since", required=True, help="ISO date — mine bugs resolved on or after this")
@click.option("--output", default="out/", type=click.Path())
@click.option("--repos-root", default="./repos", type=click.Path(),
              help="Where cloned git repos live")
@click.option("--skip-mining", is_flag=True, help="Reuse out/raw/bugs.jsonl from a prior run")
@click.option("--skip-synthesis", is_flag=True, help="Stop after stage 3")
@click.option("--auto-ship", is_flag=True, help="Open PRs for validated rules. Default: just report.")
def batch(
    config_path: str, repo: str, since: str, output: str, repos_root: str,
    skip_mining: bool, skip_synthesis: bool, auto_ship: bool,
) -> None:
    """Full batch pipeline for one repository."""
    config = Config.load(Path(config_path))
    state = PipelineState(
        config_path=Path(config_path),
        repo=repo,
        since=datetime.fromisoformat(since),
        output_dir=Path(output),
    )

    asyncio.run(_batch_async(state, config, Path(repos_root), skip_mining, skip_synthesis, auto_ship))


async def _batch_async(
    state: PipelineState, config: Config, repos_root: Path,
    skip_mining: bool, skip_synthesis: bool, auto_ship: bool,
) -> None:
    raw_path = state.output_dir / "raw" / "bugs.jsonl"
    if skip_mining and raw_path.exists():
        console.log("[blue]Reusing existing bugs.jsonl[/blue]")
    else:
        miner = JiraPRMiner(config)
        pairs = miner.mine(state.since)
        persist_raw(pairs, state.output_dir / "raw")
        state.bugs = [bug for bug, _ in pairs]
        state.fixing_commits = [c for _, commits in pairs for c in commits]

    labeler = SZZLabeler(repos_root=repos_root, strategy="ra-szz")
    bug_summaries = {b.key: b.summary for b in state.bugs}
    for fix in state.fixing_commits:
        state.bug_inducing_commits.extend(labeler.label(fix, bug_summaries.get(fix.bug_key, "")))

    console.log(f"SZZ labeled {len(state.bug_inducing_commits)} bug-inducing commits")

    builder = CorpusBuilder(output_dir=state.output_dir)
    state.corpus = builder.build(state.bugs, state.fixing_commits, state.bug_inducing_commits)
    builder.persist(state.corpus)

    embedder = build_embedder(config)
    embeddings: np.ndarray = embed_corpus(state.corpus, embedder)
    clusterer = Clusterer(config)
    clusterer.init_schema()
    state.clusters = clusterer.cluster(state.corpus, embeddings)
    clusterer.persist(state.corpus, state.clusters)

    if skip_synthesis:
        console.log("[blue]--skip-synthesis set; stopping after stage 3[/blue]")
        return

    claude = ClaudeClient(config)
    scalafix_synth = ScalafixSynthesizer(claude, config)
    opengrep_synth = OpengrepSynthesizer(claude, config)

    cap = int(config["synthesis"]["max_rules_per_run"])
    eligible_clusters = sorted(state.clusters, key=lambda c: -len(c.entries))[:cap]

    async def synth_one(cluster: Cluster) -> CandidateRule | None:
        dominant = _dominant_language(cluster)
        if dominant == "scala":
            rule = await scalafix_synth.synthesize(cluster)
            if rule:
                return rule
        if dominant in OPENGREP_LANGUAGES:
            return await opengrep_synth.synthesize(
                cluster, dominant_language=dominant  # type: ignore[arg-type]
            )
        return await opengrep_synth.synthesize(cluster)

    results = await asyncio.gather(*(synth_one(c) for c in eligible_clusters))
    state.candidate_rules = [r for r in results if r is not None]
    console.log(f"Synthesized {len(state.candidate_rules)} candidate rules")
    _persist_candidates(state)

    validator = Validator(config, state.corpus, repos_root)
    validation_results = await asyncio.gather(*(validator.validate(r) for r in state.candidate_rules))
    state.validated_rules = list(validation_results)
    _persist_validation_report(state)

    shippable = [r for r in state.validated_rules if r.ship]
    console.log(f"[green]{len(shippable)} rules passed validation, ready to ship[/green]")

    if not auto_ship:
        console.log("[blue]Run with --auto-ship to open PRs.[/blue]")
        return

    shipper = PRShipper(config)
    shipper.ship_validated(state.candidate_rules, state.validated_rules)


@cli.command()
@click.option("--config-path", default="config/config.toml", type=click.Path(exists=True))
@click.option("--report", required=True, type=click.Path(exists=True),
              help="Path to out/validated/report.json from a prior batch run")
def ship(config_path: str, report: str) -> None:
    """Ship rules from an existing validation report."""
    config = Config.load(Path(config_path))
    with Path(report).open() as f:
        report_data = json.load(f)

    candidates = [CandidateRule(**c) for c in report_data["candidates"]]
    results = [ValidationResult(**r) for r in report_data["results"]]
    shipper = PRShipper(config)
    shipper.ship_validated(candidates, results)


@cli.command()
@click.option("--config-path", default="config/config.toml", type=click.Path(exists=True))
def schema(config_path: str) -> None:
    """Initialize pgvector schema."""
    config = Config.load(Path(config_path))
    Clusterer(config).init_schema()


def _persist_candidates(state: PipelineState) -> None:
    out = state.output_dir / "candidates"
    out.mkdir(parents=True, exist_ok=True)
    for rule in state.candidate_rules:
        ext = "scala" if rule.target == "scalafix" else "yaml"
        (out / f"{rule.rule_id}.{ext}").write_text(rule.rule_source)
        (out / f"{rule.rule_id}.meta.json").write_text(json.dumps(asdict(rule), indent=2))


def _persist_validation_report(state: PipelineState) -> None:
    out = state.output_dir / "validated"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps({
        "candidates": [asdict(r) for r in state.candidate_rules],
        "results": [asdict(r) for r in state.validated_rules],
    }, indent=2))


if __name__ == "__main__":
    cli()
