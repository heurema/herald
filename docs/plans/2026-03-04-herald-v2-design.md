# Herald v2 — Agent-Native News Intelligence Layer

**Date:** 2026-03-04
**Status:** Approved (arbiter-reviewed, 4 sections)
**Breaking:** Yes (v1 → v2 migration required)

## Overview

Redesign Herald from a simple RSS/HN collector with JSONL storage into a local-first news intelligence layer with SQLite storage, article→story clustering, and structured CLI.

**Key decisions:**
- SQLite + FTS5 replaces JSONL flat files
- Article → Story → Digest entity model (clustering, not just dedup)
- Hybrid CLI + static brief (no MCP server in v2)
- stdlib-first clustering (SequenceMatcher), upgrade path to datasketch
- Breaking changes OK — clean slate

---

## Section 1: Data Model

### Tables

```sql
CREATE TABLE sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT,
    weight REAL NOT NULL DEFAULT 0.2,
    category TEXT CHECK(category IN ('community','official','aggregator'))
);

CREATE TABLE articles (
    id TEXT PRIMARY KEY,                    -- ULID
    url_original TEXT NOT NULL,
    url_canonical TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    origin_source_id TEXT NOT NULL REFERENCES sources(id),
    published_at INTEGER,
    collected_at INTEGER NOT NULL,
    points INTEGER NOT NULL DEFAULT 0 CHECK(points >= 0),
    story_type TEXT NOT NULL DEFAULT 'news'
        CHECK(story_type IN ('news','release','research','opinion','tutorial')),
    score_base REAL NOT NULL,
    scored_at INTEGER NOT NULL,
    extra TEXT CHECK(extra IS NULL OR json_valid(extra))
);

CREATE TABLE mentions (
    article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES sources(id),
    url TEXT NOT NULL,
    points INTEGER NOT NULL DEFAULT 0,
    discovered_at INTEGER NOT NULL,
    extra TEXT,
    PRIMARY KEY (article_id, source_id)
);

CREATE TABLE article_topics (
    article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    topic TEXT NOT NULL,
    PRIMARY KEY (article_id, topic)
);
CREATE INDEX idx_article_topics_topic ON article_topics(topic, article_id);

CREATE TABLE stories (
    id TEXT PRIMARY KEY,                    -- ULID
    title TEXT NOT NULL,
    summary TEXT,
    story_type TEXT NOT NULL DEFAULT 'news',
    score REAL NOT NULL,
    canonical_article_id TEXT REFERENCES articles(id) ON DELETE SET NULL,
    first_seen INTEGER NOT NULL,
    last_updated INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','inactive'))
);

CREATE TABLE story_articles (
    story_id TEXT NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    PRIMARY KEY (story_id, article_id),
    UNIQUE(article_id)  -- 1 article = 1 story
);

CREATE TABLE story_topics (
    story_id TEXT NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    topic TEXT NOT NULL,
    PRIMARY KEY (story_id, topic)
);
CREATE INDEX idx_story_topics_topic ON story_topics(topic, story_id);

CREATE TABLE pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at INTEGER NOT NULL,
    finished_at INTEGER,
    articles_new INTEGER DEFAULT 0,
    articles_updated INTEGER DEFAULT 0,
    stories_created INTEGER DEFAULT 0,
    stories_updated INTEGER DEFAULT 0,
    error TEXT
);
```

### Indexes

```sql
CREATE INDEX idx_articles_collected_at ON articles(collected_at DESC);
CREATE INDEX idx_articles_source ON articles(origin_source_id, collected_at DESC);
CREATE INDEX idx_stories_score ON stories(score DESC);
CREATE INDEX idx_stories_last_updated ON stories(last_updated DESC);
CREATE INDEX idx_story_articles_article ON story_articles(article_id, story_id);
```

### FTS5

```sql
CREATE VIRTUAL TABLE articles_fts USING fts5(title, content=articles, content_rowid=rowid);
CREATE VIRTUAL TABLE stories_fts USING fts5(title, summary, content=stories, content_rowid=rowid);
```

Sync triggers on INSERT/UPDATE/DELETE for both tables (standard FTS5 content-sync pattern).

