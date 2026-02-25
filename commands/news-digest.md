---
name: news digest
description: Read today's curated news digest
allowed-tools: Bash, Read
---

You are presenting the user's daily news digest from claude-news.

## Steps

1. **Find latest digest**: Check these paths in order:
   - `~/.local/share/claude-news/data/digests/$(date +%Y-%m-%d).md` (today)
   - Yesterday's date as fallback

2. **Read last_run.json**: Read `~/.local/share/claude-news/data/state/last_run.json` for run metadata.

3. **Show header**: "Last run: YYYY-MM-DD HH:MM (STATUS). Items: X kept from Y collected."

4. **Handle edge cases**:
   - No digest file exists: "No digest available. Run /news run or check /news init."
   - Digest exists but zero items: "No relevant items found today. Your filters may be too narrow. Edit ~/.config/claude-news/config.yaml to adjust."
   - last_run.json shows error: "Last run had errors. Check ~/.local/share/claude-news/data/state/collect.log"

5. **Present digest**: Read the digest markdown file and present the items grouped by topic. Highlight items most relevant to the user's current work context.

6. **Ask**: "Anything actionable here? I can help you dive deeper into any of these items."
