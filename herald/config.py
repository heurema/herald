"""Config loader for Herald v2."""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from herald.models import Source

_PRESETS_DIR = Path(__file__).resolve().parent.parent / "presets"


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
    tavily_api_key: str | None = None


_TYPE_ALIASES = {
    "hn_algolia": "hn",
    "hacker_news": "hn",
}


def _slugify(name: str) -> str:
    """Convert a source name to a URL-safe slug for use as an id."""
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _parse_source(raw: dict) -> Source:
    raw_type = raw.get("type", "rss")
    adapter_type = _TYPE_ALIASES.get(raw_type, raw_type)
    name = raw.get("name", "")
    source_id = raw.get("id") or _slugify(name) or "source"
    return Source(
        id=source_id,
        name=name,
        url=raw.get("url"),
        weight=raw.get("weight", 0.2),
        category=raw.get("category", "community"),
        type=adapter_type,
    )


def _resolve_preset(preset_name: str) -> list[Source]:
    """Load sources from a preset YAML file in the presets/ directory."""
    preset_path = (_PRESETS_DIR / f"{preset_name}.yaml").resolve()
    if not preset_path.is_relative_to(_PRESETS_DIR.resolve()):
        raise ValueError(f"Invalid preset name: {preset_name}")
    if not preset_path.exists():
        import sys
        print(f"herald: preset '{preset_name}' not found at {preset_path}", file=sys.stderr)
        return []
    with preset_path.open("r", encoding="utf-8") as f:
        preset_data = yaml.safe_load(f) or {}
    raw_sources = preset_data.get("sources") or preset_data.get("feeds") or []
    return [_parse_source(s) for s in raw_sources]


def load_config(path: Path) -> HeraldConfig:
    """Load config from a YAML file, merging any includes."""
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    config = _parse_config(data)

    # Resolve preset sources if a preset is specified and no explicit sources
    if not config.sources:
        preset_name = data.get("preset")
        if preset_name and preset_name != "blank":
            config.sources = _resolve_preset(preset_name)

    # Merge sources from included files
    for include_path in data.get("includes", []):
        resolved = Path(include_path).expanduser()
        if not resolved.is_absolute():
            resolved = path.parent / resolved
        if not resolved.is_file():
            import sys
            print(f"herald: includes: skipping {resolved} (not found)", file=sys.stderr)
            continue
        try:
            with resolved.open("r", encoding="utf-8") as f:
                inc_data = yaml.safe_load(f) or {}
            # Accept 'feeds' as alias for 'sources'
            raw = inc_data.get("sources") or inc_data.get("feeds") or []
            inc_sources = [_parse_source(s) for s in raw]
            # Dedupe by id — main config wins over includes
            existing_ids = {s.id for s in config.sources}
            for src in inc_sources:
                if src.id not in existing_ids:
                    config.sources.append(src)
                    existing_ids.add(src.id)
        except Exception as exc:
            import sys
            print(f"herald: includes: error loading {resolved}: {exc}", file=sys.stderr)

    return config


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
    tavily_api_key = data.get("tavily_api_key") or None

    return HeraldConfig(
        sources=sources,
        clustering=clustering,
        schedule=schedule,
        topics=topics,
        tavily_api_key=tavily_api_key,
    )
