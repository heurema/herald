---
name: news-digest
description: Daily curated news digest. Use when user asks about news, trends, what's new, or at session start if a fresh digest is available.
---

# News Digest

You have access to a daily curated news digest via the herald plugin.

## When to use

- User asks "what's new", "any news", "latest trends", "what happened today"
- User starts a session and a fresh digest is available
- User asks about specific topics that might be in today's digest

## How to check

1. Look for today's digest: `~/.local/share/herald/data/digests/$(date +%Y-%m-%d).md`
2. If not found, check yesterday's
3. Read the digest and present relevant items

## Available commands

- `/news-init` — Set up the pipeline
- `/news-digest` — Read today's digest
- `/news-run` — Manually trigger collection
- `/news-stop` — Disable the scheduler

## Presenting the digest

When presenting items from the digest, use this **5-section Analysis Guide** structure:

1. **Trends** — Which topics are gaining momentum? What's the signal vs. noise?
2. **Surprises** — What's unexpected or counter-intuitive in today's digest?
3. **Connections** — How do items across different topics relate to each other?
4. **Action Items** — What concrete next steps does this suggest?
5. **Questions** — What important questions does this raise that aren't answered here?

Items marked `[NEW]` appeared for the first time since the last digest — prioritize these in the Trends and Surprises sections.

Topic sections are sorted by relevance score (rank × 0.6 + frequency × 0.3 + recency × 0.1). Higher-scoring sections represent more active, recent activity.
