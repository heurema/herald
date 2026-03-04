# Herald

<div align="center">

**Local-first news intelligence for AI agents**

![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-Plugin-5b21b6?style=flat-square)
![Version](https://img.shields.io/badge/version-2.0.0-5b21b6?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-5b21b6?style=flat-square)

```bash
claude plugin marketplace add heurema/emporium
claude plugin install herald@emporium
```

</div>

## What it does

Herald collects articles from RSS feeds and Hacker News, deduplicates by URL, clusters related articles into stories using title similarity, scores them by source weight and recency, and generates a ranked Markdown digest — all locally, no API keys, no cloud.

The pipeline: **collect → ingest → cluster → project**.

```
RSS/Atom feeds ─┐
                 ├─→ articles ─→ stories (clustered) ─→ scored brief
HN Algolia API ─┘
```

## Install

<!-- INSTALL:START — auto-synced from emporium/INSTALL_REFERENCE.md -->
```bash
claude plugin marketplace add heurema/emporium
claude plugin install herald@emporium
```
<!-- INSTALL:END -->

<details>
<summary>Manual install from source</summary>

```bash
git clone https://github.com/heurema/herald
cd herald
pip install httpx fastfeedparser pyyaml
```

Then symlink or copy the plugin directory into Claude Code's plugin path and run `/news-init`.

</details>

## Quick start

```
/news-init          # creates ~/.herald/ with config and database
/news-add <url>     # add an RSS feed
/news-run           # collect, ingest, cluster, generate brief
/news-digest        # read the latest brief
```

## Commands

| Command | What it does |
|---------|-------------|
| `/news-init` | Create data directory, config template, and database |
| `/news-add <url>` | Add an RSS/Atom feed — auto-discovers feed URL |
| `/news-sources` | View all sources grouped by category |
| `/news-sources remove <name>` | Remove a source from config |
| `/news-run` | Run the full pipeline manually |
| `/news-digest` | Read the latest brief with 5-section analysis |
| `/news-status` | Show article/story counts and last run time |
| `/news-stop` | Show cleanup options |

## Architecture

Herald v2 uses a 4-stage pipeline with SQLite storage:

1. **Collect** — fetches RSS/Atom feeds and HN front-page stories via public APIs. Optional Tavily adapter for web search.
2. **Ingest** — UPSERT articles with URL canonicalization, deduplication, topic assignment, and cross-source mention tracking.
3. **Cluster** — groups related articles into stories using `SequenceMatcher` title similarity with 4 merge guards (threshold, time gap, title length, version/number conflict). Canonical article re-election with hysteresis.
4. **Project** — generates a Markdown brief with YAML frontmatter, stories grouped by type (release, research, tutorial, opinion, news), scored and ranked.

### Data model

```
sources → articles → mentions (cross-source)
                  → article_topics
                  → story_articles → stories → story_topics
```

### Scoring

- **Article score**: `source_weight + min(points/500, 3.0) + keyword_density * 0.2 + release_boost`
- **Story score**: `max(article_scores) + log(source_count) * 0.3 + momentum`

## Configuration

Config: `~/.herald/config.yaml`

```yaml
sources:
  - id: hn
    name: Hacker News
    type: hn           # hn | rss | tavily
    weight: 0.3
    category: community
  - id: simonw
    name: Simon Willison
    type: rss
    url: https://simonwillison.net/atom/everything/
    weight: 0.25
    category: community

topics:
  ai_agents:
    keywords: [agent, agents, agentic, tool use, mcp]
  ai_models:
    keywords: [claude, gpt, gemini, llama, llm]

clustering:
  threshold: 0.65        # title similarity threshold
  max_time_gap_days: 7   # max days between clustered articles

schedule:
  interval_hours: 4
```

### Data paths

```
~/.herald/
├── config.yaml
├── herald.db           # SQLite database
└── briefs/
    └── {run_id}.md     # generated briefs
```

## Requirements

- Python 3.12+
- `httpx`, `fastfeedparser`, `pyyaml`
- macOS or Linux
- Claude Code

## Privacy

Herald fetches only public RSS feeds and the HN Algolia API. All data stays on your machine under `~/.herald/`. No telemetry, no cloud sync. Optional Tavily adapter requires a free API key but is not needed for core functionality.

## Feedback

Found a bug? All heurema plugins ship with [Reporter](https://github.com/heurema/reporter) - file issues without leaving Claude Code:

```bash
claude plugin install reporter@emporium
/report bug
```

## See also

- [Herald v2: Local-First News Intelligence for AI Agents](https://ctxt.dev/posts/en/herald-v2-local-news-intelligence) - blog post with architecture deep-dive
- [emporium](https://github.com/heurema/emporium) - plugin marketplace
- [signum](https://github.com/heurema/signum) - contract-first AI dev pipeline
- [reporter](https://github.com/heurema/reporter) - issue filing from Claude Code

## License

[MIT](LICENSE)
