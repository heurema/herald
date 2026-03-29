"""Topic extraction for herald v2 ingest pipeline."""
from __future__ import annotations


def _keywords_for(value: any) -> list[str]:
    """Normalize a topic value to a flat list of keyword strings.

    Accepts two shapes:
      - list[str]           — flat:   ai_agents: [agent, mcp]
      - dict with 'keywords' — nested: ai_agents: {keywords: [agent, mcp]}
    """
    if isinstance(value, list):
        return [str(kw) for kw in value]
    if isinstance(value, dict):
        kws = value.get("keywords", [])
        return [str(kw) for kw in kws] if isinstance(kws, list) else []
    return []


def extract_topics(title: str, topic_rules: dict[str, any]) -> list[str]:
    t = title.lower()
    matched = []
    for topic, value in topic_rules.items():
        keywords = _keywords_for(value)
        if any(kw.lower() in t for kw in keywords):
            matched.append(topic)
    return matched
