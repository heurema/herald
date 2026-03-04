from __future__ import annotations

import math

from herald.scoring import article_score_base, story_score


def test_article_baseline():
    assert article_score_base(source_weight=0.3, points=0,
                               keyword_density=0.0, is_release=False) == 0.3


def test_article_points_cap():
    score = article_score_base(0.2, points=1500, keyword_density=0.0, is_release=False)
    assert score == 0.2 + 3.0


def test_article_points_partial():
    score = article_score_base(0.2, points=250, keyword_density=0.0, is_release=False)
    assert score == 0.2 + 0.5


def test_article_release_boost():
    score = article_score_base(0.2, 0, 0.0, is_release=True)
    assert score == 0.2 + 0.2


def test_article_density():
    score = article_score_base(0.2, 0, keyword_density=0.5, is_release=False)
    assert score == 0.2 + 0.5 * 0.2


def test_story_single_source():
    assert story_score(max_article_score=1.0, source_count=1, has_recent=False) == 1.0


def test_story_multi_source():
    expected = 1.0 + math.log(3) * 0.3
    assert abs(story_score(1.0, 3, False) - expected) < 0.001


def test_story_momentum():
    expected = 1.0 + 0.0 + 0.2
    assert story_score(1.0, 1, has_recent=True) == expected
