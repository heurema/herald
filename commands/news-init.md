---
name: news init
description: Set up herald daily digest pipeline
allowed-tools: Bash, Read, Write, Edit
---

You are setting up the herald daily news digest pipeline for the user.

## Steps

1. **Check if already set up**: Look for `~/.config/herald/config.yaml`.
   - If it exists AND no topic argument was given: tell user setup is already done and offer to re-run or show status.
   - If it exists AND a topic argument was given: skip to step 1b (add topic to existing config).

1b. **Add topic to existing config** (only when `/news init <topic>` is used with existing config):

@${CLAUDE_PLUGIN_ROOT}/lib/topic-catalog.md

   - Match the argument against the topic catalog above (use aliases for fuzzy matching: "k8s"→devops, "js"→typescript, "py"→python).
   - If matched: show what will be added (feeds + keywords), ask user to confirm, then:
     - Read `~/.config/herald/config.yaml`
     - Append feeds to `add_feeds` (skip duplicates by name or URL)
     - Append keywords to `add_keywords` (create key if missing)
     - Write config via Edit tool
     - Confirm: "Added <topic>: N feeds, M keywords. Run /news run to fetch from new sources."
   - If NOT matched: "Unknown topic '<input>'. Available: rust, devops, golang, typescript, security, python, data. Or use /news add <url> for a custom source."
   - Return (do not run setup.sh again).

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

5. **Show results**: Read `~/.local/share/herald/data/state/last_run.json` and report items collected and status.

6. **Show privacy notice**: "This plugin fetches RSS feeds and public APIs daily. All data stays local. No paid API keys required."

7. **Offer next step**: "Run /news digest to read today's digest."
