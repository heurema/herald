"""Tests for pipeline/topics.py."""


def test_parse_rules_plain_words():
    from pipeline.topics import parse_rules
    rules = parse_rules(["agent", "mcp"])
    assert len(rules) == 2
    assert all(not r.is_regex for r in rules)
    assert rules[0].pattern == "agent"
    assert rules[1].pattern == "mcp"


def test_parse_rules_regex():
    from pipeline.topics import parse_rules
    rules = parse_rules(["/^release\\s+v\\d/"])
    assert len(rules) == 1
    assert rules[0].is_regex is True
    assert rules[0].compiled is not None


def test_parse_rules_mixed():
    from pipeline.topics import parse_rules
    rules = parse_rules(["agent", "/mcp.*/"])
    assert len(rules) == 2
    assert rules[0].is_regex is False
    assert rules[1].is_regex is True


def test_parse_rules_empty_list():
    from pipeline.topics import parse_rules
    assert parse_rules([]) == []


def test_parse_rules_invalid_regex():
    from pipeline.topics import parse_rules
    rules = parse_rules(["/[unclosed/"])
    assert len(rules) == 1
    assert rules[0].is_regex is True
    assert rules[0].compiled is None


def test_parse_rules_too_long_regex():
    from pipeline.topics import parse_rules
    import warnings
    long_pattern = "/" + "a" * 201 + "/"
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        rules = parse_rules([long_pattern])
    assert len(rules) == 1
    assert rules[0].is_regex is True
    assert rules[0].compiled is None
    assert any("ReDoS" in str(warning.message) for warning in w)


# match_topic_group tests
def test_match_group_normal_hit():
    from pipeline.topics import parse_rules, TopicGroup, match_topic_group
    group = TopicGroup(name="ai", normal=parse_rules(["agent"]))
    assert match_topic_group("New AI agent released", group) is True


def test_match_group_normal_miss():
    from pipeline.topics import parse_rules, TopicGroup, match_topic_group
    group = TopicGroup(name="ai", normal=parse_rules(["agent"]))
    assert match_topic_group("Nothing relevant here", group) is False


def test_match_group_required_hit():
    from pipeline.topics import parse_rules, TopicGroup, match_topic_group
    group = TopicGroup(name="ai", required=parse_rules(["llm"]), normal=parse_rules(["agent"]))
    # required is non-empty, any required matches -> True
    assert match_topic_group("LLM agent for production", group) is True


def test_match_group_required_miss():
    from pipeline.topics import parse_rules, TopicGroup, match_topic_group
    group = TopicGroup(name="ai", required=parse_rules(["llm"]), normal=parse_rules(["agent"]))
    # has required, but text doesn't have required word -> False
    assert match_topic_group("agent deployed successfully", group) is False


def test_match_group_filter_blocks():
    from pipeline.topics import parse_rules, TopicGroup, match_topic_group
    group = TopicGroup(name="ai", normal=parse_rules(["agent"]), filter=parse_rules(["hiring"]))
    assert match_topic_group("AI agent hiring now", group) is False


def test_match_group_regex_match():
    from pipeline.topics import parse_rules, TopicGroup, match_topic_group
    group = TopicGroup(name="releases", normal=parse_rules(["/release\\s+v\\d/"]))
    assert match_topic_group("release v2 is out", group) is True


def test_match_group_empty_group():
    from pipeline.topics import TopicGroup, match_topic_group
    group = TopicGroup(name="empty")
    assert match_topic_group("anything", group) is False


# match_topics tests
def test_match_topics_multi_group():
    from pipeline.topics import parse_rules, TopicGroup, match_topics
    groups = [
        TopicGroup(name="ai", normal=parse_rules(["agent"])),
        TopicGroup(name="cloud", normal=parse_rules(["kubernetes"])),
        TopicGroup(name="finance", normal=parse_rules(["stock"])),
    ]
    result = match_topics("New AI agent on kubernetes", groups)
    assert result == {"ai", "cloud"}


def test_match_topics_none_match():
    from pipeline.topics import parse_rules, TopicGroup, match_topics
    groups = [TopicGroup(name="ai", normal=parse_rules(["agent"]))]
    assert match_topics("Nothing here", groups) == set()


# parse_topic_config tests
def test_parse_config_flat_list():
    from pipeline.topics import parse_topic_config
    groups = parse_topic_config({"ai": ["agent", "mcp"]})
    assert len(groups) == 1
    assert groups[0].name == "ai"
    assert len(groups[0].normal) == 2
    assert len(groups[0].required) == 0
    assert len(groups[0].filter) == 0


def test_parse_config_dict_format():
    from pipeline.topics import parse_topic_config
    groups = parse_topic_config({"ai": {"required": ["agent"], "normal": ["mcp"], "filter": ["hiring"]}})
    assert len(groups) == 1
    g = groups[0]
    assert len(g.required) == 1
    assert len(g.normal) == 1
    assert len(g.filter) == 1


def test_parse_config_mixed():
    from pipeline.topics import parse_topic_config
    groups = parse_topic_config({
        "ai": ["agent", "mcp"],
        "cloud": {"required": ["kubernetes"], "normal": ["docker"]},
    })
    assert len(groups) == 2
    names = {g.name for g in groups}
    assert names == {"ai", "cloud"}


def test_parse_config_invalid_type_skipped():
    from pipeline.topics import parse_topic_config
    import warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        groups = parse_topic_config({"bad": 42, "good": ["agent"]})
    assert len(groups) == 1
    assert groups[0].name == "good"
    assert any("bad" in str(warning.message) for warning in w)


# topic_score tests
def test_topic_score_all_high():
    from pipeline.topics import topic_score
    assert abs(topic_score(1.0, 1.0, 1.0) - 1.0) < 1e-9


def test_topic_score_all_zero():
    from pipeline.topics import topic_score
    assert topic_score(0.0, 0.0, 0.0) == 0.0


def test_topic_score_weights():
    from pipeline.topics import topic_score
    # rank dominates: rank=1.0, freq=0, hotness=0 -> 0.6
    assert abs(topic_score(1.0, 0.0, 0.0) - 0.6) < 1e-9


# hours_old tests
def test_hours_old_published_field():
    from pipeline.topics import hours_old
    from datetime import datetime, timezone, timedelta
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    item = {"published": one_hour_ago}
    result = hours_old(item)
    assert 0.9 < result < 1.1


def test_hours_old_fallback_to_collected_at():
    from pipeline.topics import hours_old
    from datetime import datetime, timezone, timedelta
    two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    item = {"collected_at": two_hours_ago}
    result = hours_old(item)
    assert 1.9 < result < 2.1


def test_hours_old_naive_timestamp_assumed_utc():
    from pipeline.topics import hours_old
    from datetime import datetime, timezone, timedelta
    # Naive timestamp (no tzinfo) should be treated as UTC
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(tzinfo=None).isoformat()
    item = {"published": one_hour_ago}
    result = hours_old(item)
    assert 0.9 < result < 1.1


def test_hours_old_missing_fields():
    from pipeline.topics import hours_old
    assert hours_old({}) == 0.0


def test_hours_old_bad_value():
    from pipeline.topics import hours_old
    assert hours_old({"published": "not-a-date"}) == 0.0


def test_hours_old_future_timestamp_clamped():
    from pipeline.topics import hours_old
    from datetime import datetime, timezone, timedelta
    future = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()
    item = {"published": future}
    result = hours_old(item)
    assert result == 0.0
