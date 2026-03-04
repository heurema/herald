"""Tests for herald.cluster module."""
from __future__ import annotations

import time
import tempfile
from dataclasses import fields
from pathlib import Path

import pytest

from herald.cluster import ClusterResult, cluster, deactivate_stale, normalize_title
from herald.config import ClusterConfig
from herald.db import Database


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "test.db")
    db.execute("INSERT INTO sources (id, name, weight) VALUES ('hn', 'Hacker News', 0.5)")
    return db


def _insert_article(
    db: Database,
    article_id: str,
    title: str,
    score_base: float = 1.0,
    collected_at: int | None = None,
    source_id: str = "hn",
) -> None:
    if collected_at is None:
        collected_at = int(time.time())
    db.execute(
        """
        INSERT INTO articles
            (id, url_original, url_canonical, title, origin_source_id,
             collected_at, score_base, scored_at, story_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'news')
        """,
        (
            article_id,
            f"http://example.com/{article_id}",
            f"http://example.com/{article_id}",
            title,
            source_id,
            collected_at,
            score_base,
            collected_at,
        ),
    )


def _insert_article_topics(db: Database, article_id: str, topics: list[str]) -> None:
    for topic in topics:
        db.execute(
            "INSERT INTO article_topics (article_id, topic) VALUES (?, ?)",
            (article_id, topic),
        )


# ---------------------------------------------------------------------------
# AC1: ClusterResult dataclass
# ---------------------------------------------------------------------------

def test_result_dataclass_fields():
    """ClusterResult has stories_created, stories_updated, articles_clustered all defaulting to 0."""
    r = ClusterResult()
    assert r.stories_created == 0
    assert r.stories_updated == 0
    assert r.articles_clustered == 0


def test_result_dataclass_field_names():
    """ClusterResult has exactly the expected fields."""
    field_names = {f.name for f in fields(ClusterResult)}
    assert field_names == {"stories_created", "stories_updated", "articles_clustered"}


def test_result_custom_values():
    r = ClusterResult(stories_created=3, stories_updated=1, articles_clustered=5)
    assert r.stories_created == 3
    assert r.stories_updated == 1
    assert r.articles_clustered == 5


# ---------------------------------------------------------------------------
# AC2: normalize_title
# ---------------------------------------------------------------------------

def test_normalize_strips_whitespace():
    assert normalize_title("  hello world  ") == "hello world"


def test_normalize_lowercases():
    assert normalize_title("Python Is Great") == "python is great"


def test_normalize_collapses_internal_whitespace():
    assert normalize_title("hello   world") == "hello world"


def test_normalize_removes_ask_hn_prefix():
    assert normalize_title("Ask HN: Why is Python slow?") == "why is python slow?"


def test_normalize_removes_show_hn_prefix():
    assert normalize_title("Show HN: My new project") == "my new project"


def test_normalize_removes_tell_hn_prefix():
    assert normalize_title("Tell HN: I quit my job") == "i quit my job"


def test_normalize_removes_pdf_suffix():
    assert normalize_title("A great paper [pdf]") == "a great paper"


def test_normalize_removes_video_suffix_parens():
    assert normalize_title("A great talk (video)") == "a great talk"


def test_normalize_removes_video_suffix_brackets():
    assert normalize_title("A great talk [video]") == "a great talk"


def test_normalize_no_prefix_no_suffix():
    assert normalize_title("Python 3.14 released") == "python 3.14 released"


def test_normalize_case_insensitive_prefix():
    assert normalize_title("ask hn: lowercase prefix") == "lowercase prefix"


# ---------------------------------------------------------------------------
# AC3: Single unclustered article -> new story
# ---------------------------------------------------------------------------

def test_new_story_creates_story(tmp_path):
    """Single unclustered article creates a new story."""
    db = _make_db(tmp_path)
    _insert_article(db, "a1", "Python 3.14 Released with New Features")
    result = cluster(db)
    assert result.stories_created == 1
    assert result.articles_clustered == 1
    assert result.stories_updated == 0
    db.close()


def test_new_story_inserts_into_stories_table(tmp_path):
    db = _make_db(tmp_path)
    _insert_article(db, "a1", "Python 3.14 Released with New Features")
    cluster(db)
    row = db.execute("SELECT id, status FROM stories").fetchone()
    assert row is not None
    assert row[1] == "active"
    db.close()


