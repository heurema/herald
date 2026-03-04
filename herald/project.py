"""Project brief generator for Herald v2.

Generates a markdown digest of recent stories from the database,
grouped by story type, with YAML frontmatter metadata.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from herald.db import Database


# Ordered list of story types for section rendering
_STORY_TYPE_ORDER: list[str] = ["release", "research", "tutorial", "opinion", "news"]

# Human-readable section headings per story type
_SECTION_HEADINGS: dict[str, str] = {
    "release": "Releases",
    "research": "Research",
    "tutorial": "Tutorials",
    "opinion": "Opinion",
    "news": "News",
}


def _fetch_stories(
    db: Database,
    since: int,
    max_stories: int,
    topic_filter: str | None,
) -> list[dict]:
    """Fetch active stories updated since a given Unix timestamp.

    Parameters
    ----------
    db:
        Open database connection.
    since:
        Unix timestamp; only stories with last_updated >= since are returned.
    max_stories:
        Maximum number of stories to return, ordered by score descending.
    topic_filter:
        If provided, restrict to stories that have this topic in story_topics.

    Returns
    -------
    list[dict]
        Each dict has keys: id, title, score, story_type.
    """
    if topic_filter is not None:
        rows = db.execute(
            """
            SELECT s.id, s.title, s.score, s.story_type
            FROM stories s
            JOIN story_topics st ON st.story_id = s.id
            WHERE s.last_updated >= ?
              AND s.status = 'active'
              AND st.topic = ?
            ORDER BY s.score DESC
            LIMIT ?
            """,
            (since, topic_filter, max_stories),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT s.id, s.title, s.score, s.story_type
            FROM stories s
            WHERE s.last_updated >= ?
              AND s.status = 'active'
            ORDER BY s.score DESC
            LIMIT ?
            """,
            (since, max_stories),
        ).fetchall()

    return [
        {
            "id": row[0],
            "title": row[1],
            "score": row[2],
            "story_type": row[3],
        }
        for row in rows
    ]


def _fetch_story_articles(db: Database, story_id: str) -> list[dict]:
    """Return articles linked to a story.

    Parameters
    ----------
    db:
        Open database connection.
    story_id:
        Story identifier.

    Returns
    -------
    list[dict]
        Each dict has keys: url, title, source_name.
    """
    rows = db.execute(
        """
        SELECT a.url_canonical, a.title, s.name
        FROM story_articles sa
        JOIN articles a ON a.id = sa.article_id
        JOIN sources s ON s.id = a.origin_source_id
        WHERE sa.story_id = ?
        ORDER BY a.score_base DESC
        """,
        (story_id,),
    ).fetchall()
    return [{"url": row[0], "title": row[1], "source_name": row[2]} for row in rows]


def _fetch_story_topics(db: Database, story_id: str) -> list[str]:
    """Return topic tags for a story.

    Parameters
    ----------
    db:
        Open database connection.
    story_id:
        Story identifier.

    Returns
    -------
    list[str]
        Topic strings, ordered alphabetically.
    """
    rows = db.execute(
        "SELECT topic FROM story_topics WHERE story_id = ? ORDER BY topic",
        (story_id,),
    ).fetchall()
    return [row[0] for row in rows]


def _render_story(story: dict, articles: list[dict], topics: list[str]) -> str:
    """Render a single story as a markdown block.

    Parameters
    ----------
    story:
        Story dict with keys id, title, score, story_type.
    articles:
        List of article dicts with keys url, title, source_name.
    topics:
        List of topic tag strings.

    Returns
    -------
    str
        Markdown-formatted story block.
    """
    lines: list[str] = []

    # Title line with score badge
    score = story["score"]
    source_count = len({a["source_name"] for a in articles})
    source_label = "source" if source_count == 1 else "sources"
    lines.append(f"### {story['title']}")
    lines.append(f"")
    lines.append(f"⭐ {score:.2f} &nbsp;·&nbsp; {source_count} {source_label}")

    # Topic tags (if any)
    if topics:
        tag_line = " ".join(f"`{t}`" for t in topics)
        lines.append(f"")
        lines.append(tag_line)

    # Article URLs as bullet list
    if articles:
        lines.append(f"")
        for article in articles:
            lines.append(f"- [{article['title']}]({article['url']})")

    return "\n".join(lines)


def _render_section(story_type: str, stories_with_data: list[tuple]) -> str:
    """Render a section heading and its stories.

    Parameters
    ----------
    story_type:
        One of: release, research, tutorial, opinion, news.
    stories_with_data:
        List of (story, articles, topics) tuples.

    Returns
    -------
    str
        Markdown section string.
    """
    heading = _SECTION_HEADINGS.get(story_type, story_type.title())
    lines: list[str] = [f"## {heading}", ""]
    for story, articles, topics in stories_with_data:
        lines.append(_render_story(story, articles, topics))
        lines.append("")
    return "\n".join(lines)


def project_brief(
    db: Database,
    hours: int = 24,
    max_stories: int = 25,
    topic_filter: str | None = None,
) -> str:
    """Generate a markdown project brief from recent stories in the database.

    Produces a document with YAML frontmatter followed by stories grouped by
    type (release, research, tutorial, opinion, news), ordered by score
    descending within each section.

    Parameters
    ----------
    db:
        Open database connection.
    hours:
        Look-back window in hours. Only stories with last_updated within the
        last N hours are included. Default: 24.
    max_stories:
        Maximum total number of stories to include. Default: 25.
    topic_filter:
        If provided, restrict output to stories tagged with this topic.

    Returns
    -------
    str
        Markdown string with YAML frontmatter block.
    """
    now = int(time.time())
    since = now - hours * 3600

    stories = _fetch_stories(db, since, max_stories, topic_filter)

    # Build frontmatter
    generated_at = datetime.fromtimestamp(now, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    frontmatter_lines = [
        "---",
        f"generated_at: {generated_at}",
        f"story_count: {len(stories)}",
        f"period_hours: {hours}",
        "---",
    ]
    frontmatter = "\n".join(frontmatter_lines)

    if not stories:
        return frontmatter + "\n"

    # Group stories by type, preserving score order within each type
    grouped: dict[str, list[dict]] = {}
    for story in stories:
        st = story["story_type"]
        grouped.setdefault(st, []).append(story)

    # Render sections in canonical order, then any unknown types
    known = [t for t in _STORY_TYPE_ORDER if t in grouped]
    unknown = [t for t in grouped if t not in _STORY_TYPE_ORDER]
    ordered_types = known + sorted(unknown)

    sections: list[str] = []
    for story_type in ordered_types:
        type_stories = grouped[story_type]
        stories_with_data: list[tuple] = []
        for story in type_stories:
            articles = _fetch_story_articles(db, story["id"])
            topics = _fetch_story_topics(db, story["id"])
            stories_with_data.append((story, articles, topics))
        sections.append(_render_section(story_type, stories_with_data))

    body = "\n".join(sections)
    return frontmatter + "\n" + body
