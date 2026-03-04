"""Clustering algorithm for Herald v2.

Groups unclustered articles into stories using title similarity, time gap,
version/number conflict, and topic overlap guards.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from herald.config import ClusterConfig
from herald.db import Database
from herald.scoring import story_score
from herald.ulid import generate_ulid


@dataclass
class ClusterResult:
    stories_created: int = 0
    stories_updated: int = 0
    articles_clustered: int = 0


# Common prefixes to strip from titles before comparison
_PREFIX_RE = re.compile(
    r"^(ask hn|show hn|tell hn)\s*:\s*",
    re.IGNORECASE,
)

# Trailing qualifiers like [pdf], (video), [video], (pdf)
_SUFFIX_RE = re.compile(
    r"\s*[\[\(][^\]\)]*[\]\)]\s*$",
    re.IGNORECASE,
)

# Digits or version strings used for conflict detection
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)*")


def normalize_title(title: str) -> str:
    """Normalize a title for similarity comparison."""
    t = title.strip()
    # Remove common prefixes
    t = _PREFIX_RE.sub("", t)
    # Remove trailing qualifiers like [pdf] or (video) — repeatedly
    while True:
        t2 = _SUFFIX_RE.sub("", t)
        if t2 == t:
            break
        t = t2
    t = t.lower()
    # Collapse internal whitespace
    t = " ".join(t.split())
    return t


def _has_version_conflict(norm_a: str, norm_b: str) -> bool:
    """Return True if the two titles have different numeric/version tokens."""
    nums_a = set(_NUMBER_RE.findall(norm_a))
    nums_b = set(_NUMBER_RE.findall(norm_b))
    if not nums_a and not nums_b:
        return False
    # If both have numbers and they differ, it's a conflict
    return nums_a != nums_b


def _title_similarity(norm_a: str, norm_b: str) -> float:
    return SequenceMatcher(None, norm_a, norm_b).ratio()


def _get_article_topics(db: Database, article_id: str) -> set[str]:
    rows = db.execute(
        "SELECT topic FROM article_topics WHERE article_id = ?",
        (article_id,),
    ).fetchall()
    return {row[0] for row in rows}


def _get_story_member_ids(db: Database, story_id: str) -> list[str]:
    rows = db.execute(
        "SELECT article_id FROM story_articles WHERE story_id = ?",
        (story_id,),
    ).fetchall()
    return [row[0] for row in rows]


def _sync_story_topics(db: Database, story_id: str) -> None:
    """Recompute story_topics from member article_topics (top 5 by frequency)."""
    rows = db.execute(
        """
        SELECT at.topic, COUNT(*) AS cnt
        FROM story_articles sa
        JOIN article_topics at ON at.article_id = sa.article_id
        WHERE sa.story_id = ?
        GROUP BY at.topic
        ORDER BY cnt DESC, at.topic
        LIMIT 5
        """,
        (story_id,),
    ).fetchall()
    db.execute("DELETE FROM story_topics WHERE story_id = ?", (story_id,))
    for row in rows:
        db.execute(
            "INSERT OR IGNORE INTO story_topics (story_id, topic) VALUES (?, ?)",
            (story_id, row[0]),
        )


def _recompute_story_score(db: Database, story_id: str, cfg: ClusterConfig) -> float:
    """Recompute the story score from member articles."""
    now = int(time.time())
    cutoff = now - cfg.max_time_gap_days * 86400

    rows = db.execute(
        """
        SELECT a.score_base, a.collected_at, a.origin_source_id
        FROM story_articles sa
        JOIN articles a ON a.id = sa.article_id
        WHERE sa.story_id = ?
        """,
        (story_id,),
    ).fetchall()

    if not rows:
        return 0.0

    max_score = max(row[0] for row in rows)
    source_count = len({row[2] for row in rows})
    has_recent = any(row[1] >= cutoff for row in rows)
    return story_score(max_score, source_count, has_recent)


def _can_merge(
    article_id: str,
    article_norm: str,
    article_topics: set[str],
    article_collected_at: int,
    story: dict,
    cfg: ClusterConfig,
    db: Database,
) -> bool:
    """Apply 4 merge guards. Return True if the article can merge into story."""
    # Guard 1: title similarity
    story_norm = normalize_title(story["title"])
    if _title_similarity(article_norm, story_norm) < cfg.threshold:
        return False

    # Guard 2: time gap
    max_gap_secs = cfg.max_time_gap_days * 86400
    if abs(article_collected_at - story["last_updated"]) > max_gap_secs:
        return False

    # Guard 3: version/number conflict
    if _has_version_conflict(article_norm, story_norm):
        return False

    # Guard 4: topic overlap (only blocks if both sides have topics)
    story_topics: set[str] = set()
    member_ids = _get_story_member_ids(db, story["id"])
    for mid in member_ids:
        story_topics |= _get_article_topics(db, mid)

    if article_topics and story_topics and not (article_topics & story_topics):
        return False

    return True


def cluster(db: Database, cfg: ClusterConfig | None = None) -> ClusterResult:
    """Cluster unclustered articles into stories.

    For each unclustered article (not in story_articles), attempt to merge
    into an existing active story. If no match found, create a new story.
    """
    if cfg is None:
        cfg = ClusterConfig()

    result = ClusterResult()

    # Fetch all unclustered articles ordered by collected_at ascending
    unclustered = db.execute(
        """
        SELECT a.id, a.title, a.collected_at, a.score_base, a.origin_source_id
        FROM articles a
        WHERE a.id NOT IN (SELECT article_id FROM story_articles)
        ORDER BY a.collected_at ASC
        """,
    ).fetchall()

    for article_row in unclustered:
        article_id = article_row[0]
        title = article_row[1]
        collected_at = article_row[2]
        score_base = article_row[3]

        norm = normalize_title(title)

        # Guard: skip short titles
        if len(norm.split()) < cfg.min_title_words:
            continue

        article_topics = _get_article_topics(db, article_id)

        # Find matching active stories (ordered by last_updated desc for recency)
        active_stories = db.execute(
            """
            SELECT id, title, last_updated, canonical_article_id
            FROM stories
            WHERE status = 'active'
            ORDER BY last_updated DESC
            """,
        ).fetchall()

        matched_story_id: str | None = None
        for story_row in active_stories:
            story = {
                "id": story_row[0],
                "title": story_row[1],
                "last_updated": story_row[2],
                "canonical_article_id": story_row[3],
            }
            if _can_merge(
                article_id,
                norm,
                article_topics,
                collected_at,
                story,
                cfg,
                db,
            ):
                matched_story_id = story["id"]
                break

        now = int(time.time())
        cutoff = now - cfg.max_time_gap_days * 86400

        with db.transaction():
            if matched_story_id is None:
                # Create new story — use story_score() for consistent scoring
                story_id = generate_ulid()
                has_recent = collected_at >= cutoff
                initial_score = story_score(score_base, 1, has_recent)
                db.execute(
                    """
                    INSERT INTO stories
                        (id, title, score, canonical_article_id, first_seen, last_updated, status)
                    VALUES (?, ?, ?, ?, ?, ?, 'active')
                    """,
                    (story_id, title, initial_score, article_id, collected_at, collected_at),
                )
                db.execute(
                    "INSERT INTO story_articles (story_id, article_id) VALUES (?, ?)",
                    (story_id, article_id),
                )
                _sync_story_topics(db, story_id)
                result.stories_created += 1
                result.articles_clustered += 1
            else:
                # Merge into existing story
                db.execute(
                    "INSERT INTO story_articles (story_id, article_id) VALUES (?, ?)",
                    (matched_story_id, article_id),
                )

                # Canonical re-election with hysteresis
                canon_row = db.execute(
                    "SELECT canonical_article_id FROM stories WHERE id = ?",
                    (matched_story_id,),
                ).fetchone()
                canon_id = canon_row[0] if canon_row else None

                new_canonical = canon_id
                if canon_id is not None:
                    canon_score_row = db.execute(
                        "SELECT score_base FROM articles WHERE id = ?",
                        (canon_id,),
                    ).fetchone()
                    if canon_score_row is not None:
                        canon_score = canon_score_row[0]
                        if score_base > canon_score + cfg.canonical_delta:
                            new_canonical = article_id
                else:
                    new_canonical = article_id

                # Recompute story score
                new_score = _recompute_story_score(db, matched_story_id, cfg)

                # Use max(current, collected_at) to prevent backward regression
                # when a late-arriving old article is added
                story_last_updated = story["last_updated"]
                updated_at = max(story_last_updated, collected_at)

                db.execute(
                    """
                    UPDATE stories
                    SET last_updated = ?, score = ?, canonical_article_id = ?
                    WHERE id = ?
                    """,
                    (updated_at, new_score, new_canonical, matched_story_id),
                )
                _sync_story_topics(db, matched_story_id)
                result.stories_updated += 1
                result.articles_clustered += 1

    return result


def deactivate_stale(db: Database, cfg: ClusterConfig | None = None) -> int:
    """Set status='inactive' on stories not updated within max_time_gap_days.

    Returns the number of stories deactivated.
    """
    if cfg is None:
        cfg = ClusterConfig()

    cutoff = int(time.time()) - cfg.max_time_gap_days * 86400
    cursor = db.execute(
        """
        UPDATE stories
        SET status = 'inactive'
        WHERE status = 'active' AND last_updated < ?
        """,
        (cutoff,),
    )
    return cursor.rowcount
