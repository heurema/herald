# Herald FAQ

## Getting Started

**Q: What do I need to install Herald?**

Python 3.10 or higher, Claude Code, and network access to fetch RSS feeds. No API keys are required. `TAVILY_API_KEY` is optional and enables enhanced web search in digests.

**Q: How do I set up Herald for the first time?**

Run `/news init` inside Claude Code. The interactive setup will ask you to choose a preset (e.g., `devtools`, `ai-research`, `infosec`) and optionally install a scheduler so digests are fetched automatically each day.

**Q: How do I verify Herald is working after setup?**

Run `/news digest --demo`. This bypasses the scheduler and fetches + scores feeds immediately, printing the result to your terminal. If you see a formatted digest, Herald is working.

**Q: Where does Herald store its files?**

| Purpose | Location |
|---------|----------|
| Configuration | `~/.config/herald/config.yaml` |
| Raw feed data | `~/.local/share/herald/data/raw/YYYY-MM-DD.jsonl` |
| Digests | `~/.local/share/herald/digests/YYYY-MM-DD.yaml` |
| Lock file | `/tmp/herald.lock` |
| Scheduler (macOS) | `~/Library/LaunchAgents/dev.herald.fetch.plist` |

---

## Daily Usage

**Q: How do I read today's digest?**

Run `/news digest` in Claude Code. If no digest exists for today yet, Herald will prompt you to run a manual fetch first.

**Q: How do I add a new RSS feed or topic?**

```
/news add https://example.com/feed.xml
/news add rust programming
```

Pass a URL to add an RSS/Atom feed directly. Pass a topic phrase to let Herald find relevant feeds automatically.

**Q: How do I see and manage my current sources?**

Run `/news sources`. This lists all active feeds with their status (enabled/disabled, last fetch time, error count).

**Q: What are presets and how do I switch them?**

Presets are curated feed bundles for common interest areas (e.g., `devtools`, `ai-research`, `infosec`). During `/news init` you choose one as a starting point. To add feeds from another preset later, edit `~/.config/herald/config.yaml` directly or use `/news add` for individual feeds.

**Q: Can I trigger a fetch manually without waiting for the scheduler?**

Yes. Run `/news run` to execute an immediate fetch cycle. The result is saved to the digest store and readable via `/news digest`.

**Q: How do I stop the scheduler without uninstalling Herald?**

Run `/news stop`. This removes the launchd plist (macOS), systemd timer (Linux), or crontab entry without deleting your config or historical digests.

---

## Troubleshooting

**Q: `/news digest` says "no digest found for today". What do I do?**

The scheduler has not run yet, or was not installed. Run `/news run` to fetch immediately, then `/news digest` again.

**Q: Herald hangs or times out when fetching feeds.**

Each feed has a 5-10 second timeout. A slow or unreachable feed will block its slot. To identify problem feeds:

```bash
# Check the raw log for the current day
cat ~/.local/share/herald/data/raw/$(date +%Y-%m-%d).jsonl | python3 -m json.tool | grep -i error
```

Disable a problem feed with `/news sources`, then select it and toggle it off.

**Q: I get "lock file exists" or Herald refuses to start.**

Herald uses `/tmp/herald.lock` to prevent concurrent runs. If a previous run crashed, the lock may be stale:

```bash
rm /tmp/herald.lock
```

Verify no Herald process is running before removing the lock:

```bash
pgrep -fl herald
```

**Q: The scheduler is not running on macOS. How do I check?**

```bash
# Check if the plist is loaded
launchctl list | grep herald

# Check the plist file directly
cat ~/Library/LaunchAgents/dev.herald.fetch.plist

# Manually load it
launchctl load ~/Library/LaunchAgents/dev.herald.fetch.plist

# Check for errors in system log
log show --predicate 'subsystem == "dev.herald"' --last 1h
```

**Q: The scheduler is not running on Linux. How do I check?**

```bash
# Check systemd timer status
systemctl --user status herald-fetch.timer

# List all timers
systemctl --user list-timers

# Enable and start if missing
systemctl --user enable --now herald-fetch.timer

# View recent logs
journalctl --user -u herald-fetch.service --since "1 hour ago"
```

