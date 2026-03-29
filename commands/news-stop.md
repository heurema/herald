---
name: news-stop
description: Show cleanup options for herald data
allowed-tools: Bash, Read
---

You are helping the user clean up herald data.

## Steps

1. **Find data directory and check status**:
   ```bash
   cd "${CLAUDE_PLUGIN_ROOT}" && PYTHONPATH=. python3 -c "from herald.cli import _default_data_dir; print(_default_data_dir())"
   ```
   (Defaults to `~/.local/share/herald/`; use `--data-dir` or `HERALD_DATA_DIR` to override.)

```bash
cd "${CLAUDE_PLUGIN_ROOT}" && PYTHONPATH=. python3 -m herald.cli status 2>/dev/null
```

2. **Show cleanup options** (use the data directory path from step 1):
   - "To delete all data and config: `rm -rf <data-dir>/`"
   - "To re-initialize: run `/news-init`"

3. **Do NOT delete data automatically.** The user decides.
