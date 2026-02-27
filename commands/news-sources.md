---
name: news sources
description: View and manage your herald news sources and topics
allowed-tools: Bash, Read, Write, Edit
---

You are showing and managing the user's herald sources.

## Preflight

1. Check `~/.config/herald/config.yaml` exists. If not: "Run /news init first."
2. Read config. If YAML parse fails: "Config file has invalid YAML. Fix manually or delete and /news init."

## Resolve preset path

The preset file lives in the plugin directory. Get the path via Bash:
```bash
echo "${CLAUDE_PLUGIN_ROOT}/presets"
```
Use the returned absolute path to Read the preset YAML file. The preset name is in the user config's `preset` field (default: "ai-engineering").

## Default: show all sources

1. Read user config: `~/.config/herald/config.yaml`
2. Determine preset name from config `preset` field (default: "ai-engineering")
3. Read preset file via the resolved absolute path from Bash above
4. Compute effective list:
   - Start with preset feeds
   - Add feeds from user's `add_feeds`
   - Remove feeds listed in user's `remove_feeds`
5. Read user's `add_keywords` and `remove_keywords` to compute active topics
6. Display grouped by tier:

```
TIER 1 — Daily (high priority)
  ✓ HN Frontpage 100+        (preset)
  ✓ Simon Willison           (preset)
  + Dan Luu                  (added by you)

TIER 2 — Weekly (normal priority)
  ✓ Import AI                (preset)

TIER 3 — Releases
  ✓ Claude Code Releases     (preset)

Removed by you:
  × r/MachineLearning

Topics: ai_agents, ai_coding, ai_finance, ai_models, ai_engineering
Total: 22 sources, 5 topics

Commands: /news add <url-or-topic>, /news sources remove <name>
```

## Subcommand: remove <name>

1. Read config + preset (resolve preset path via Bash first)
2. Check if name exists in preset feeds or in user's `add_feeds`
3. If NOT found anywhere: "Feed '<name>' not found. Run /news sources to see all feeds."
4. If preset feed:
   - Add name to `remove_feeds` list in user config
   - Confirm: "Removed <name> (preset source). Undo: /news sources restore <name>"
5. If user-added feed:
   - Remove entry from `add_feeds` list
   - Confirm: "Removed <name> (your custom source). Re-add with: /news add <url>"
   - Do NOT show undo via restore — restore only works for preset feeds.

## Subcommand: restore <name>

1. Read config
2. Check if name is in `remove_feeds` list
3. If found: remove from list, write config. Show: "Restored <name>."
4. If NOT found: "Feed '<name>' is not in your removed list. Run /news sources to see status."

## Subcommand: export

1. Read preset + user config via Bash-resolved path
2. Compute merged effective config (all feeds + all keywords, fully resolved)
3. Write standalone YAML file with `preset: "blank"` + all feeds + all keywords explicit:
   - Default path: `~/herald-export-YYYY-MM-DD.yaml` (use current date)
4. Show: "Exported to <path>. Share with colleague: /news sources import <path>"

## Subcommand: import <path>

1. Read the external file. Validate it's valid YAML with a feeds or add_feeds structure.
2. Show what will be added: list new feeds not already in user config, list new keyword topics.
3. Merge: add new feeds and keywords, keep existing ones. No destructive replace.
4. Write merged config.
5. Confirm: "Imported N new sources, M new topics. Run /news run to fetch from new sources."

## Subcommand: add (fallback)

If user types `/news sources add <something>`:
"Use /news add <url-or-topic> to add sources."

## Config rules

- NEVER edit preset files
- Only edit ~/.config/herald/config.yaml
- Use Edit tool for targeted changes, not full rewrite
- Preserve existing YAML comments
- Always confirm before writing
