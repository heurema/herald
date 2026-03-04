"""Topic rule-engine and scoring for the TrendRadar pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
import warnings

_MAX_REGEX_LEN = 200


@dataclass
class Rule:
    pattern: str
    is_regex: bool
    compiled: re.Pattern | None  # None if regex compile failed


@dataclass
class TopicGroup:
    name: str
    required: list[Rule] = field(default_factory=list)
    normal: list[Rule] = field(default_factory=list)
    filter: list[Rule] = field(default_factory=list)


def parse_rules(words: list[str]) -> list[Rule]:
    """Parse a list of keyword or regex strings into Rule objects.

    Strings that start and end with '/' are treated as regex patterns.
    Plain strings are case-insensitive substring matches.
    """
    rules: list[Rule] = []
    for word in words:
        if word.startswith("/") and word.endswith("/") and len(word) > 2:
            pattern = word[1:-1]
            if len(pattern) > _MAX_REGEX_LEN:
                warnings.warn(
                    f"regex pattern too long (ReDoS risk): {word!r}",
                    stacklevel=2,
                )
                rules.append(Rule(pattern=pattern, is_regex=True, compiled=None))
            else:
                try:
                    compiled = re.compile(pattern, re.IGNORECASE)
                    rules.append(Rule(pattern=pattern, is_regex=True, compiled=compiled))
                except re.error:
                    warnings.warn(
                        f"invalid regex pattern (compile failed): {word!r}",
                        stacklevel=2,
                    )
                    rules.append(Rule(pattern=pattern, is_regex=True, compiled=None))
        else:
            rules.append(Rule(pattern=word, is_regex=False, compiled=None))
    return rules


def _match_rule(text: str, rule: Rule) -> bool:
    """Return True if *text* matches *rule* (case-insensitive)."""
    if rule.is_regex:
        if rule.compiled is None:
            return False
        return bool(rule.compiled.search(text))
    return rule.pattern.lower() in text.lower()


def match_topic_group(text: str, group: TopicGroup) -> bool:
    """Return True if *text* belongs to *group* per the rule contract.

    Logic:
    - Empty group (no required, normal, filter) -> False
    - If any filter rule matches -> False
    - If required is non-empty: return True iff any required rule matches
    - If required is empty: return True iff any normal rule matches
    """
    if not group.required and not group.normal and not group.filter:
        return False

    # Filter blocks unconditionally
    if any(_match_rule(text, r) for r in group.filter):
        return False

    if group.required:
        return any(_match_rule(text, r) for r in group.required)
    else:
        return any(_match_rule(text, r) for r in group.normal)


def match_topics(text: str, groups: list[TopicGroup]) -> set[str]:
    """Return set of group names where match_topic_group returns True."""
    return {g.name for g in groups if match_topic_group(text, g)}


def parse_topic_config(keywords: dict) -> list[TopicGroup]:
    """Build a list of TopicGroup objects from a keywords config dict.

    Each value can be:
    - list[str]: treated as {"normal": value}
    - dict: may contain "required", "normal", "filter" keys (all optional)
    - anything else: emits a warning and is skipped
    """
    groups: list[TopicGroup] = []
    for topic_name, value in keywords.items():
        if isinstance(value, list):
            groups.append(TopicGroup(
                name=topic_name,
                normal=parse_rules(value),
            ))
        elif isinstance(value, dict):
            required = parse_rules(value.get("required") or [])
            normal = parse_rules(value.get("normal") or [])
            filter_ = parse_rules(value.get("filter") or [])
            groups.append(TopicGroup(
                name=topic_name,
                required=required,
                normal=normal,
                filter=filter_,
            ))
        else:
            warnings.warn(
                f"Skipping topic {topic_name!r}: unexpected type {type(value)}, expected list or dict",
                stacklevel=2,
            )
    return groups


def topic_score(rank: float, freq: float, hotness: float) -> float:
    """Weighted topic score: rank*0.6 + freq*0.3 + hotness*0.1."""
    return rank * 0.6 + freq * 0.3 + hotness * 0.1


def hours_old(item: dict) -> float:
    """Return how many hours old *item* is based on 'published' or 'collected_at'.

    Returns 0.0 on any error (missing field, parse failure, future timestamp).
    """
    now_utc = datetime.now(timezone.utc)
    for field_name in ("published", "collected_at"):
        raw = item.get(field_name)
        if not raw:
            continue
        try:
            ts = datetime.fromisoformat(str(raw))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            delta = (now_utc - ts).total_seconds() / 3600
            return max(0.0, delta)
        except (ValueError, TypeError):
            continue
    return 0.0
