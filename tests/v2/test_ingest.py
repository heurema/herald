"""Tests for herald/ingest.py — Herald v2 Ingest Stage."""
from __future__ import annotations

import pytest

from herald.db import Database
from herald.ingest import ingest_items, IngestResult
from herald.models import RawItem, Source


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "test.db")
    # Insert a source so foreign key constraints are satisfied
    d.execute("INSERT INTO sources (id, name, weight, category) VALUES ('src1', 'Test Source', 0.5, 'community')")
    yield d
    d.close()


@pytest.fixture
def source():
    return Source(id="src1", name="Test Source", weight=0.5, category="community")


@pytest.fixture
def sources(source):
    return {"src1": source}


def _make_item(url="https://example.com/article", title="Test Article", source_id="src1", points=10):
    return RawItem(url=url, title=title, source_id=source_id, published_at=1000000, points=points)


# AC1: ingest_items returns IngestResult with articles_new=1 when a new article is ingested
def test_ingest_new_article(db, sources):
    item = _make_item()
    result = ingest_items(db, [item], sources)
    assert isinstance(result, IngestResult)
    assert result.articles_new == 1
    assert result.articles_updated == 0

    row = db.execute("SELECT title, points FROM articles WHERE url_canonical = 'https://example.com/article'").fetchone()
    assert row is not None
    assert row["title"] == "Test Article"
    assert row["points"] == 10


# AC2: Ingesting same canonical URL a second time updates existing article and returns articles_updated=1
def test_ingest_duplicate_url_updates(db, sources):
    item1 = _make_item(points=10)
    result1 = ingest_items(db, [item1], sources)
    assert result1.articles_new == 1
    assert result1.articles_updated == 0

    item2 = _make_item(points=50)
    result2 = ingest_items(db, [item2], sources)
    assert result2.articles_new == 0
    assert result2.articles_updated == 1

    # points should be updated to max(10, 50) = 50
    row = db.execute("SELECT points FROM articles WHERE url_canonical = 'https://example.com/article'").fetchone()
    assert row is not None
    assert row["points"] == 50


# AC3: Each call to ingest_items inserts a mention row for the article+source pair
def test_ingest_creates_mention(db, sources):
    item = _make_item()
    ingest_items(db, [item], sources)

    rows = db.execute(
        "SELECT article_id, source_id FROM mentions WHERE source_id = 'src1'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["source_id"] == "src1"


# AC4: Topics are extracted from the item title using topic_rules and stored in article_topics
def test_ingest_assigns_topics(db, sources):
    item = _make_item(title="PyTorch 2.0 release — new AI features")
    topic_rules = {"ai": ["pytorch", "ai"], "python": ["python"]}
    ingest_items(db, [item], sources, topic_rules=topic_rules)

    rows = db.execute(
        "SELECT topic FROM article_topics"
    ).fetchall()
    topics = {row["topic"] for row in rows}
    assert "ai" in topics
    assert "python" not in topics


# AC5 covers all previous plus ensuring full suite passes (handled by running all tests)

# --- Additional tests for robustness ---

def test_ingest_empty_items(db, sources):
    """Empty items list returns zeros without error."""
    result = ingest_items(db, [], sources)
    assert result.articles_new == 0
    assert result.articles_updated == 0
    count = db.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    assert count == 0


def test_ingest_tracking_params_same_canonical(db, sources):
    """URLs differing only in tracking params canonicalize to same URL -> UPSERT."""
    item1 = _make_item(url="https://example.com/article?ref=hn")
    item2 = _make_item(url="https://example.com/article?utm_source=newsletter")
    result = ingest_items(db, [item1, item2], sources)
    assert result.articles_new == 1
    assert result.articles_updated == 1

    count = db.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    assert count == 1


def test_ingest_no_topic_rules_no_topics_inserted(db, sources):
    """No topic_rules -> no article_topics rows inserted."""
    item = _make_item(title="PyTorch AI release")
    ingest_items(db, [item], sources, topic_rules=None)

    count = db.execute("SELECT COUNT(*) FROM article_topics").fetchone()[0]
    assert count == 0


def test_ingest_mention_deduplication(db, sources):
    """Re-ingesting same article from same source does not create duplicate mentions."""
    item = _make_item()
    ingest_items(db, [item], sources)
    ingest_items(db, [item], sources)

    count = db.execute("SELECT COUNT(*) FROM mentions WHERE source_id = 'src1'").fetchone()[0]
    assert count == 1


def test_ingest_multiple_items(db, sources):
    """Multiple distinct items are each inserted as new articles."""
    items = [
        _make_item(url="https://example.com/a", title="Article A"),
        _make_item(url="https://example.com/b", title="Article B"),
        _make_item(url="https://example.com/c", title="Article C"),
    ]
    result = ingest_items(db, items, sources)
    assert result.articles_new == 3
    assert result.articles_updated == 0


def test_ingest_unknown_source_skipped(db):
    """Item with unknown source_id is skipped without error."""
    sources = {}  # no sources registered
    item = _make_item(source_id="unknown")
    result = ingest_items(db, [item], sources)
    assert result.articles_new == 0
    assert result.articles_updated == 0


def test_ingest_result_is_dataclass():
    r = IngestResult()
    assert r.articles_new == 0
    assert r.articles_updated == 0


def test_ingest_points_max_on_update(db, sources):
    """UPSERT keeps MAX(existing, new) points."""
    ingest_items(db, [_make_item(points=100)], sources)
    ingest_items(db, [_make_item(points=5)], sources)  # lower points -> no change
    row = db.execute("SELECT points FROM articles").fetchone()
    assert row["points"] == 100
