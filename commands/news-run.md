---
name: news-run
description: Manually trigger herald news collection and analysis
allowed-tools: Bash, Read
---

You are manually triggering the herald v2 pipeline.

## Steps

1. **Check setup**: Find the herald data directory:
   ```bash
   cd "${CLAUDE_PLUGIN_ROOT}" && PYTHONPATH=. python3 -c "from herald.cli import _default_data_dir; print(_default_data_dir())"
   ```
   Verify `config.yaml` exists there (defaults to `~/.local/share/herald/`; use `--data-dir` or `HERALD_DATA_DIR` to override). If not: "Run `/news-init` first."

2. **Run pipeline**:

```bash
cd "${CLAUDE_PLUGIN_ROOT}" && PYTHONPATH=. python3 -m herald.cli run
```

3. **Show results**: Run status to see what was collected:

```bash
cd "${CLAUDE_PLUGIN_ROOT}" && PYTHONPATH=. python3 -m herald.cli status
```

4. **Offer next step**: "Run `/news-digest` to read the results."
