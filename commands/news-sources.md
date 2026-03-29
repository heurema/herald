---
name: news-sources
description: View and manage your herald news sources
allowed-tools: Bash, Read, Write, Edit
---

You are showing and managing the user's herald sources.

## Preflight

1. Find the herald data directory:
   ```bash
   cd "${CLAUDE_PLUGIN_ROOT}" && PYTHONPATH=. python3 -c "from herald.cli import _default_data_dir; print(_default_data_dir())"
   ```
   Check `config.yaml` exists there (defaults to `~/.local/share/herald/`; use `--data-dir` or `HERALD_DATA_DIR` to override). If not: "Run `/news-init` first."
2. Read config. If YAML parse fails: "Config file has invalid YAML."

## Default: show all sources

1. Read `config.yaml` from the herald data directory (see Preflight)
2. Display sources grouped by category:

```
Sources:
  community:
    - hn: Hacker News (weight: 0.3)
  official:
    - openai: OpenAI Blog (weight: 0.25)

Topics: ai_agents, ai_models
Total: N sources
```

3. Show available commands:
   - `/news-add <url>` — add a source
   - `/news-sources remove <name>` — remove a source

## Subcommand: remove <name>

1. Read config
2. Find source by id or name (case-insensitive match)
3. If found: remove from sources list, write config via Edit tool
4. Confirm: "Removed <name>. Run `/news-run` to update."
5. If not found: "Source '<name>' not found. Run `/news-sources` to see all."

## Config rules

- Only edit the `config.yaml` in the herald data directory (see Preflight)
- Use Edit tool for targeted changes
- Preserve YAML comments
- Always confirm before writing