### Scoring Formulas

```
Article.score_base = source.weight
                   + min(points / 500, 3.0)
                   + keyword_density * 0.2
                   + (0.2 if story_type == 'release')

effective_score    = score_base - (hours_since_scored * 0.005)

Story.score        = max(article.score_base)
                   + ln(source_count) * 0.3
                   + (0.2 if new_article_in_24h)
```

### URL Canonicalization (10 rules)

1. Lowercase scheme + host
2. Strip `www.` only for exact match
3. Remove: `utm_*`, `fbclid`, `gclid`, `ref`, `source`
4. Sort remaining query params
5. Strip fragment (except `#!` hashbang)
6. Normalize `http` → `https`
7. Strip trailing `/` (except root)
8. Strip default ports (`:80`, `:443`)
9. Percent-decode unreserved chars
10. Store both `url_original` and `url_canonical`

---

## Section 2: Pipeline Architecture

### 4 Stages: Collect → Ingest → Cluster → Project

```
Collect     → raw items from sources (RSS/Atom, HN Algolia, Tavily)
Ingest      → normalize + score + UPSERT into SQLite (single transaction)
Cluster     → group articles into stories (single transaction)
Project     → generate markdown brief from SQL queries
```

### Collect

Each source adapter returns `RawItem` dicts. Adapters: `RSSAdapter`, `HNAdapter`, `TavilyAdapter`.

```python
@dataclass
class RawItem:
    url: str
    title: str
    source_id: str
    published_at: int | None
    points: int
    extra: dict | None
```

Error handling: per-source try/except, log failures, continue with others.

### Ingest (single transaction)

```sql
INSERT INTO articles (id, url_original, url_canonical, title, origin_source_id,
                      published_at, collected_at, story_type, score_base, scored_at, extra)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(url_canonical) DO UPDATE SET
    points = max(articles.points, excluded.points),
    score_base = excluded.score_base,
    scored_at = excluded.scored_at
RETURNING id;
```

After UPSERT: insert/update mentions, refresh article_topics.

### Cluster

See Section 4 below.

### Project

SQL queries → markdown with YAML frontmatter. Static file output (no server).

---

## Section 3: CLI Interface

### Commands

```
herald init [preset]              # initialize config + database
herald run                        # collect + ingest + cluster + project
herald brief [--limit N]          # show latest brief
herald search <query>             # FTS5 search
herald topic <name> [--limit N]   # articles/stories for topic
herald topics                     # list all topics with counts
herald story <id>                 # story detail with articles
herald stories [--limit N]        # top stories
herald article <id>               # article detail
herald sources                    # list configured sources
herald source add <url> [--name] [--weight] [--category]
herald source remove <id>
herald status                     # db stats, last run, health
herald config show|edit           # view/edit YAML config
herald schedule install|uninstall|status  # cron management
herald recluster [--since Nd]     # rebuild clusters for window
```

### Global Flags

```
--format md|json    # output format (default: md)
--json              # alias for --format json
--limit N           # limit results
--help              # help text
```

### JSON Output Contract

```json
{"schema_version": 1, "generated_at": "...", "command": "...", "data": {...}, "errors": []}
```

### Slash Commands (thin wrappers)

```
/herald          → herald brief --limit 10
/herald-topic    → herald topic <arg>
/herald-search   → herald search <query>
/herald-story    → herald story <id>
/herald-run      → herald run
```

All call CLI with `--format md`, parse output.

### Config (YAML SSoT)

```yaml
sources:
  - id: hn
    name: Hacker News
    adapter: hn_algolia
    weight: 0.3
    category: community

clustering:
  threshold: 0.65
  max_time_gap_days: 7
  min_title_words: 4
  canonical_delta: 0.1

schedule:
  interval_hours: 4
```

---

## Section 4: Clustering Algorithm

### Incremental Single-Pass Clustering

