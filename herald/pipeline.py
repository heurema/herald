"""Herald v2 pipeline orchestrator.

Runs the full data pipeline: collect -> ingest -> cluster -> deactivate_stale -> project_brief.
Records execution metadata to pipeline_runs table and saves the brief to disk.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from herald.cluster import cluster, deactivate_stale
from herald.collect import collect_all
from herald.config import HeraldConfig
from herald.db import Database
from herald.ingest import ingest_items
from herald.project import project_brief


@dataclass
class PipelineResult:
    articles_new: int = 0
    articles_updated: int = 0
    stories_created: int = 0
    stories_updated: int = 0
    articles_clustered: int = 0
    brief: str = ""
    run_id: int = 0


def run_pipeline(
    config: HeraldConfig,
    db: Database,
    *,
    adapter_map: dict[str, str] | None = None,
    data_dir: Path | None = None,
) -> PipelineResult:
    """Run the full Herald pipeline and return aggregated counts.

    Parameters
    ----------
    config:
        Herald configuration with sources, clustering, and topic rules.
    db:
        Open database connection.
    adapter_map:
        Optional mapping of source.id -> adapter name ('rss', 'hn', 'tavily').
        Defaults to 'rss' for all sources when None.
    data_dir:
        Directory where briefs are saved. If None, brief is not saved to disk.
        Brief file is written to {data_dir}/briefs/{run_id}.md.
    """
    started_at = int(time.time())

    # Insert pipeline_runs row and retrieve the run_id
    cursor = db.execute(
        "INSERT INTO pipeline_runs (started_at) VALUES (?)",
        (started_at,),
    )
    run_id = cursor.lastrowid

    result = PipelineResult(run_id=run_id)
    error_text: str | None = None

    try:
        # Stage 1: collect
        sources_dict = {s.id: s for s in config.sources}
        raw_items = collect_all(config.sources, adapter_map=adapter_map)

        # Stage 2: ingest
        ingest_result = ingest_items(
            db,
            raw_items,
            sources_dict,
            topic_rules=config.topics or None,
        )
        result.articles_new = ingest_result.articles_new
        result.articles_updated = ingest_result.articles_updated

        # Stage 3: cluster
        cluster_result = cluster(db, config.clustering)
        result.stories_created = cluster_result.stories_created
        result.stories_updated = cluster_result.stories_updated
        result.articles_clustered = cluster_result.articles_clustered

        # Stage 4: deactivate stale stories
        deactivate_stale(db, config.clustering)

        # Stage 5: project brief
        brief_md = project_brief(db)
        result.brief = brief_md

        # Save brief to disk if data_dir is provided
        if data_dir is not None:
            briefs_dir = Path(data_dir) / "briefs"
            briefs_dir.mkdir(parents=True, exist_ok=True)
            brief_path = briefs_dir / f"{run_id}.md"
            brief_path.write_text(brief_md, encoding="utf-8")

    except Exception as exc:
        error_text = str(exc)
        raise
    finally:
        finished_at = int(time.time())
        db.execute(
            """
            UPDATE pipeline_runs
            SET finished_at = ?,
                articles_new = ?,
                articles_updated = ?,
                stories_created = ?,
                stories_updated = ?,
                error = ?
            WHERE id = ?
            """,
            (
                finished_at,
                result.articles_new,
                result.articles_updated,
                result.stories_created,
                result.stories_updated,
                error_text,
                run_id,
            ),
        )

    return result