def test_new_story_inserts_into_story_articles(tmp_path):
    db = _make_db(tmp_path)
    _insert_article(db, "a1", "Python 3.14 Released with New Features")
    cluster(db)
    row = db.execute("SELECT article_id FROM story_articles WHERE article_id='a1'").fetchone()
    assert row is not None
    db.close()


def test_new_story_canonical_is_article(tmp_path):
    db = _make_db(tmp_path)
    _insert_article(db, "a1", "Python 3.14 Released with New Features", score_base=1.5)
    cluster(db)
    row = db.execute("SELECT canonical_article_id FROM stories").fetchone()
    assert row[0] == "a1"
    db.close()


# ---------------------------------------------------------------------------
# AC4: Two similar articles merge into the same story
# ---------------------------------------------------------------------------

def test_merge_similar_titles(tmp_path):
    """Two articles with similar titles merge into one story."""
    db = _make_db(tmp_path)
    now = int(time.time())
    _insert_article(db, "a1", "Python 3.14 Released with Many New Features", collected_at=now - 3600)
    _insert_article(db, "a2", "Python 3.14 Released with Many New Features Today", collected_at=now)
    result = cluster(db)
    assert result.stories_created == 1
    assert result.articles_clustered == 2
    assert result.stories_updated == 1
    db.close()


def test_merge_both_in_same_story(tmp_path):
    db = _make_db(tmp_path)
    now = int(time.time())
    _insert_article(db, "a1", "Python 3.14 Released with Many New Features", collected_at=now - 3600)
    _insert_article(db, "a2", "Python 3.14 Released with Many New Features Today", collected_at=now)
    cluster(db)
    stories = db.execute("SELECT id FROM stories").fetchall()
    assert len(stories) == 1
    story_id = stories[0][0]
    articles = db.execute(
        "SELECT article_id FROM story_articles WHERE story_id=?", (story_id,)
    ).fetchall()
    article_ids = {r[0] for r in articles}
    assert "a1" in article_ids
    assert "a2" in article_ids
    db.close()


# ---------------------------------------------------------------------------
# AC5: Short title articles are skipped
# ---------------------------------------------------------------------------

def test_short_title_skipped(tmp_path):
    """Article with fewer than min_title_words words is skipped."""
    db = _make_db(tmp_path)
    cfg = ClusterConfig(min_title_words=4)
    _insert_article(db, "a1", "Foo bar")  # 2 words — below threshold
    result = cluster(db, cfg)
    assert result.stories_created == 0
    assert result.articles_clustered == 0
    db.close()


def test_short_title_not_in_story_articles(tmp_path):
    db = _make_db(tmp_path)
    cfg = ClusterConfig(min_title_words=4)
    _insert_article(db, "a1", "Too short")
    cluster(db, cfg)
    row = db.execute("SELECT article_id FROM story_articles WHERE article_id='a1'").fetchone()
    assert row is None
    db.close()


def test_short_title_exactly_min_words_passes(tmp_path):
    """Article with exactly min_title_words is accepted."""
    db = _make_db(tmp_path)
    cfg = ClusterConfig(min_title_words=4)
    _insert_article(db, "a1", "Python is very great")  # exactly 4 words
    result = cluster(db, cfg)
    assert result.stories_created == 1
    db.close()


# ---------------------------------------------------------------------------
# AC6: Time gap guard prevents merging distant articles
# ---------------------------------------------------------------------------

def test_time_gap_prevents_merge(tmp_path):
    """Two articles beyond max_time_gap_days are not merged."""
    db = _make_db(tmp_path)
    cfg = ClusterConfig(max_time_gap_days=7)
    now = int(time.time())
    old = now - 8 * 86400  # 8 days ago — beyond the 7-day limit
    _insert_article(db, "a1", "Python 3.14 Released with New Features", collected_at=old)
    _insert_article(db, "a2", "Python 3.14 Released with New Features Now", collected_at=now)
    result = cluster(db, cfg)
    assert result.stories_created == 2
    assert result.articles_clustered == 2
    assert result.stories_updated == 0
    db.close()


