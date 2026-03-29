---
name: news-status
description: Show herald database statistics and last run info
allowed-tools: Bash, Read
---

You are showing the user's herald status.

## Steps

1. **Check setup**: Find the herald data directory:
   ```bash
   cd "${CLAUDE_PLUGIN_ROOT}" && PYTHONPATH=. python3 -c "from herald.cli import _default_data_dir; print(_default_data_dir())"
   ```
   Verify `herald.db` exists there (defaults to `~/.local/share/herald/`; use `--data-dir` or `HERALD_DATA_DIR` to override). If not: "Run `/news-init` first."

2. **Show status**:

```bash
cd "${CLAUDE_PLUGIN_ROOT}" && PYTHONPATH=. python3 -m herald.cli status
```

3. **Present** the article count, story count, and last run time in a readable format.
