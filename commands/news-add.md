---
name: news add
description: Add a news source (URL, domain, or topic) to your herald config
allowed-tools: Bash, Read, Write, Edit
---

You are adding a news source to the user's herald config.

## Preflight

1. Check that `~/.config/herald/config.yaml` exists. If not: "Run /news init first."
2. Read config. If YAML parse fails: "Your config file has invalid YAML. Fix it manually or delete it and run /news init."

## Determine input type

Parse the user's input after `/news add`:
- If it looks like a URL (starts with http/https or contains a dot with a path): → URL flow
- If it matches a known topic from the catalog below: → Topic flow
- If no argument: ask "Paste a URL or type a topic name (e.g., rust, devops, security)"

## URL Flow — RSS Autodiscovery

1. **Platform heuristics** — check first (no HTTP needed):
   - `github.com/<org>/<repo>` → `https://github.com/<org>/<repo>/releases.atom`
   - `*.substack.com` → `https://<domain>/feed`
   - `reddit.com/r/<sub>` → `https://www.reddit.com/r/<sub>.rss`
   - `medium.com/<user>` → `https://medium.com/feed/<user>`
   - `dev.to/<user>` → `https://dev.to/feed/<user>`
   - `youtube.com/@<channel>` → tell user: "YouTube requires a channel ID for RSS. Find it at youtube.com/account_advanced."

2. **Common RSS paths** — try GET requests (NOT HEAD — many sites block HEAD):
   ```bash
   UA="Mozilla/5.0 (compatible; Herald/1.0)"
   DOMAIN="<domain>"
   FOUND=""
   for path in /feed /rss /atom.xml /feed.xml /rss.xml /index.xml /feed/atom; do
     RESP=$(curl -s -o /dev/null -w "%{http_code} %{content_type}" -L --max-time 5 --max-redirs 3 -A "$UA" "https://${DOMAIN}${path}" 2>/dev/null)
     CODE=$(echo "$RESP" | cut -d' ' -f1)
     CTYPE=$(echo "$RESP" | cut -d' ' -f2-)
     if [ "$CODE" = "200" ]; then
       FOUND="https://${DOMAIN}${path}"
       echo "Found: ${FOUND} (${CTYPE})"
       break
     fi
   done
   echo "RESULT: ${FOUND:-NONE}"
   ```

3. **HTML head parsing** — if no common path works:
   ```bash
   UA="Mozilla/5.0 (compatible; Herald/1.0)"
   curl -s -L --max-time 10 --max-redirs 3 -A "$UA" "<url>" 2>/dev/null | \
     grep -ioE '<link[^>]+(application/(rss|atom)\+xml|text/xml)[^>]+>' | \
     grep -ioE 'href="[^"]+"' | head -3
   ```
   Note: extracted href may be relative — prepend `https://<domain>` if it doesn't start with http.

4. **Validate discovered feed** — fetch and check content looks like XML/RSS:
   ```bash
   UA="Mozilla/5.0 (compatible; Herald/1.0)"
   curl -s -L --max-time 10 -A "$UA" "<feed_url>" 2>/dev/null | head -5
   ```
   If first lines contain `<?xml` or `<rss` or `<feed` or `<atom` — valid feed.
   If HTML or empty — not a feed, continue searching or tell user.

5. **If found**: Show the discovered RSS URL and ask user to confirm.
6. **If not found**: "Could not auto-detect RSS feed for <domain>. Tried: /feed, /atom.xml, /feed.xml, etc. If you know the RSS URL, paste it directly."

## After RSS URL is confirmed

1. Suggest a name from the domain or feed title. Ask user to accept or change.
2. Ask for priority:
   - high (tier:1, weight:0.25) — daily must-reads
   - normal (tier:2, weight:0.20) — good sources (default)
   - low (tier:3, weight:0.15) — occasional/community
3. Read `~/.config/herald/config.yaml`
4. Resolve preset path via Bash: `echo "${CLAUDE_PLUGIN_ROOT}/presets"`, then Read the preset file (name from config's `preset` field, default "ai-engineering").
5. Check: if a feed with same name OR same URL already exists in preset feeds OR in `add_feeds` — tell user and stop. (Check both to avoid duplicates in the pipeline.)
6. Append to `add_feeds` list. If `add_feeds` key doesn't exist yet, create it.
7. Write the updated config via Edit tool (targeted append, not full rewrite).
8. Confirm: "Added <name>. Run /news run to fetch articles from this source."

## Topic Flow

@${CLAUDE_PLUGIN_ROOT}/lib/topic-catalog.md

If input matches a topic name or alias from the catalog above:

1. Show what will be added: keywords list + feed names with URLs.
2. Ask: "Add all feeds + keywords? [all / keywords only / let me pick]"
3. Read `~/.config/herald/config.yaml`
4. Resolve preset path via Bash: `echo "${CLAUDE_PLUGIN_ROOT}/presets"`, then Read the preset file.
5. For each selected feed: check if name or URL already exists in preset feeds OR in `add_feeds` — skip duplicates silently and note them.
6. Add to `add_keywords` (create key if missing) and `add_feeds` as selected.
7. Write config via Edit tool.
8. Confirm: "Added <topic>: N feeds, M keywords. Run /news run to see results."

If input does NOT match any topic: "Unknown topic '<input>'. Available: rust, devops, golang, typescript, security, python, data. Or paste a URL."

## Config rules

- NEVER edit preset files in the plugin directory
- Only edit `~/.config/herald/config.yaml`
- Use Edit tool for targeted changes (append to list), not Write for full rewrite
- Preserve existing content and YAML comments
- Always confirm with user before writing
