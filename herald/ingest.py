"""Herald v2 Ingest Stage: RawItem -> article UPSERT pipeline."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

from herald.db import Database
from herald.models import RawItem, Source
from herald.scoring import article_score_base
from herald.ulid import generate_ulid
from herald.url import canonicalize_url

_RELEASE_KEYWORDS = frozenset(
    {"release", "launches", "launch", "v1.", "v2.", "v3.", "version", "ships", "shipped"}
)

_TYPE_KEYWORDS: dict[str, frozenset[str]] = {
    "release": _RELEASE_KEYWORDS,
    "research": frozenset({"paper", "arxiv", "study", "survey", "benchmark"}),
    "opinion": frozenset({"opinion", "editorial", "why ", "how ", "thoughts on"}),
    "tutorial": frozenset({"tutorial", "guide", "how to", "howto", "step by step"}),
}


def _detect_release(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in _RELEASE_KEYWORDS)


def _detect_type(title: str) -> str:
    t = title.lower()
    for story_type, keywords in _TYPE_KEYWORDS.items():
        if any(kw in t for kw in keywords):
            return story_type
    return "news"


def _extract_topics(title: str, topic_rules: dict[str, list[str]]) -> list[str]:
    t = title.lower()
    return [topic for topic, keywords in topic_rules.items() if any(kw.lower() in t for kw in keywords)]


@dataclass
class IngestResult:
    articles_new: int = 0
    articles_updated: int = 0


def ingest_items(
    db: Database,
    items: list[RawItem],
    sources: dict[str, Source],
    topic_rules: dict[str, list[str]] | None = None,
) -> IngestResult:
    result = IngestResult()
    now = int(time.time())

    with db.transaction():
        for item in items:
            source = sources.get(item.source_id)
            if source is None:
                continue

            try:
                url_canonical = canonicalize_url(item.url)
            except Exception:
                continue

            # Pre-check: does this canonical URL already exist?
            existing = db.execute(
                "SELECT id, points FROM articles WHERE url_canonical = ?",
                (url_canonical,),
            ).fetchone()

            is_release = _detect_release(item.title)
            story_type = _detect_type(item.title)
            extra_json = json.dumps(item.extra) if item.extra else None

            if existing is None:
                # New article
                article_id = generate_ulid()
                score = article_score_base(
                    source_weight=source.weight,
                    points=item.points,
                    keyword_density=0.0,
                    is_release=is_release,
                )
                db.execute(
                    """
                    INSERT INTO articles
                        (id, url_original, url_canonical, title, origin_source_id,
                         published_at, collected_at, points, story_type, score_base,
                         scored_at, extra)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        article_id,
                        item.url,
                        url_canonical,
                        item.title,
                        item.source_id,
                        item.published_at,
                        now,
                        item.points,
                        story_type,
                        score,
                        now,
                        extra_json,
                    ),
                )
                result.articles_new += 1
            else:
                # Existing article — update only if new points are higher
                article_id = existing[0]
                existing_points = existing[1]
                effective_points = max(existing_points, item.points)
                score = article_score_base(
                    source_weight=source.weight,
                    points=effective_points,
                    keyword_density=0.0,
                    is_release=is_release,
                )
                if item.points > existing_points:
                    db.execute(
                        """
                        UPDATE articles
                        SET points = ?,
                            score_base = ?,
                            scored_at = ?
                        WHERE id = ?
                        """,
                        (effective_points, score, now, article_id),
                    )
                result.articles_updated += 1

            # Insert mention (ignore duplicates — same article+source)
            db.execute(
                """
                INSERT OR IGNORE INTO mentions
                    (article_id, source_id, url, points, discovered_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (article_id, item.source_id, item.url, item.points, now),
            )

            # Assign topics
            if topic_rules:
                topics = _extract_topics(item.title, topic_rules)
                for topic in topics:
                    db.execute(
                        "INSERT OR IGNORE INTO article_topics (article_id, topic) VALUES (?, ?)",
                        (article_id, topic),
                    )

    return result
