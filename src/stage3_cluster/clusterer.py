"""Stage 3b: Cluster corpus entries by embedding similarity.

HDBSCAN is the right choice over k-means here for two reasons:
  1. We don't know the number of clusters in advance — there might be 5 recurring
     bug patterns or 50.
  2. HDBSCAN naturally produces a "noise" cluster (-1) for one-off bugs that don't
     repeat. Those get filtered out — we only synthesize rules for clusters with
     ≥ min_cluster_size members.

After clustering, an LLM call summarizes each cluster in 1-2 sentences. That
summary feeds into the rule-synthesis prompt in stage 4.

Persistence: corpus entries + embeddings + cluster ids land in Postgres (pgvector).
This means the continuous loop can query "which cluster does this new bug belong
to?" without recomputing everything.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import hdbscan
import numpy as np
import psycopg
from psycopg.rows import dict_row
from rich.console import Console

from ..config import Config
from ..types import Cluster, CorpusEntry

console = Console()


SCHEMA_DDL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS corpus_entries (
    id BIGSERIAL PRIMARY KEY,
    bug_key TEXT NOT NULL,
    repo TEXT NOT NULL,
    file_path TEXT NOT NULL,
    language TEXT NOT NULL,
    buggy_code TEXT NOT NULL,
    fix_diff TEXT NOT NULL,
    bug_summary TEXT NOT NULL,
    jira_labels TEXT[] NOT NULL DEFAULT '{}',
    szz_confidence REAL NOT NULL,
    embedding VECTOR,                       -- dim set at insert time
    cluster_id INT,                         -- nullable; -1 = noise
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (bug_key, file_path)
);

CREATE INDEX IF NOT EXISTS corpus_cluster_idx ON corpus_entries (cluster_id);
CREATE INDEX IF NOT EXISTS corpus_embedding_idx ON corpus_entries
    USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS clusters (
    cluster_id INT PRIMARY KEY,
    description TEXT,
    centroid VECTOR,
    size INT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
"""


class Clusterer:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.min_cluster_size = int(config["clustering"]["min_cluster_size"])

    def connect(self) -> psycopg.Connection:
        pg = self.config["postgres"]
        return psycopg.connect(
            host=pg["host"], port=pg["port"],
            dbname=pg["database"], user=pg["user"], password=pg["password"],
            row_factory=dict_row,
        )

    def init_schema(self) -> None:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(SCHEMA_DDL)
            conn.commit()
        console.log("Initialized pgvector schema")

    def cluster(self, entries: list[CorpusEntry], embeddings: np.ndarray) -> list[Cluster]:
        """Run HDBSCAN, attach cluster ids to entries, return Cluster objects."""
        if len(entries) < self.min_cluster_size:
            console.log(f"[yellow]Only {len(entries)} entries — skipping clustering[/yellow]")
            return []

        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=self.min_cluster_size,
            metric="euclidean",                          # embeddings already normalized
            cluster_selection_method="eom",
        )
        labels = clusterer.fit_predict(embeddings)

        # Group entries by cluster id
        grouped: dict[int, list[CorpusEntry]] = defaultdict(list)
        for entry, label in zip(entries, labels, strict=True):
            entry.cluster_id = int(label)
            grouped[int(label)].append(entry)

        # Drop noise cluster (-1), build Cluster objects for the rest
        clusters: list[Cluster] = []
        for cid, group in grouped.items():
            if cid == -1:
                continue
            indices = [i for i, e in enumerate(entries) if e.cluster_id == cid]
            centroid = embeddings[indices].mean(axis=0)
            clusters.append(Cluster(
                cluster_id=cid,
                entries=group,
                centroid_embedding=centroid.tolist(),
                description=None,
            ))

        noise = sum(1 for label in labels if label == -1)
        console.log(
            f"Clustered into {len(clusters)} groups "
            f"({noise}/{len(entries)} entries = noise, dropped)"
        )
        return clusters

    def persist(self, entries: list[CorpusEntry], clusters: list[Cluster]) -> None:
        """Upsert entries + clusters into pgvector."""
        with self.connect() as conn, conn.cursor() as cur:
            for e in entries:
                if e.embedding is None:
                    continue
                cur.execute(
                    """
                    INSERT INTO corpus_entries
                        (bug_key, repo, file_path, language, buggy_code, fix_diff,
                         bug_summary, jira_labels, szz_confidence, embedding, cluster_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (bug_key, file_path) DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        cluster_id = EXCLUDED.cluster_id
                    """,
                    (e.bug_key, e.repo, e.file_path, e.language, e.buggy_code, e.fix_diff,
                     e.bug_summary, e.jira_labels, e.szz_confidence, e.embedding, e.cluster_id),
                )
            for c in clusters:
                cur.execute(
                    """
                    INSERT INTO clusters (cluster_id, description, centroid, size)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (cluster_id) DO UPDATE SET
                        description = EXCLUDED.description,
                        centroid = EXCLUDED.centroid,
                        size = EXCLUDED.size
                    """,
                    (c.cluster_id, c.description, c.centroid_embedding, len(c.entries)),
                )
            conn.commit()
        console.log(f"Persisted {len(entries)} entries and {len(clusters)} clusters to pgvector")

    def find_cluster_for_new_entry(self, embedding: list[float], threshold: float = 0.75) -> int | None:
        """For the continuous loop: which existing cluster does a new bug belong to?"""
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT cluster_id, 1 - (centroid <=> %s::vector) AS similarity
                FROM clusters
                ORDER BY centroid <=> %s::vector
                LIMIT 1
                """,
                (embedding, embedding),
            )
            row = cur.fetchone()
            if row and row["similarity"] >= threshold:
                return int(row["cluster_id"])
        return None
