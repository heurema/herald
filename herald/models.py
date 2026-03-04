"""Data models for Herald v2."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Source:
    id: str
    name: str
    url: str | None = None
    weight: float = 0.2
    category: str = "community"  # community | official | aggregator
    type: str = "rss"  # rss | hn | tavily


@dataclass
class RawItem:
    url: str
    title: str
    source_id: str
    published_at: int | None = None
    points: int = 0
    extra: dict | None = None


@dataclass
class Article:
    id: str
    url_original: str
    url_canonical: str
    title: str
    origin_source_id: str
    published_at: int | None
    collected_at: int
    points: int
    story_type: str
    score_base: float
    scored_at: int
    extra: dict | None = None


@dataclass
class Story:
    id: str
    title: str
    score: float
    canonical_article_id: str | None
    first_seen: int
    last_updated: int
    status: str = "active"
    summary: str | None = None
    story_type: str = "news"
