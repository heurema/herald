"""Scoring formulas for articles and stories."""
from __future__ import annotations

import math
import re
from urllib.parse import urlparse

# Matches arxiv paper IDs like 2603.12345 in URLs from arxiv.org and mirrors
_ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,6})")
_MIRROR_DOMAINS = frozenset({"arxiv.org", "tldr.takara.ai"})


def article_score_base(
    source_weight: float,
    points: int,
    keyword_density: float,
    is_release: bool,
) -> float:
    return (
        source_weight
        + min(points / 500, 3.0)
        + keyword_density * 0.2
        + (0.2 if is_release else 0.0)
    )


def story_score(
    max_article_score: float,
    source_count: int,
    has_recent: bool,
) -> float:
    coverage = math.log(max(source_count, 1)) * 0.3
    momentum = 0.2 if has_recent else 0.0
    return max_article_score + coverage + momentum


def _extract_paper_id(url: str) -> str | None:
    """Extract arxiv paper ID from URL if it belongs to a known mirror domain."""
    if not url:
        return None
    try:
        hostname = urlparse(url).hostname or ""
    except Exception:
        return None
    # Strip leading "www." for comparison
    hostname = hostname.removeprefix("www.")
    if hostname not in _MIRROR_DOMAINS:
        return None
    m = _ARXIV_ID_RE.search(url)
    return m.group(1) if m else None


def effective_source_count(sources_and_urls: list[tuple[str, str]]) -> int:
    """Count unique sources, collapsing mirrors that reference the same paper.

    Articles from different feeds that resolve to the same arxiv paper ID
    (e.g. arxiv.org and tldr.takara.ai) count as one source.
    """
    seen_paper_ids: dict[str, str] = {}  # paper_id -> first source_id
    effective: set[str] = set()

    for source_id, url in sources_and_urls:
        paper_id = _extract_paper_id(url)
        if paper_id is not None:
            if paper_id not in seen_paper_ids:
                seen_paper_ids[paper_id] = source_id
                effective.add(source_id)
            # else: mirror of already-counted paper — skip
        else:
            effective.add(source_id)

    return max(len(effective), 1)