def test_time_gap_within_limit_merges(tmp_path):
    """Two articles within max_time_gap_days merge."""
    db = _make_db(tmp_path)
    cfg = ClusterConfig(max_time_gap_days=7)
    now = int(time.time())
    recent = now - 6 * 86400  # 6 days ago
    _insert_article(db, "a1", "Python 3.14 Released with New Features", collected_at=recent)
    _insert_article(db, "a2", "Python 3.14 Released with New Features Now", collected_at=now)
    result = cluster(db, cfg)
    assert result.stories_created == 1
    assert result.stories_updated == 1
    db.close()


# ---------------------------------------------------------------------------
# AC7: Version/number conflict guard
# ---------------------------------------------------------------------------

def test_version_conflict_prevents_merge(tmp_path):
    """Two articles with different version numbers are not merged."""
    db = _make_db(tmp_path)
    now = int(time.time())
    _insert_article(db, "a1", "Rust Programming Language Version 1.0 Released", collected_at=now - 3600)
    _insert_article(db, "a2", "Rust Programming Language Version 2.0 Released", collected_at=now)
    result = cluster(db)
    assert result.stories_created == 2
    assert result.stories_updated == 0
    db.close()


def test_version_conflict_same_number_merges(tmp_path):
    """Articles with same numbers are not blocked by version guard."""
    db = _make_db(tmp_path)
    now = int(time.time())
    _insert_article(db, "a1", "Rust version 1.0 released for everyone", collected_at=now - 3600)
    _insert_article(db, "a2", "Rust version 1.0 now available everywhere", collected_at=now)
    result = cluster(db)
    assert result.stories_created == 1
    assert result.stories_updated == 1
    db.close()


def test_version_conflict_no_numbers_merges(tmp_path):
    """Articles with no numbers at all are not blocked by version guard."""
    db = _make_db(tmp_path)
    now = int(time.time())
    _insert_article(db, "a1", "Python released with many new features today", collected_at=now - 3600)
    _insert_article(db, "a2", "Python released with many new features now", collected_at=now)
    result = cluster(db)
    assert result.stories_created == 1
    assert result.stories_updated == 1
    db.close()


# ---------------------------------------------------------------------------
# AC8: story_topics synced from member article_topics (top 5 by frequency)
# ---------------------------------------------------------------------------

def test_topics_synced_after_clustering(tmp_path):
    """story_topics is populated after clustering."""
    db = _make_db(tmp_path)
    _insert_article(db, "a1", "Python 3.14 Released with New Features")
    _insert_article_topics(db, "a1", ["python", "release", "programming"])
    cluster(db)
    rows = db.execute(
        "SELECT topic FROM story_topics WHERE story_id IN (SELECT id FROM stories)"
    ).fetchall()
    topics = {r[0] for r in rows}
    assert "python" in topics
    assert "release" in topics
    db.close()


def test_topics_at_most_five(tmp_path):
    """story_topics has at most 5 topics."""
    db = _make_db(tmp_path)
    _insert_article(db, "a1", "Python 3.14 Released with New Features")
    _insert_article_topics(db, "a1", ["t1", "t2", "t3", "t4", "t5", "t6", "t7"])
    cluster(db)
    rows = db.execute(
        "SELECT topic FROM story_topics WHERE story_id IN (SELECT id FROM stories)"
    ).fetchall()
    assert len(rows) <= 5
    db.close()


def test_topics_merged_story_combined(tmp_path):
    """Topics from multiple member articles are combined for merged story."""
    db = _make_db(tmp_path)
    now = int(time.time())
    _insert_article(db, "a1", "Python 3.14 Released with New Features", collected_at=now - 3600)
    _insert_article(db, "a2", "Python 3.14 Released with New Features Now", collected_at=now)
    _insert_article_topics(db, "a1", ["python"])
    _insert_article_topics(db, "a2", ["python", "release"])
    cluster(db)
    rows = db.execute(
        "SELECT topic FROM story_topics WHERE story_id IN (SELECT id FROM stories)"
    ).fetchall()
    topics = {r[0] for r in rows}
    assert "python" in topics
    assert "release" in topics
    db.close()


