---
name: news-init
description: Set up herald daily digest pipeline
allowed-tools: Bash, Read, Write, Edit
---

You are setting up the herald v2 daily news digest pipeline.

## Steps

1. **Check if already set up**: Find the herald data directory by running:
   ```bash
   cd "${CLAUDE_PLUGIN_ROOT}" && PYTHONPATH=. python3 -c "from herald.cli import _default_data_dir; print(_default_data_dir())"
   ```
   Check if `config.yaml` exists in that directory (defaults to `~/.local/share/herald/`; falls back to `~/.herald/` for legacy installs; override with `--data-dir` or `HERALD_DATA_DIR`).
   - If it exists: tell user setup is done, offer to show status (`/news-status`) or run pipeline (`/news-run`).

2. **Run init**:

```bash
cd "${CLAUDE_PLUGIN_ROOT}" && PYTHONPATH=. python3 -m herald.cli init
```

3. **Configure sources**: Read `config.yaml` from the herald data directory (see step 1) and help user add sources:
   - Ask: "What topics do you follow? (e.g., AI, Rust, DevOps, security)"
   - Based on answer, suggest sources with RSS feeds and HN integration
   - Edit `~/.herald/config.yaml` to add sources using this format:
     ```yaml
     sources:
       - id: hn
         name: Hacker News
         weight: 0.3
         category: community
       - id: simonw
         name: Simon Willison
         url: https://simonwillison.net/atom/everything/
         weight: 0.2
     ```
   - For HN source, add `hn` adapter mapping (handled by pipeline)
   - Optionally configure topics for keyword filtering

4. **Run first collection**:

```bash
cd "${CLAUDE_PLUGIN_ROOT}" && PYTHONPATH=. python3 -m herald.cli run
```

5. **Show results**: Report articles collected and stories created.

6. **Privacy note**: "All data stays local in your herald data directory (~/.local/share/herald/ by default). No paid API keys required. RSS feeds are fetched directly."

7. **Next step**: "Run `/news-digest` to read today's digest."
