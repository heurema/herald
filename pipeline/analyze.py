"""Analysis pipeline: keyword filtering, signal scoring, digest generation."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Text sanitization
# ---------------------------------------------------------------------------

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b-\x1f]")


def sanitize_text(text: str) -> str:
    """Strip control chars (\\x00-\\x1f except \\n), truncate to 500 chars."""
    cleaned = _CONTROL_CHAR_RE.sub("", text)
    return cleaned[:500]


# ---------------------------------------------------------------------------
# Keyword matching
# ---------------------------------------------------------------------------

def keyword_match(text: str, keywords: dict[str, list[str]]) -> set[str]:
    """Return set of topic category names that match in text (case-insensitive).

    Multi-word phrases are matched first and their text is masked so that
    constituent single words no longer trigger standalone matches.
    Single-word keywords use whole-word (\\b) boundary matching.
    Multi-word phrases use substring matching.
    """
    text_lower = text.lower()

    # First pass: collect all multi-word phrase matches and mask consumed text
    masked = text_lower
    for kw_list in keywords.values():
        for kw in kw_list:
            if " " in kw and kw in masked:
                # Replace the phrase with underscores so constituent words won't match
                masked = masked.replace(kw, "_" * len(kw))

    matched: set[str] = set()
    for topic, kw_list in keywords.items():
        for kw in kw_list:
            kw_lower = kw.lower()
            if " " in kw_lower:
                # Phrase — check original text
                if kw_lower in text_lower:
                    matched.add(topic)
                    break
            else:
                # Single word — whole-word match against masked text
                pattern = r"\b" + re.escape(kw_lower) + r"\b"
                if re.search(pattern, masked):
                    matched.add(topic)
                    break

    return matched


# ---------------------------------------------------------------------------
# Keyword density
# ---------------------------------------------------------------------------

def keyword_density(text: str, keywords: dict[str, list[str]]) -> float:
    """Return total keyword hits / word count. 0.0 if no words or no matches."""
    words = text.lower().split()
    if not words:
        return 0.0

    text_lower = text.lower()
    hits = 0
    for kw_list in keywords.values():
        for kw in kw_list:
            kw_lower = kw.lower()
            if " " in kw_lower:
                if kw_lower in text_lower:
                    hits += 1
            else:
                pattern = r"\b" + re.escape(kw_lower) + r"\b"
                if re.search(pattern, text_lower):
                    hits += 1

    return hits / len(words)


# ---------------------------------------------------------------------------
# Signal scoring
# ---------------------------------------------------------------------------

def signal_score(item: dict, source_weights: dict[str, float]) -> float:
    """Compute signal score from source weight, points, keyword density, release flag, age."""
    score = (
        source_weights.get(item["source"], 0.1)
        + min(item.get("extra", {}).get("points", 0) / 500, 0.3)
        + item.get("keyword_density", 0) * 0.2
        + (0.2 if item.get("is_release") else 0)
        - item.get("hours_old", 0) * 0.005
    )
    return score


# ---------------------------------------------------------------------------
# Hard cap
# ---------------------------------------------------------------------------

def apply_hard_cap(items: list[dict], max_items: int = 10) -> list[dict]:
    """Sort by score descending, return top max_items."""
    return sorted(items, key=lambda x: x.get("score", 0), reverse=True)[:max_items]


# ---------------------------------------------------------------------------
# Digest generation
# ---------------------------------------------------------------------------

def generate_digest(items: list[dict], date: str, stats: dict) -> str:
    """Generate a Markdown digest grouped by first topic."""
    lines: list[str] = []

    lines.append(f"# News Digest — {date}")
    lines.append("")
    collected = stats.get("collected", 0)
    filtered = stats.get("filtered", 0)
    kept = stats.get("kept", 0)
    cost = stats.get("cost", 0.0)
    lines.append(
        f"_Collected: {collected} | Filtered: {filtered} | Kept: {kept} | Cost: ${cost:.4f}_"
    )
    lines.append("")

    # Group by first topic
    grouped: dict[str, list[dict]] = {}
    for item in items:
        topics = item.get("topics") or []
        topic = topics[0] if topics else "uncategorized"
        grouped.setdefault(topic, []).append(item)

    for topic, topic_items in grouped.items():
        lines.append(f"## {topic.replace('_', ' ').title()}")
        lines.append("")
        for idx, item in enumerate(topic_items, 1):
            title = item.get("title", "Untitled")
            url = item.get("url", "")
            score = item.get("score", 0)
            summary = item.get("summary", "")
            source = item.get("source", "")
            lines.append(f"{idx}. [{title}]({url})  ")
            lines.append(f"   Score: {score:.1f} | Source: {source}")
            if summary:
                lines.append(f"   {summary}")
            lines.append("")

    lines.append("---")
    lines.append("_Generated by claude-news_")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Hours-old helper
# ---------------------------------------------------------------------------

def _hours_old(item: dict) -> float:
    """Compute hours between item timestamp and now."""
    now = datetime.now(timezone.utc)
    ts_str = item.get("published") or item.get("collected_at") or ""
    if not ts_str:
        return 0.0
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = now - dt
        return max(delta.total_seconds() / 3600, 0.0)
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entrypoint for the analysis pipeline."""
    parser = argparse.ArgumentParser(description="Analyze and score collected news items.")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    parser.add_argument("--input", default=None, help="Input raw JSONL path")
    parser.add_argument("--output", default=None, help="Output digest path")
    parser.add_argument("--state-dir", default=None, help="State directory for seen_urls.txt")
    args = parser.parse_args()

    # Resolve config: if --config points to a config.yaml with preset field, use overlay
    if args.config:
        import yaml  # type: ignore
        with open(args.config, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if "preset" in raw or "add_feeds" in raw:
            from pipeline.config import resolve_config
            config = resolve_config(user_config_path=Path(args.config))
        else:
            config = raw
    else:
        from pipeline.config import resolve_config
        config = resolve_config()

    keywords: dict[str, list[str]] = config.get("keywords", {})
    scoring_cfg: dict = config.get("scoring", {})
    source_weights: dict[str, float] = {
        feed["name"]: feed.get("weight", 0.1)
        for feed in config.get("feeds", [])
    }
    max_items: int = scoring_cfg.get("max_items", 10)

    # Resolve paths with XDG defaults
    if args.input:
        input_path = Path(args.input)
    else:
        from pipeline.paths import raw_dir
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        input_path = raw_dir() / f"{today}.jsonl"

    if args.state_dir:
        state_dir_path = Path(args.state_dir)
    else:
        from pipeline.paths import state_dir as _state_dir
        state_dir_path = _state_dir()

    # Load raw items
    raw_items: list[dict] = []
    if input_path.exists():
        with input_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        raw_items.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    total_collected = len(raw_items)

    # Load SeenUrls
    from pipeline.dedup import SeenUrls, dedup_items
    from pipeline.collect import RawItem

    seen_path = state_dir_path / "seen_urls.txt"
    seen = SeenUrls(seen_path, max_age_days=config.get("retention", {}).get("seen_urls_days", 90))

    # Convert raw dicts to RawItem for dedup
    raw_item_objs = [
        RawItem(
            url=d.get("url", ""),
            title=d.get("title", ""),
            source=d.get("source", ""),
            published=d.get("published", ""),
            extra=d.get("extra", {}),
            collected_at=d.get("collected_at", ""),
        )
        for d in raw_items
    ]

    # Stage 1: Dedup
    deduped = dedup_items(raw_item_objs, seen)

    # Stage 2: Keyword filter — drop items with no matching topic
    filtered: list[dict] = []
    for item_obj in deduped:
        topics = keyword_match(item_obj.title, keywords)
        if not topics:
            continue
        d = item_obj.to_dict()
        d["topics"] = sorted(topics)
        filtered.append(d)

    total_filtered = len(filtered)

    # Stage 3: Signal scoring
    scored: list[dict] = []
    for item in filtered:
        item["hours_old"] = _hours_old(item)
        item["is_release"] = item.get("extra", {}).get("is_release", False)
        item["keyword_density"] = keyword_density(item.get("title", ""), keywords)
        item["score"] = signal_score(item, source_weights)
        scored.append(item)

    # Stage 4: Sort by signal score (Haiku classification removed — no API cost)
    pre_sorted = sorted(scored, key=lambda x: x.get("score", 0), reverse=True)

    # Stage 5: Hard cap
    final = apply_hard_cap(pre_sorted, max_items=max_items)
    kept = len(final)

    estimated_cost = 0.0

    stats = {
        "collected": total_collected,
        "filtered": total_filtered,
        "kept": kept,
        "cost": estimated_cost,
    }

    # Generate digest
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    digest = generate_digest(final, today, stats)

    # Atomic write
    if args.output:
        output_path = Path(args.output)
    else:
        from pipeline.paths import digests_dir
        output_path = digests_dir() / f"{today}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=output_path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(digest)
        os.rename(tmp_path, output_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    # Save seen_urls
    seen.save()

    # Print stats
    print(f"[analyze] Collected: {total_collected} | Deduped → Keyword filtered: {total_filtered} | Kept: {kept}")
    print(f"[analyze] Digest written to {output_path}")
    print(f"[analyze] Scoring: signal-based (no API cost)")


if __name__ == "__main__":
    main()
