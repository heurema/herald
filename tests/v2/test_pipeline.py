"""Tests for herald/pipeline.py — Herald v2 pipeline orchestrator."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from herald.config import HeraldConfig, ClusterConfig
from herald.db import Database
from herald.models import RawItem, Source
from herald.pipeline import PipelineResult, run_pipeline


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "test.db")
    d.execute(
        "INSERT INTO sources (id, name, weight, category) VALUES ('src1', 'Test Source', 0.5, 'community')"
    )
    yield d
    d.close()


@pytest.fixture
def config():
    source = Source(id="src1", name="Test Source", url="http://example.com/rss", weight=0.5)
    return HeraldConfig(
        sources=[source],
        clustering=ClusterConfig(),
        topics={},
    )


def _make_raw_item(
    url: str = "https://example.com/article-one",
    title: str = "Example Article About Python Testing",
    source_id: str = "src1",
) -> RawItem:
    return RawItem(url=url, title=title, source_id=source_id, published_at=1_000_000, points=10)


# ---------------------------------------------------------------------------
# AC1: PipelineResult dataclass fields
# ---------------------------------------------------------------------------

def test_pipeline_result_dataclass():
    r = PipelineResult()
    assert r.articles_new == 0
    assert r.articles_updated == 0
    assert r.stories_created == 0
    assert r.stories_updated == 0
    assert r.articles_clustered == 0
    assert r.brief == ""
    assert r.run_id == 0

    r2 = PipelineResult(
        articles_new=3,
        articles_updated=1,
        stories_created=2,
        stories_updated=0,
        articles_clustered=3,
        brief="# Brief",
        run_id=42,
    )
    assert r2.articles_new == 3
    assert r2.articles_updated == 1
    assert r2.stories_created == 2
    assert r2.stories_updated == 0
    assert r2.articles_clustered == 3
    assert r2.brief == "# Brief"
    assert r2.run_id == 42


# ---------------------------------------------------------------------------
# AC2: run_pipeline executes all stages in order and returns aggregated counts
# ---------------------------------------------------------------------------

def test_pipeline_full_execution(db, config, tmp_path):
    items = [
        _make_raw_item(
            url="https://example.com/article-alpha",
            title="Python 3.14 Release Candidate ships today",
        ),
        _make_raw_item(
            url="https://example.com/article-beta",
            title="New research paper on machine learning benchmarks",
        ),
    ]

    with patch("herald.pipeline.collect_all", return_value=items):
        result = run_pipeline(config, db, data_dir=tmp_path)

    assert isinstance(result, PipelineResult)
    assert result.articles_new == 2
    assert result.articles_updated == 0
    # Each article gets its own story (titles are different)
    assert result.stories_created == 2
    assert result.articles_clustered == 2
    assert result.run_id > 0
    assert isinstance(result.brief, str)


# ---------------------------------------------------------------------------
# AC3: pipeline records execution to pipeline_runs table
# ---------------------------------------------------------------------------

def test_pipeline_records_run(db, config, tmp_path):
    items = [_make_raw_item()]

    with patch("herald.pipeline.collect_all", return_value=items):
        result = run_pipeline(config, db, data_dir=tmp_path)

    row = db.execute(
        "SELECT * FROM pipeline_runs WHERE id = ?", (result.run_id,)
    ).fetchone()

    assert row is not None
    assert row["started_at"] > 0
    assert row["finished_at"] is not None
    assert row["finished_at"] >= row["started_at"]
    assert row["articles_new"] == result.articles_new
    assert row["articles_updated"] == result.articles_updated
    assert row["stories_created"] == result.stories_created
    assert row["stories_updated"] == result.stories_updated
    assert row["error"] is None


# ---------------------------------------------------------------------------
# AC4: pipeline saves brief to {data_dir}/briefs/{run_id}.md
# ---------------------------------------------------------------------------

def test_pipeline_saves_brief(db, config, tmp_path):
    items = [_make_raw_item()]

    with patch("herald.pipeline.collect_all", return_value=items):
        result = run_pipeline(config, db, data_dir=tmp_path)

    brief_path = tmp_path / "briefs" / f"{result.run_id}.md"
    assert brief_path.exists(), f"Brief file not found: {brief_path}"

    content = brief_path.read_text(encoding="utf-8")
    assert content == result.brief
    assert "generated_at" in content  # YAML frontmatter


# ---------------------------------------------------------------------------
# AC5: on error, pipeline records error text and re-raises
# ---------------------------------------------------------------------------

def test_pipeline_error_handling(db, config, tmp_path):
    with patch("herald.pipeline.collect_all", side_effect=RuntimeError("network failure")):
        with pytest.raises(RuntimeError, match="network failure"):
            run_pipeline(config, db, data_dir=tmp_path)

    # pipeline_runs row should exist with error text and finished_at set
    rows = db.execute("SELECT * FROM pipeline_runs ORDER BY id DESC LIMIT 1").fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row["error"] == "network failure"
    assert row["finished_at"] is not None


# ---------------------------------------------------------------------------
# AC6: collect stage is mocked — full suite runs without network I/O
# ---------------------------------------------------------------------------

def test_pipeline_empty_collect(db, config, tmp_path):
    """collect_all returns [] -> pipeline completes with all zero counts."""
    with patch("herald.pipeline.collect_all", return_value=[]):
        result = run_pipeline(config, db, data_dir=tmp_path)

    assert result.articles_new == 0
    assert result.articles_updated == 0
    assert result.stories_created == 0
    assert result.stories_updated == 0
    assert result.articles_clustered == 0
    assert isinstance(result.brief, str)
    assert result.run_id > 0

    # Brief file should still be created
    brief_path = tmp_path / "briefs" / f"{result.run_id}.md"
    assert brief_path.exists()
