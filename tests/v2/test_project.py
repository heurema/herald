"""Tests for herald.project module."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from herald.db import Database
from herald.project import project_brief


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "test.db")
    db.execute("INSERT INTO sources (id, name, weight) VALUES ('src1', 'HackerNews', 0.5)")
    db.execute("INSERT INTO sources (id, name, weight) VALUES ('src2', 'Reddit', 0.3)")
    return db


def _insert_story(
    db: Database,
    story_id: str,
    title: str,
    score: float = 1.0,
    story_type: str = "news",
    first_seen: int | None = None,
    last_updated: int | None = None,
    status: str = "active",
) -> None:
    now = int(time.time())
    if first_seen is None:
        first_seen = now
    if last_updated is None:
        last_updated = now
    db.execute(
        """
        INSERT INTO stories (id, title, score, story_type, canonical_article_id,
                             first_seen, last_updated, status)
        VALUES (?, ?, ?, ?, NULL, ?, ?, ?)
        """,
        (story_id, title, score, story_type, first_seen, last_updated, status),
    )


def _insert_article(
    db: Database,
    article_id: str,
    title: str,
    source_id: str = "src1",
    score_base: float = 1.0,
    collected_at: int | None = None,
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


def _link_article(db: Database, story_id: str, article_id: str) -> None:
    db.execute(
        "INSERT INTO story_articles (story_id, article_id) VALUES (?, ?)",
        (story_id, article_id),
    )


def _add_topic(db: Database, story_id: str, topic: str) -> None:
    db.execute(
        "INSERT INTO story_topics (story_id, topic) VALUES (?, ?)",
        (story_id, topic),
    )


# ---------------------------------------------------------------------------
# AC1: YAML frontmatter with generated_at, story_count, period_hours
# ---------------------------------------------------------------------------

def test_project_brief_returns_markdown_with_frontmatter(tmp_path):
    """project_brief() returns a string with a valid YAML frontmatter block."""
    db = _make_db(tmp_path)
    result = project_brief(db)
    db.close()

    assert isinstance(result, str)
    assert result.startswith("---\n")
    assert "generated_at:" in result
    assert "story_count:" in result
    assert "period_hours:" in result
    # Frontmatter must be closed
    lines = result.split("\n")
    # First line is "---", find the closing "---"
    closing = lines.index("---", 1)
    assert closing > 0


def test_project_brief_frontmatter_story_count_zero_when_empty(tmp_path):
    """story_count in frontmatter reflects actual number of stories returned."""
    db = _make_db(tmp_path)
    result = project_brief(db)
    db.close()

    assert "story_count: 0" in result


def test_project_brief_frontmatter_period_hours_default(tmp_path):
    """period_hours defaults to 24."""
    db = _make_db(tmp_path)
    result = project_brief(db)
    db.close()

    assert "period_hours: 24" in result


def test_project_brief_frontmatter_period_hours_custom(tmp_path):
    """period_hours reflects the hours argument."""
    db = _make_db(tmp_path)
    result = project_brief(db, hours=48)
    db.close()

    assert "period_hours: 48" in result


def test_project_brief_frontmatter_story_count_with_stories(tmp_path):
    """story_count matches the number of stories rendered."""
    now = int(time.time())
    db = _make_db(tmp_path)
    _insert_story(db, "s1", "Story One", last_updated=now)
    _insert_story(db, "s2", "Story Two", last_updated=now)
    result = project_brief(db)
    db.close()

    assert "story_count: 2" in result


# ---------------------------------------------------------------------------
# AC2: Filtering by last N hours
# ---------------------------------------------------------------------------

def test_project_brief_filters_by_hours(tmp_path):
    """Only stories with last_updated within the time window are returned."""
    now = int(time.time())
    db = _make_db(tmp_path)
    # Recent story: updated 1 hour ago
    _insert_story(db, "recent", "Recent Story Title Here", last_updated=now - 3600)
    # Old story: updated 25 hours ago (outside default 24h window)
    _insert_story(db, "old", "Old Story Title Here", last_updated=now - 25 * 3600)

    result = project_brief(db, hours=24)
    db.close()

    assert "Recent Story Title Here" in result
    assert "Old Story Title Here" not in result


def test_project_brief_filters_boundary_included(tmp_path):
    """Stories at exactly the boundary (last_updated == since) are included."""
    now = int(time.time())
    db = _make_db(tmp_path)
    # Story updated exactly 24 hours ago
    boundary_ts = now - 24 * 3600
    _insert_story(db, "boundary", "Boundary Story Title Here", last_updated=boundary_ts)

    result = project_brief(db, hours=24)
    db.close()

    assert "Boundary Story Title Here" in result


def test_project_brief_all_outside_window_returns_empty_sections(tmp_path):
    """If all stories are outside the window, story_count=0 with valid frontmatter."""
    now = int(time.time())
    db = _make_db(tmp_path)
    _insert_story(db, "old", "Old Story Title Here", last_updated=now - 48 * 3600)

    result = project_brief(db, hours=1)
    db.close()

    assert "story_count: 0" in result
    assert result.startswith("---\n")


# ---------------------------------------------------------------------------
# AC3: max_stories parameter
# ---------------------------------------------------------------------------

def test_project_brief_respects_max_stories(tmp_path):
    """project_brief() returns at most max_stories stories."""
    now = int(time.time())
    db = _make_db(tmp_path)
    for i in range(10):
        _insert_story(db, f"s{i}", f"Story Number {i} with title", last_updated=now)

    result = project_brief(db, max_stories=3)
    db.close()

    assert "story_count: 3" in result


def test_project_brief_max_stories_default_25(tmp_path):
    """Default max_stories is 25 — returns all if fewer exist."""
    now = int(time.time())
    db = _make_db(tmp_path)
    for i in range(5):
        _insert_story(db, f"s{i}", f"Story Number {i} with title", last_updated=now)

    result = project_brief(db)
    db.close()

    assert "story_count: 5" in result


def test_project_brief_max_stories_orders_by_score(tmp_path):
    """max_stories keeps top-scored stories."""
    now = int(time.time())
    db = _make_db(tmp_path)
    _insert_story(db, "low", "Low Score Story Title", score=0.5, last_updated=now)
    _insert_story(db, "high", "High Score Story Title", score=9.9, last_updated=now)
    _insert_story(db, "mid", "Mid Score Story Title", score=5.0, last_updated=now)

    result = project_brief(db, max_stories=2)
    db.close()

    assert "High Score Story Title" in result
    assert "Mid Score Story Title" in result
    assert "Low Score Story Title" not in result


# ---------------------------------------------------------------------------
# AC4: Groups by story_type
# ---------------------------------------------------------------------------

def test_project_brief_groups_by_story_type(tmp_path):
    """project_brief() renders separate sections for each story_type."""
    now = int(time.time())
    db = _make_db(tmp_path)
    _insert_story(db, "r1", "New Library Released Today", story_type="release", last_updated=now)
    _insert_story(db, "n1", "Tech Industry News Headline", story_type="news", last_updated=now)

    result = project_brief(db)
    db.close()

    assert "## Releases" in result
    assert "## News" in result


def test_project_brief_section_order(tmp_path):
    """Sections appear in canonical type order: release, research, tutorial, opinion, news."""
    now = int(time.time())
    db = _make_db(tmp_path)
    _insert_story(db, "n1", "News Story Title Here", story_type="news", last_updated=now)
    _insert_story(db, "r1", "Release Story Title Here", story_type="release", last_updated=now)

    result = project_brief(db)
    db.close()

    release_pos = result.index("## Releases")
    news_pos = result.index("## News")
    assert release_pos < news_pos


def test_project_brief_only_present_types_rendered(tmp_path):
    """Sections for absent story types are not rendered."""
    now = int(time.time())
    db = _make_db(tmp_path)
    _insert_story(db, "r1", "Release Story Title Here", story_type="release", last_updated=now)

    result = project_brief(db)
    db.close()

    assert "## Releases" in result
    assert "## News" not in result
    assert "## Research" not in result


# ---------------------------------------------------------------------------
# AC5: Story format — title, score badge, source count, article URLs
# ---------------------------------------------------------------------------

def test_project_brief_story_format(tmp_path):
    """Each story block includes title, score badge, source count, and article URLs."""
    now = int(time.time())
    db = _make_db(tmp_path)
    _insert_story(db, "s1", "Python 3.14 Released With Speed", score=2.5,
                  story_type="release", last_updated=now)
    _insert_article(db, "a1", "Python 3.14 Released With Speed", source_id="src1")
    _link_article(db, "s1", "a1")

    result = project_brief(db)
    db.close()

    assert "### Python 3.14 Released With Speed" in result
    assert "⭐ 2.50" in result
    assert "1 source" in result
    assert "http://example.com/a1" in result


def test_project_brief_story_format_multiple_sources(tmp_path):
    """Source count is plural when multiple distinct sources are linked."""
    now = int(time.time())
    db = _make_db(tmp_path)
    _insert_story(db, "s1", "Big Tech Story Headline Today", score=1.5,
                  story_type="news", last_updated=now)
    _insert_article(db, "a1", "Big Tech Story Headline Today", source_id="src1")
    _insert_article(db, "a2", "Big Tech Story Coverage from Reddit", source_id="src2")
    _link_article(db, "s1", "a1")
    _link_article(db, "s1", "a2")

    result = project_brief(db)
    db.close()

    assert "2 sources" in result
    assert "http://example.com/a1" in result
    assert "http://example.com/a2" in result


def test_project_brief_story_format_score_two_decimal(tmp_path):
    """Score badge always shows two decimal places."""
    now = int(time.time())
    db = _make_db(tmp_path)
    _insert_story(db, "s1", "Score Format Test Story Title", score=1.0,
                  story_type="news", last_updated=now)

    result = project_brief(db)
    db.close()

    assert "⭐ 1.00" in result


def test_project_brief_story_article_link_format(tmp_path):
    """Article links are rendered as markdown links with title and URL."""
    now = int(time.time())
    db = _make_db(tmp_path)
    _insert_story(db, "s1", "Article Link Format Story", story_type="news",
                  last_updated=now)
    _insert_article(db, "a1", "Link Article Title Here", source_id="src1")
    _link_article(db, "s1", "a1")

    result = project_brief(db)
    db.close()

    assert "[Link Article Title Here](http://example.com/a1)" in result


# ---------------------------------------------------------------------------
# AC6: topic_filter parameter
# ---------------------------------------------------------------------------

def test_project_brief_topic_filter(tmp_path):
    """topic_filter restricts output to stories with the specified topic."""
    now = int(time.time())
    db = _make_db(tmp_path)
    _insert_story(db, "py", "Python Language Update Release", story_type="release",
                  last_updated=now)
    _insert_story(db, "rs", "Rust Language Update Release", story_type="release",
                  last_updated=now)
    _add_topic(db, "py", "python")
    _add_topic(db, "rs", "rust")

    result = project_brief(db, topic_filter="python")
    db.close()

    assert "Python Language Update Release" in result
    assert "Rust Language Update Release" not in result


def test_project_brief_topic_filter_no_match_returns_empty(tmp_path):
    """topic_filter with no matching stories returns story_count=0."""
    now = int(time.time())
    db = _make_db(tmp_path)
    _insert_story(db, "py", "Python Language Update Release", story_type="release",
                  last_updated=now)
    _add_topic(db, "py", "python")

    result = project_brief(db, topic_filter="nonexistent")
    db.close()

    assert "story_count: 0" in result
    assert "Python Language Update Release" not in result


def test_project_brief_topic_filter_none_returns_all(tmp_path):
    """topic_filter=None (default) returns all stories regardless of topics."""
    now = int(time.time())
    db = _make_db(tmp_path)
    _insert_story(db, "py", "Python Language Story Title", story_type="news",
                  last_updated=now)
    _insert_story(db, "rs", "Rust Language Story Title", story_type="news",
                  last_updated=now)

    result = project_brief(db)
    db.close()

    assert "Python Language Story Title" in result
    assert "Rust Language Story Title" in result


def test_project_brief_topic_filter_story_count_reflects_filter(tmp_path):
    """story_count in frontmatter counts only filtered stories."""
    now = int(time.time())
    db = _make_db(tmp_path)
    _insert_story(db, "py", "Python Language Story Title", story_type="news",
                  last_updated=now)
    _insert_story(db, "rs", "Rust Language Story Title", story_type="news",
                  last_updated=now)
    _add_topic(db, "py", "python")
    _add_topic(db, "rs", "rust")

    result = project_brief(db, topic_filter="python")
    db.close()

    assert "story_count: 1" in result


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------

def test_project_brief_story_with_topics_rendered(tmp_path):
    """Stories with topics show topic tags in the markdown."""
    now = int(time.time())
    db = _make_db(tmp_path)
    _insert_story(db, "s1", "Tagged Story With Topics Here", story_type="news",
                  last_updated=now)
    _add_topic(db, "s1", "python")
    _add_topic(db, "s1", "release")

    result = project_brief(db)
    db.close()

    assert "`python`" in result
    assert "`release`" in result


def test_project_brief_story_no_articles(tmp_path):
    """Stories with no articles are included without crashing."""
    now = int(time.time())
    db = _make_db(tmp_path)
    _insert_story(db, "s1", "Story Without Articles Here", story_type="news",
                  last_updated=now)

    result = project_brief(db)
    db.close()

    assert "Story Without Articles Here" in result
    assert "story_count: 1" in result


def test_project_brief_empty_db(tmp_path):
    """Empty database returns valid frontmatter with story_count=0."""
    db = _make_db(tmp_path)
    result = project_brief(db)
    db.close()

    assert result.startswith("---\n")
    assert "story_count: 0" in result
    assert "period_hours: 24" in result