```python
def cluster(db: Database) -> ClusterResult:
    """Single transaction. Deterministic: ORDER BY collected_at ASC, id ASC."""

    active_stories = db.query("""
        SELECT s.id, s.title, s.score, s.canonical_article_id
        FROM stories s WHERE s.status = 'active'
        ORDER BY s.score DESC
    """)

    unclustered = db.query("""
        SELECT a.id, a.title, a.score_base, a.origin_source_id, a.collected_at
        FROM articles a
        LEFT JOIN story_articles sa ON sa.article_id = a.id
        WHERE sa.story_id IS NULL
        ORDER BY a.collected_at ASC, a.id ASC
    """)

    for article in unclustered:
        norm_title = normalize_title(article.title)
        best_match, best_score = None, 0.0

        for story in active_stories:
            # Guard 1: topic overlap (≥1 shared topic from top-5)
            if not topics_overlap(article, story):
                continue
            # Guard 2: time gap > max_time_gap_days
            if time_gap(article, story) > max_time_gap_days * 86400:
                continue
            # Guard 3: min title words
            if len(norm_title.split()) < min_title_words:
                continue
            # Guard 4: token overlap — ≥2 shared non-stopword tokens
            if shared_tokens(norm_title, story.title) < 2:
                continue
            # Guard 5: version/number match
            if has_conflicting_numbers(norm_title, story.title):
                continue

            sim = SequenceMatcher(None, norm_title,
                                  normalize_title(story.title)).ratio()
            if sim > best_score:
                best_score, best_match = sim, story

        if best_match and best_score >= threshold:  # default 0.65
            join_story(article, best_match)
            # update in-memory story title (may change from canonical re-election)
            best_match.title = get_story_title(best_match.id, db)
        else:
            new_story = create_story(article)
            active_stories.append(new_story)  # add to candidates

    deactivate_stale_stories(db, max_time_gap_days)
```

### Title Normalization

Strip HN prefixes (`Show HN:`, `Ask HN:`, etc.), outlet suffixes (`- The Verge`, `| TechCrunch`, etc.), lowercase, collapse whitespace.

### Guards (5 total)

| # | Guard | Purpose | Cost |
|---|-------|---------|------|
| 1 | Topic overlap (top-5) | Skip unrelated articles | O(1) set intersection |
| 2 | Time gap | Skip old stories | O(1) timestamp |
| 3 | Min title words ≥ 4 | Skip generic titles | O(1) split |
| 4 | Token overlap ≥ 2 | Cheap pre-filter before SequenceMatcher | O(n) set intersection |
| 5 | Version/number match | Prevent "iOS 18.1" + "iOS 18.2" merge | O(n) regex |

### Story Score

```
score = max(article.score_base) + ln(source_count) * 0.3 + (0.2 if recent_24h)
```

### Canonical Re-election (with hysteresis)

Update `canonical_article_id` only when `new_source.weight ≥ current_source.weight + 0.1`. Prevents title thrashing.

### Story Topics

Union of article_topics, capped to top-5 by frequency. `topics_overlap` checks intersection against top-5.

### Recluster

```
1. DELETE story_articles for articles in window (--since Nd)
2. Recalculate canonical/score/topics for affected stories
3. DELETE empty stories
4. Run cluster()
```

### Story Lifecycle

Unified window: `max_time_gap_days` (default 7d) used for both time_gap guard AND lifecycle deactivation. No 72h/7d conflict.

### Phase 2: datasketch MinHash LSH

Trigger: >1000 active stories OR SequenceMatcher latency >5s/run. Same interface, better scale.

### Concurrency

Single-process, sequential execution. `cluster()` runs inside pipeline after Ingest. `BEGIN IMMEDIATE` transaction. No parallel cluster() runs.

---

## Config Model

**YAML file** = input SSoT (sources, clustering params, schedule).
**SQLite** = runtime data (articles, stories, scores, pipeline_runs).

YAML is read-only for the pipeline. CLI `config edit` modifies YAML. CLI `source add/remove` modifies YAML.

## Dependencies

- `fastfeedparser` — RSS/Atom parsing
- `httpx` — HTTP client
- `pyyaml` — config parsing
- `datasketch` — Phase 2 only (optional)

## Migration

v1 → v2 is a clean break. No migration path — `herald init` creates fresh SQLite database. Old JSONL data is not imported.