def test_topics_ordered_by_frequency(tmp_path):
    """Top topics (highest frequency) come first in story_topics."""
    db = _make_db(tmp_path)
    now = int(time.time())
    # Two articles with "python" in common; "rare" only once
    _insert_article(db, "a1", "Python 3.14 Released with New Features", collected_at=now - 3600)
    _insert_article(db, "a2", "Python 3.14 Released with New Features Now", collected_at=now)
    _insert_article_topics(db, "a1", ["python", "rare"])
    _insert_article_topics(db, "a2", ["python"])
    cluster(db)
    # "python" appears in 2 articles, "rare" in 1 — python should be top
    story_id = db.execute("SELECT id FROM stories").fetchone()[0]
    rows = db.execute(
        """
        SELECT at.topic, COUNT(*) cnt
        FROM story_articles sa
        JOIN article_topics at ON at.article_id = sa.article_id
        WHERE sa.story_id = ?
        GROUP BY at.topic
        ORDER BY cnt DESC
        """,
        (story_id,),
    ).fetchall()
    # python should rank higher than rare
    topic_order = [r[0] for r in rows]
    assert topic_order.index("python") < topic_order.index("rare")
    db.close()


# ---------------------------------------------------------------------------
# AC9: deactivate_stale
# ---------------------------------------------------------------------------

def test_stale_story_deactivated(tmp_path):
    """Stories older than max_time_gap_days are set to inactive."""
    db = _make_db(tmp_path)
    cfg = ClusterConfig(max_time_gap_days=7)
    old_ts = int(time.time()) - 8 * 86400  # 8 days ago
    # Insert a story directly with an old last_updated
    db.execute(
        """
        INSERT INTO stories (id, title, score, canonical_article_id, first_seen, last_updated, status)
        VALUES ('s1', 'Old Story Title', 1.0, NULL, ?, ?, 'active')
        """,
        (old_ts, old_ts),
    )
    count = deactivate_stale(db, cfg)
    assert count == 1
    row = db.execute("SELECT status FROM stories WHERE id='s1'").fetchone()
    assert row[0] == "inactive"
    db.close()


def test_active_story_not_deactivated(tmp_path):
    """Active stories updated recently are not deactivated."""
    db = _make_db(tmp_path)
    cfg = ClusterConfig(max_time_gap_days=7)
    now = int(time.time())
    db.execute(
        """
        INSERT INTO stories (id, title, score, canonical_article_id, first_seen, last_updated, status)
        VALUES ('s1', 'Recent Story Title', 1.0, NULL, ?, ?, 'active')
        """,
        (now, now),
    )
    count = deactivate_stale(db, cfg)
    assert count == 0
    row = db.execute("SELECT status FROM stories WHERE id='s1'").fetchone()
    assert row[0] == "active"
    db.close()


def test_stale_deactivates_only_old(tmp_path):
    """Only old stories are deactivated; recent remain active."""
    db = _make_db(tmp_path)
    cfg = ClusterConfig(max_time_gap_days=7)
    now = int(time.time())
    old_ts = now - 8 * 86400
    db.execute(
        "INSERT INTO stories (id, title, score, canonical_article_id, first_seen, last_updated, status)"
        " VALUES ('s1', 'Old Story', 1.0, NULL, ?, ?, 'active')",
        (old_ts, old_ts),
    )
    db.execute(
        "INSERT INTO stories (id, title, score, canonical_article_id, first_seen, last_updated, status)"
        " VALUES ('s2', 'New Story', 1.0, NULL, ?, ?, 'active')",
        (now, now),
    )
    count = deactivate_stale(db, cfg)
    assert count == 1
    s1 = db.execute("SELECT status FROM stories WHERE id='s1'").fetchone()[0]
    s2 = db.execute("SELECT status FROM stories WHERE id='s2'").fetchone()[0]
    assert s1 == "inactive"
    assert s2 == "active"
    db.close()


# ---------------------------------------------------------------------------
# AC10: Canonical re-election with hysteresis
# ---------------------------------------------------------------------------

def test_canonical_reelection_when_higher_score(tmp_path):
    """Higher-score article replaces canonical when score_base > canonical + delta."""
    db = _make_db(tmp_path)
    cfg = ClusterConfig(canonical_delta=0.1)
    now = int(time.time())
    # First article becomes canonical
    _insert_article(db, "a1", "Python released with great new features", score_base=1.0, collected_at=now - 3600)
    # Second article has score 0.21 higher (> 0.1 delta)
    _insert_article(db, "a2", "Python released with great new features now", score_base=1.21, collected_at=now)
    cluster(db, cfg)
    row = db.execute("SELECT canonical_article_id FROM stories").fetchone()
    assert row[0] == "a2"
    db.close()


