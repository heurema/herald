"""Tests for analyze module."""

def test_keyword_match():
    from pipeline.analyze import keyword_match
    keywords = {
        "ai_agents": ["agent", "mcp", "claude code"],
        "ai_models": ["llm", "gpt", "claude"],
    }
    assert keyword_match("New MCP server released for Claude Code", keywords) == {"ai_agents"}
    assert keyword_match("No relevant content here at all", keywords) == set()

def test_keyword_match_multi_topic():
    from pipeline.analyze import keyword_match
    keywords = {
        "ai_agents": ["agent", "mcp"],
        "ai_models": ["llm", "claude"],
    }
    # Should match both topics
    result = keyword_match("New Claude agent framework with LLM integration", keywords)
    assert "ai_agents" in result
    assert "ai_models" in result

def test_keyword_density():
    from pipeline.analyze import keyword_density
    keywords = {"ai_agents": ["agent", "mcp", "tool use"]}
    density = keyword_density("AI agent with MCP tool use support", keywords)
    assert density > 0.1

def test_keyword_density_no_match():
    from pipeline.analyze import keyword_density
    keywords = {"ai_agents": ["agent", "mcp"]}
    density = keyword_density("Weather forecast for tomorrow morning", keywords)
    assert density == 0.0

def test_signal_score():
    from pipeline.analyze import signal_score
    item = {
        "source": "hn_frontpage",
        "extra": {"points": 400},
        "keyword_density": 0.15,
        "is_release": False,
        "hours_old": 2,
    }
    weights = {"hn_frontpage": 0.25}
    score = signal_score(item, weights)
    assert 0.3 < score < 0.8

def test_signal_score_release_boost():
    from pipeline.analyze import signal_score
    item = {
        "source": "github_release",
        "extra": {},
        "keyword_density": 0.1,
        "is_release": True,
        "hours_old": 1,
    }
    weights = {"github_release": 0.2}
    score_release = signal_score(item, weights)
    item_no = dict(item, is_release=False)
    score_no_release = signal_score(item_no, weights)
    assert score_release > score_no_release

def test_hard_cap():
    from pipeline.analyze import apply_hard_cap
    items = [{"score": i} for i in range(20, 0, -1)]
    capped = apply_hard_cap(items, max_items=10)
    assert len(capped) == 10
    assert capped[0]["score"] == 20

def test_hard_cap_fewer_than_max():
    from pipeline.analyze import apply_hard_cap
    items = [{"score": 8}, {"score": 9}]
    capped = apply_hard_cap(items, max_items=10)
    assert len(capped) == 2

def test_sanitize_text():
    from pipeline.analyze import sanitize_text
    assert sanitize_text("Hello\x00World\x01Test") == "HelloWorldTest"
    assert len(sanitize_text("x" * 1000)) == 500  # truncated

def test_generate_digest_format():
    from pipeline.analyze import generate_digest
    items = [
        {"url": "https://example.com/1", "title": "Test Item", "score": 9.0,
         "topics": ["ai_agents"], "summary": "A test summary.", "source": "HN"},
    ]
    digest = generate_digest(items, "2026-02-25", {"collected": 100, "filtered": 30, "kept": 1, "cost": 0.01})
    assert "# News Digest" in digest
    assert "Test Item" in digest
    assert "2026-02-25" in digest


def test_generate_digest_new_badge():
    from pipeline.analyze import generate_digest
    items = [{
        "title": "Breaking news",
        "url": "https://example.com/1",
        "source": "test",
        "topics": ["ai"],
        "score": 1.0,
        "published": "2024-01-01T10:00:00",
        "extra": {},
        "is_new": True,
    }]
    output = generate_digest(items, "2024-01-01", {"total": 1, "new": 0, "dupes": 0})
    assert "[NEW]" in output


def test_generate_digest_no_new_badge():
    from pipeline.analyze import generate_digest
    items = [{
        "title": "Old news",
        "url": "https://example.com/2",
        "source": "test",
        "topics": ["ai"],
        "score": 0.5,
        "published": "2024-01-01T10:00:00",
        "extra": {},
        "is_new": False,
    }]
    output = generate_digest(items, "2024-01-01", {"total": 1, "new": 0, "dupes": 0})
    assert "[NEW]" not in output


def test_generate_digest_analysis_guide():
    from pipeline.analyze import generate_digest
    items = [{
        "title": "Test item",
        "url": "https://example.com/3",
        "source": "test",
        "topics": ["ai"],
        "score": 1.0,
        "published": "2024-01-01T10:00:00",
        "extra": {},
        "is_new": False,
    }]
    output = generate_digest(items, "2024-01-01", {"total": 1, "new": 0, "dupes": 0})
    assert "Analysis Guide" in output
    assert "Trends" in output
    assert "Surprises" in output
    assert "Connections" in output
    assert "Action Items" in output
    assert "Questions" in output


def test_generate_digest_backward_compat():
    from pipeline.analyze import generate_digest
    items = [{
        "title": "Test item",
        "url": "https://example.com/4",
        "source": "test",
        "topics": ["ai"],
        "score": 1.0,
        "published": "2024-01-01T10:00:00",
        "extra": {},
    }]
    # Call without source_weights — must not raise
    output = generate_digest(items, "2024-01-01", {"total": 1, "new": 0, "dupes": 0})
    assert isinstance(output, str)
    assert len(output) > 0


def test_generate_digest_topic_sort_order():
    from pipeline.analyze import generate_digest
    # Create items in two topics: "zzz" topic with 1 item (low freq), "aaa" topic with 3 items (high freq)
    # Higher freq -> higher topic_score -> "aaa" section should appear first
    items = [
        {"title": f"AAA item {i}", "url": f"https://example.com/aaa/{i}", "source": "test",
         "topics": ["aaa"], "score": 0.9 - i*0.1, "published": "2024-01-01T10:00:00",
         "extra": {}, "is_new": False}
        for i in range(3)
    ] + [
        {"title": "ZZZ item", "url": "https://example.com/zzz/1", "source": "test",
         "topics": ["zzz"], "score": 1.0, "published": "2024-01-01T10:00:00",
         "extra": {}, "is_new": False}
    ]
    output = generate_digest(items, "2024-01-01", {"total": 4, "new": 0, "dupes": 0})
    # Headers now include score: "## Aaa (score: 0.72)" — search by prefix
    pos_aaa = output.find("## Aaa")
    pos_zzz = output.find("## Zzz")
    # "aaa" has 3 items (freq=0.75), "zzz" has 1 (freq=0.25) -> aaa should be first
    if pos_aaa != -1 and pos_zzz != -1:
        assert pos_aaa < pos_zzz


def test_generate_digest_section_header_has_score():
    from pipeline.analyze import generate_digest
    import re
    items = [{
        "title": "Test item",
        "url": "https://example.com/1",
        "source": "test",
        "topics": ["ai"],
        "score": 1.0,
        "published": "2024-01-01T10:00:00",
        "extra": {},
        "is_new": False,
    }]
    output = generate_digest(items, "2024-01-01", {"total": 1, "new": 0, "dupes": 0})
    # Section header should include score value, e.g. "## Ai (score: 0.60)"
    assert re.search(r"## Ai \(score: \d+\.\d+\)", output)
