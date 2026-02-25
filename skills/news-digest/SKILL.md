---
name: news-digest
description: Daily curated news digest. Use when user asks about news, trends, what's new, or at session start if a fresh digest is available.
---

# News Digest

You have access to a daily curated news digest via the claude-news plugin.

## When to use

- User asks "what's new", "any news", "latest trends", "what happened today"
- User starts a session and a fresh digest is available
- User asks about specific topics that might be in today's digest

## How to check

1. Look for today's digest: `~/.local/share/claude-news/data/digests/$(date +%Y-%m-%d).md`
2. If not found, check yesterday's
3. Read the digest and present relevant items

## Available commands

- `/news init` — Set up the pipeline
- `/news digest` — Read today's digest
- `/news run` — Manually trigger collection
- `/news stop` — Disable the scheduler
