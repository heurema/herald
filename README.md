# Herald

Daily curated news digest for your domain. One command to set up, zero API keys, works offline after first fetch.

A [Claude Code](https://docs.anthropic.com/en/docs/claude-code) plugin that delivers a daily filtered top-10 digest — zero cost, zero credentials, fully local.

## Install

```bash
claude plugin add heurema/herald
```

Then in Claude Code:

```
/news init
```

This runs preflight checks, creates a Python venv, installs dependencies, copies the default config, and sets up a daily scheduler.

## Commands

| Command | What it does |
|---------|-------------|
| `/news init` | Interactive setup wizard — pick preset, schedule time, verify |
| `/news digest` | Read today's digest, grouped by topic |
| `/news run` | Manually trigger collection + analysis |
| `/news stop` | Disable scheduler, show cleanup options |

## How It Works

```
Daily: scheduler → run.sh → collect.py → analyze.py → digest.md
                                ↓
                  20 RSS feeds + HN Algolia API
                                ↓
                  dedup → keyword filter → signal scoring → top 10
```

1. **Collect**: Fetches RSS feeds and HN front-page stories via public APIs
2. **Dedup**: 3-layer deduplication (URL hash, normalization, title similarity)
3. **Filter**: Keyword matching against your configured topics
4. **Score**: Signal scoring based on source weight, points, keyword density, recency
5. **Digest**: Top 10 items as a Markdown file, grouped by topic

## Configuration

Config lives at `~/.config/herald/config.yaml`. It layers your overrides on top of a preset:

```yaml
version: 1
preset: "ai-engineering"    # base preset
schedule_time: "06:00"
timezone: "local"
max_items: 10

# Add your own feeds
add_feeds:
  - name: "My Blog"
    url: "https://myblog.com/feed"
    tier: 1
    weight: 0.25

# Remove preset feeds you don't want
remove_feeds:
  - "r/MachineLearning"

# Add keyword topics
add_keywords:
  devops:
    - "kubernetes"
    - "terraform"

# Remove keyword topics
remove_keywords:
  - ai_finance
```

### Blank preset

Start from scratch with `--blank`:

```
/news init --preset blank --time 08:00
```

Then add your own feeds and keywords in the config file.

## Presets

### AI Engineering (default)

20 curated feeds across 5 tiers:

- **Tier 1** (daily): HN, Simon Willison, AlphaSignal, HF Papers, arXiv cs.AI, GitHub Trending
- **Tier 2** (weekly): Import AI, Last Week in AI, Ahead of AI, Latent Space, Practical AI
- **Tier 3** (releases): Claude Code, OpenAI Agents SDK, LangChain, CrewAI
- **Tier 4** (finance): arXiv q-fin, r/algotrading, ML-Quant
- **Tier 5** (community): r/LocalLLaMA, r/MachineLearning

5 keyword categories: ai_agents, ai_coding, ai_finance, ai_models, ai_engineering

## Data

All data is local:

```
~/.config/herald/          # config
~/.local/share/herald/     # data + venv
├── .venv/
└── data/
    ├── raw/YYYY-MM-DD.jsonl    # raw items (90-day retention)
    ├── digests/YYYY-MM-DD.md   # daily digests (365-day retention)
    └── state/
        ├── seen_urls.txt       # dedup index (90-day retention)
        ├── last_run.json       # run metadata
        └── collect.log         # run log
```

## Privacy

- Fetches only RSS feeds and the public HN Algolia API
- All data stays local on your machine
- No paid API keys required
- Optional: Tavily search (free tier key, not required)

## Requirements

- Python 3.10+
- macOS or Linux (Windows via WSL)
- Claude Code

## Uninstall

```
/news stop
rm -rf ~/.local/share/herald/
rm -rf ~/.config/herald/
```

## See Also

Other [heurema](https://github.com/heurema) projects:

- **[sigil](https://github.com/heurema/sigil)** — risk-adaptive development pipeline with adversarial code review
- **[teams-field-guide](https://github.com/heurema/teams-field-guide)** — comprehensive guide to Claude Code multi-agent teams
- **[codex-partner](https://github.com/heurema/codex-partner)** — using Codex CLI as second AI alongside Claude Code
- **[proofpack](https://github.com/heurema/proofpack)** — proof-carrying CI gate for AI agent changes

## License

MIT
