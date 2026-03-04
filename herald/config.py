"""Config loader for Herald v2."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from herald.models import Source


@dataclass
class ClusterConfig:
    threshold: float = 0.65
    max_time_gap_days: int = 7
    min_title_words: int = 4
    canonical_delta: float = 0.1


@dataclass
class ScheduleConfig:
    interval_hours: int = 4


@dataclass
class HeraldConfig:
    sources: list[Source] = field(default_factory=list)
    clustering: ClusterConfig = field(default_factory=ClusterConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    topics: dict = field(default_factory=dict)


_TYPE_ALIASES = {
    "hn_algolia": "hn",
    "hacker_news": "hn",
}


def _parse_source(raw: dict) -> Source:
    raw_type = raw.get("type", "rss")
    adapter_type = _TYPE_ALIASES.get(raw_type, raw_type)
    return Source(
        id=raw["id"],
        name=raw["name"],
        url=raw.get("url"),
        weight=raw.get("weight", 0.2),
        category=raw.get("category", "community"),
        type=adapter_type,
    )


def load_config(path: Path) -> HeraldConfig:
    """Load config from a YAML file."""
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return _parse_config(data)


def load_config_from_string(text: str) -> HeraldConfig:
    """Load config from a YAML string."""
    data = yaml.safe_load(text) or {}
    return _parse_config(data)


def _parse_config(data: dict) -> HeraldConfig:
    sources = [_parse_source(s) for s in data.get("sources", [])]

    cluster_data = data.get("clustering", {})
    clustering = ClusterConfig(
        threshold=cluster_data.get("threshold", 0.65),
        max_time_gap_days=cluster_data.get("max_time_gap_days", 7),
        min_title_words=cluster_data.get("min_title_words", 4),
        canonical_delta=cluster_data.get("canonical_delta", 0.1),
    )

    sched_data = data.get("schedule", {})
    schedule = ScheduleConfig(
        interval_hours=sched_data.get("interval_hours", 4),
    )

    topics = data.get("topics", {})

    return HeraldConfig(
        sources=sources,
        clustering=clustering,
        schedule=schedule,
        topics=topics,
    )