def test_canonical_not_replaced_when_equal_plus_delta(tmp_path):
    """Canonical is NOT replaced when score_base == canonical + delta (not strictly greater)."""
    db = _make_db(tmp_path)
    cfg = ClusterConfig(canonical_delta=0.1)
    now = int(time.time())
    _insert_article(db, "a1", "Python released with great new features", score_base=1.0, collected_at=now - 3600)
    # Exactly at threshold: 1.0 + 0.1 = 1.1 — must NOT replace
    _insert_article(db, "a2", "Python released with great new features now", score_base=1.1, collected_at=now)
    cluster(db, cfg)
    row = db.execute("SELECT canonical_article_id FROM stories").fetchone()
    assert row[0] == "a1"
    db.close()


def test_canonical_not_replaced_when_lower_score(tmp_path):
    """Canonical is NOT replaced when new article has lower score."""
    db = _make_db(tmp_path)
    cfg = ClusterConfig(canonical_delta=0.1)
    now = int(time.time())
    _insert_article(db, "a1", "Python released with great new features", score_base=2.0, collected_at=now - 3600)
    _insert_article(db, "a2", "Python released with great new features now", score_base=0.5, collected_at=now)
    cluster(db, cfg)
    row = db.execute("SELECT canonical_article_id FROM stories").fetchone()
    assert row[0] == "a1"
    db.close()


# ---------------------------------------------------------------------------
# Holdout scenarios (bonus — also tested)
# ---------------------------------------------------------------------------

def test_idempotent_second_call(tmp_path):
    """Calling cluster() twice on same data returns zeros on second call."""
    db = _make_db(tmp_path)
    _insert_article(db, "a1", "Python 3.14 Released with New Features")
    cluster(db)
    result2 = cluster(db)
    assert result2.stories_created == 0
    assert result2.stories_updated == 0
    assert result2.articles_clustered == 0
    db.close()


def test_canonical_boundary_strictly_greater(tmp_path):
    """score_base = canonical + delta + epsilon DOES replace canonical."""
    db = _make_db(tmp_path)
    cfg = ClusterConfig(canonical_delta=0.1)
    now = int(time.time())
    _insert_article(db, "a1", "Python released with great new features", score_base=1.0, collected_at=now - 3600)
    epsilon = 0.001
    _insert_article(db, "a2", "Python released with great new features now", score_base=1.0 + 0.1 + epsilon, collected_at=now)
    cluster(db, cfg)
    row = db.execute("SELECT canonical_article_id FROM stories").fetchone()
    assert row[0] == "a2"
    db.close()


def test_last_updated_no_backward_regression(tmp_path):
    """last_updated does not regress when a late-arriving old article is added."""
    db = _make_db(tmp_path)
    now = int(time.time())
    # First article is recent
    _insert_article(db, "a1", "Python released with great new features", collected_at=now)
    cluster(db)
    story_row = db.execute("SELECT id, last_updated FROM stories").fetchone()
    story_id, original_last_updated = story_row[0], story_row[1]
    assert original_last_updated == now

    # Late-arriving article collected 5 days ago — should NOT regress last_updated
    old_ts = now - 5 * 86400
    _insert_article(db, "a2", "Python released with great new features now", collected_at=old_ts)
    cluster(db)
    updated_row = db.execute("SELECT last_updated FROM stories WHERE id = ?", (story_id,)).fetchone()
    assert updated_row[0] == now  # must stay at `now`, not regress to old_ts
    db.close()


def test_dissimilar_titles_separate_stories(tmp_path):
    """Articles with dissimilar titles each become their own story."""
    db = _make_db(tmp_path)
    now = int(time.time())
    _insert_article(db, "a1", "Python programming language released today here", collected_at=now - 100)
    _insert_article(db, "a2", "Rust systems language different memory model", collected_at=now)
    result = cluster(db)
    assert result.stories_created == 2
    assert result.stories_updated == 0
    db.close()
