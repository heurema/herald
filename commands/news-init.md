---
name: news init
description: Set up claude-news daily digest pipeline
allowed-tools: Bash, Read, Write
---

You are setting up the claude-news daily news digest pipeline for the user.

## Steps

1. **Check if already set up**: Look for `~/.config/claude-news/config.yaml`. If it exists, tell the user setup is already done and offer to re-run or show status.

2. **Ask preferences** (if interactive):
   - Preset: "AI Engineering" (default) or blank (`--blank`) for custom
   - Schedule time: default 06:00, or ask for preferred time

3. **Run setup.sh**:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/setup.sh" --preset <preset> --time <HH:MM>
```

4. **Run first collection** to verify everything works:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/pipeline/run.sh"
```

5. **Show results**: Read `~/.local/share/claude-news/data/state/last_run.json` and report items collected and status.

6. **Show privacy notice**: "This plugin fetches RSS feeds and public APIs daily. All data stays local. No paid API keys required."

7. **Offer next step**: "Run /news digest to read today's digest."