**Q: I get a Python version error.**

Herald requires Python 3.10+. Check your version:

```bash
python3 --version
```

If your system Python is older, you can point Herald at a newer interpreter by setting `python_bin` in `~/.config/herald/config.yaml`:

```yaml
python_bin: /opt/homebrew/bin/python3.13
```

**Q: The virtual environment is broken or missing.**

<details>
<summary>Reinitialize the venv</summary>

```bash
# Locate the herald lib directory (same as where setup.sh lives)
HERALD_LIB=~/.local/lib/herald

# Remove and recreate
rm -rf "$HERALD_LIB/.venv"
python3 -m venv "$HERALD_LIB/.venv"
"$HERALD_LIB/.venv/bin/pip" install -r "$HERALD_LIB/requirements.txt"
```

After recreating, run `/news run` to confirm feeds fetch correctly.
</details>

**Q: `/news digest --demo` shows no items or an empty digest.**

<details>
<summary>Diagnosis steps</summary>

1. Check that at least one feed is enabled: `/news sources`
2. Run a manual fetch and watch the output: `/news run`
3. Inspect the raw data file for the current day:
   ```bash
   wc -l ~/.local/share/herald/data/raw/$(date +%Y-%m-%d).jsonl
   ```
   Zero lines means no items were fetched. Check network access and feed URLs.
4. Verify the feed URLs are reachable:
   ```bash
   curl -I https://example.com/feed.xml
   ```
</details>

---

## Privacy & Data

**Q: Does Herald send my data anywhere?**

Herald only contacts the RSS/Atom feed URLs you have configured, and (if enabled) the Tavily API for enhanced search. No telemetry, no analytics, no data leaves your machine beyond these explicit requests.

**Q: Is an internet connection required?**

Yes, to fetch feeds. Once a digest is generated, you can read it offline via `/news digest` since the result is stored locally in `~/.local/share/herald/digests/`.

**Q: What happens to historical digests?**

They accumulate in `~/.local/share/herald/digests/`. Herald does not auto-delete them. You can remove old files manually:

```bash
# Remove digests older than 30 days
find ~/.local/share/herald/digests/ -name "*.yaml" -mtime +30 -delete
```

**Q: Does Herald store feed credentials or cookies?**

No. Herald only fetches public RSS/Atom feeds over HTTP/HTTPS with no authentication. Feed URLs requiring login are not supported.

---

## Customization

**Q: How do I edit Herald's configuration directly?**

Open `~/.config/herald/config.yaml` in any editor. Changes take effect on the next fetch cycle or `/news run`.

**Q: Can I add feeds that are not in any preset?**

Yes. Use `/news add <url>` for any valid RSS or Atom feed URL, or add entries directly under the `feeds:` key in `config.yaml`:

```yaml
feeds:
  - url: https://example.com/feed.xml
    label: "Example Blog"
    enabled: true
```

**Q: How do I change the fetch schedule?**

Edit the schedule in `config.yaml`:

```yaml
schedule:
  hour: 7
  minute: 30
```

After changing the schedule, re-run `/news init` (or reload the scheduler manually) for the change to take effect.

**Q: Can I run Herald on a server and sync digests to my laptop?**

Herald's data directories (`~/.local/share/herald/`) are plain files. You can sync them with any tool (rsync, Syncthing, rclone). Configure the same `config.yaml` on your laptop and point Herald at the synced data directory by setting `data_dir` in the config.

**Q: How do I completely uninstall Herald?**

```bash
# Stop and remove the scheduler
/news stop   # inside Claude Code, OR:

# macOS — remove plist manually
launchctl unload ~/Library/LaunchAgents/dev.herald.fetch.plist
rm ~/Library/LaunchAgents/dev.herald.fetch.plist

# Linux — disable timer
systemctl --user disable --now herald-fetch.timer

# Remove data and config
rm -rf ~/.config/herald
rm -rf ~/.local/share/herald
rm -rf ~/.local/lib/herald
```
