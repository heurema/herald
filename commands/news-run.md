---
name: news run
description: Manually trigger news collection and analysis
allowed-tools: Bash, Read
---

You are manually triggering the claude-news pipeline.

## Steps

1. **Check setup**: Verify `~/.local/share/claude-news/.venv/bin/activate` exists. If not, tell user to run `/news init` first.

2. **Run pipeline**:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/pipeline/run.sh"
```

3. **Show progress**: Read the tail of `~/.local/share/claude-news/data/state/collect.log` for the latest run output.

4. **Show results**: Read `~/.local/share/claude-news/data/state/last_run.json` and report:
   - Items collected
   - Status

5. **Offer next step**: "Run /news digest to read the results."
