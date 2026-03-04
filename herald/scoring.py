"""Scoring formulas for articles and stories."""
from __future__ import annotations

import math


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
