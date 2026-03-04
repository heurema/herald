# Herald v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rewrite Herald from JSONL-based news collector into SQLite-backed news intelligence layer with article→story clustering and structured CLI.

**Architecture:** 4-stage pipeline (Collect → Ingest → Cluster → Project) backed by SQLite + FTS5. Incremental single-pass clustering with SequenceMatcher. CLI via argparse, slash commands as thin wrappers. See `docs/plans/2026-03-04-herald-v2-design.md` for full design.

**Tech Stack:** Python 3.14, SQLite (stdlib), fastfeedparser, httpx, pyyaml. No new dependencies.

**V1 reference:** Current code in `pipeline/`. V2 goes into `herald/` (new package). V1 stays untouched until v2 is stable, then removed.

---

## Task 1: Project Structure & Database Foundation

**Files:**
- Create: `herald/__init__.py`
- Create: `herald/db.py`
- Create: `herald/schema.sql`
- Create: `tests/v2/__init__.py`
- Create: `tests/v2/test_db.py`

**Step 1: Create v2 package directory**

```bash
mkdir -p herald tests/v2
touch herald/__init__.py tests/v2/__init__.py
```

**Step 2: Write schema.sql**

Full SQL schema from design doc (sources, articles, mentions, article_topics, stories, story_articles, story_topics, pipeline_runs, indexes, FTS5 tables, FTS5 sync triggers). One file, executed on init.

Reference: `docs/plans/2026-03-04-herald-v2-design.md` Section 1.

**Step 3: Write failing test for db module**

```python
# tests/v2/test_db.py
import sqlite3
import tempfile
from pathlib import Path

from herald.db import Database


def test_database_creates_tables():
    with tempfile.TemporaryDirectory() as d:
        db = Database(Path(d) / "test.db")
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = {r[0] for r in tables}
        assert "sources" in names
        assert "articles" in names
        assert "stories" in names
        assert "story_articles" in names
        assert "mentions" in names
        assert "pipeline_runs" in names


def test_database_creates_fts():
    with tempfile.TemporaryDirectory() as d:
        db = Database(Path(d) / "test.db")
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = {r[0] for r in tables}
        assert "articles_fts" in names
        assert "stories_fts" in names


def test_database_foreign_keys_enabled():
    with tempfile.TemporaryDirectory() as d:
        db = Database(Path(d) / "test.db")
        fk = db.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1


def test_database_wal_mode():
    with tempfile.TemporaryDirectory() as d:
        db = Database(Path(d) / "test.db")
        mode = db.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"


def test_database_transaction():
    with tempfile.TemporaryDirectory() as d:
        db = Database(Path(d) / "test.db")
        with db.transaction():
            db.execute("INSERT INTO sources (id, name, weight) VALUES ('s1', 'Test', 0.5)")
        row = db.execute("SELECT id, name FROM sources WHERE id='s1'").fetchone()
        assert row == ("s1", "Test")


def test_database_transaction_rollback():
    with tempfile.TemporaryDirectory() as d:
        db = Database(Path(d) / "test.db")
        try:
            with db.transaction():
                db.execute("INSERT INTO sources (id, name, weight) VALUES ('s1', 'Test', 0.5)")
                raise ValueError("boom")
        except ValueError:
            pass
        row = db.execute("SELECT id FROM sources WHERE id='s1'").fetchone()
        assert row is None


def test_fts5_available():
    """FTS5 extension works — insert and match."""
    with tempfile.TemporaryDirectory() as d:
        db = Database(Path(d) / "test.db")
        db.execute("INSERT INTO sources (id, name, weight) VALUES ('s1', 'Test', 0.5)")
        db.execute("""INSERT INTO articles (id, url_original, url_canonical, title,
            origin_source_id, collected_at, score_base, scored_at, story_type)
            VALUES ('a1', 'https://x.com', 'https://x.com', 'Python release notes',
            's1', 1000, 0.5, 1000, 'news')""")
        results = db.execute(
            "SELECT title FROM articles_fts WHERE articles_fts MATCH 'python'"
        ).fetchall()
        assert len(results) == 1
```

**Step 4: Run tests — verify they fail**

```bash
cd /Users/vi/personal/skill7/devtools/herald
PYTHONPATH=. pytest tests/v2/test_db.py -v
```

Expected: `ModuleNotFoundError: No module named 'herald.db'`

**Step 5: Implement db.py**

```python
# herald/db.py
"""SQLite database wrapper for Herald v2."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._conn = sqlite3.connect(str(path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._init_schema()

    def _init_schema(self):
        schema = _SCHEMA_PATH.read_text()
        self._conn.executescript(schema)

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def executemany(self, sql: str, params_seq) -> sqlite3.Cursor:
        return self._conn.executemany(sql, params_seq)

    @contextmanager
    def transaction(self):
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def close(self):
        self._conn.close()
```

**Step 6: Run tests — verify they pass**

```bash
PYTHONPATH=. pytest tests/v2/test_db.py -v
```

Expected: all 6 PASS.

**Step 7: Commit**

```bash
git add herald/ tests/v2/ herald/schema.sql
git commit -m "feat(v2): database foundation — schema, connection, transactions"
```

---

## Task 2: URL Canonicalization

**Files:**
- Create: `herald/url.py`
- Create: `tests/v2/test_url.py`

**Step 1: Write failing tests**

```python
# tests/v2/test_url.py
from herald.url import canonicalize_url


def test_lowercase_host():
    assert canonicalize_url("https://Example.COM/path") == "https://example.com/path"


def test_strip_www():
    assert canonicalize_url("https://www.example.com/p") == "https://example.com/p"


def test_strip_utm():
    assert canonicalize_url("https://x.com/p?utm_source=tw&id=1") == "https://x.com/p?id=1"


def test_strip_fbclid():
    assert canonicalize_url("https://x.com/p?fbclid=abc&q=1") == "https://x.com/p?q=1"


def test_sort_query_params():
    assert canonicalize_url("https://x.com/?z=1&a=2") == "https://x.com/?a=2&z=1"


def test_strip_fragment():
    assert canonicalize_url("https://x.com/p#section") == "https://x.com/p"


def test_keep_hashbang():
    assert canonicalize_url("https://x.com/#!/page") == "https://x.com/#!/page"


def test_http_to_https():
    assert canonicalize_url("http://example.com/p") == "https://example.com/p"


def test_strip_trailing_slash():
    assert canonicalize_url("https://x.com/path/") == "https://x.com/path"


def test_keep_root_slash():
    assert canonicalize_url("https://x.com/") == "https://x.com/"


def test_strip_default_port():
    assert canonicalize_url("https://x.com:443/p") == "https://x.com/p"


def test_strip_port_80():
    assert canonicalize_url("http://x.com:80/p") == "https://x.com/p"


def test_percent_decode_unreserved():
    assert canonicalize_url("https://x.com/%7Euser") == "https://x.com/~user"


def test_strip_ref_and_source():
    assert canonicalize_url("https://x.com/p?ref=tw&source=hn&id=1") == "https://x.com/p?id=1"


def test_combined():
    url = "http://WWW.Example.COM:80/path/?utm_source=x&b=2&a=1&ref=y#frag"
    assert canonicalize_url(url) == "https://example.com/path?a=1&b=2"
```

**Step 2: Run — verify fail**

```bash
PYTHONPATH=. pytest tests/v2/test_url.py -v
```

**Step 3: Implement url.py**

```python
# herald/url.py
"""URL canonicalization — 10 rules from design doc."""
import re
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode, unquote

_STRIP_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_cid", "utm_reader", "utm_name", "utm_social", "utm_social-type",
    "fbclid", "gclid", "gclsrc", "ref", "source",
})

_UNRESERVED = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)


def _decode_unreserved(s: str) -> str:
    """Percent-decode unreserved characters (RFC 3986 §2.3)."""
    def _repl(m):
        ch = chr(int(m.group(1), 16))
        return ch if ch in _UNRESERVED else m.group(0)
    return re.sub(r"%([0-9A-Fa-f]{2})", _repl, s)


def canonicalize_url(url: str) -> str:
    p = urlparse(url)

    # Rule 6: http → https
    scheme = "https"

    # Rule 1: lowercase host
    host = p.hostname or ""
    # Rule 2: strip www. (exact prefix)
    if host.startswith("www."):
        host = host[4:]

    # Rule 8: strip default ports
    port = p.port
    if port in (80, 443, None):
        netloc = host
    else:
        netloc = f"{host}:{port}"

    # Rule 9: percent-decode unreserved chars in path
    path = _decode_unreserved(p.path)

    # Rule 7: strip trailing slash (except root)
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    # Rule 5: strip fragment (except #! hashbang)
    fragment = p.fragment if p.fragment.startswith("!") else ""

    # Rule 3+13: remove tracking params
    if p.query:
        params = parse_qs(p.query, keep_blank_values=True)
        filtered = {
            k: v for k, v in params.items()
            if k.lower() not in _STRIP_PARAMS
        }
        # Rule 4: sort remaining params
        query = urlencode(sorted(filtered.items()), doseq=True)
    else:
        query = ""

    return urlunparse((scheme, netloc, path, "", query, fragment))
```

**Step 4: Run — verify pass**

```bash
PYTHONPATH=. pytest tests/v2/test_url.py -v
```

**Step 5: Commit**

```bash
git add herald/url.py tests/v2/test_url.py
git commit -m "feat(v2): URL canonicalization — 10 normalization rules"
```

---

## Task 3: Models & ULID

**Files:**
- Create: `herald/models.py`
- Create: `herald/ulid.py`
- Create: `tests/v2/test_models.py`

**Step 1: Write failing tests**

```python
# tests/v2/test_models.py
import time
from herald.ulid import generate_ulid
from herald.models import RawItem, Article, Source


def test_ulid_is_26_chars():
    assert len(generate_ulid()) == 26


def test_ulid_sortable_by_time():
    a = generate_ulid()
    time.sleep(0.002)
    b = generate_ulid()
    assert a < b


def test_ulid_unique():
    ids = {generate_ulid() for _ in range(100)}
    assert len(ids) == 100


def test_raw_item_fields():
    item = RawItem(url="https://x.com", title="Test", source_id="hn",
                   published_at=1000, points=50, extra=None)
    assert item.url == "https://x.com"
    assert item.source_id == "hn"


def test_source_defaults():
    s = Source(id="hn", name="Hacker News")
    assert s.weight == 0.2
    assert s.category == "community"
```

**Step 2: Run — verify fail**

```bash
PYTHONPATH=. pytest tests/v2/test_models.py -v
```

**Step 3: Implement ulid.py (stdlib, no deps)**

```python
# herald/ulid.py
"""Minimal ULID generator — stdlib only, no external deps."""
import os
import time

_ENCODING = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def generate_ulid() -> str:
    """Generate a ULID (Universally Unique Lexicographically Sortable Identifier)."""
    t = int(time.time() * 1000)
    # 10 chars for timestamp (48 bits)
    ts_part = []
    for _ in range(10):
        ts_part.append(_ENCODING[t & 0x1F])
        t >>= 5
    ts_part.reverse()
    # 16 chars for randomness (80 bits)
    rand_bytes = os.urandom(10)
    rand_int = int.from_bytes(rand_bytes, "big")
    rnd_part = []
    for _ in range(16):
        rnd_part.append(_ENCODING[rand_int & 0x1F])
        rand_int >>= 5
    rnd_part.reverse()
    return "".join(ts_part) + "".join(rnd_part)
```

**Step 4: Implement models.py**

```python
# herald/models.py
"""Data models for Herald v2."""
from dataclasses import dataclass, field


@dataclass
class Source:
    id: str
    name: str
    url: str | None = None
    weight: float = 0.2
    category: str = "community"  # community | official | aggregator


@dataclass
class RawItem:
    url: str
    title: str
    source_id: str
    published_at: int | None = None
    points: int = 0
    extra: dict | None = None


@dataclass
class Article:
    id: str
    url_original: str
    url_canonical: str
    title: str
    origin_source_id: str
    published_at: int | None
    collected_at: int
    points: int
    story_type: str
    score_base: float
    scored_at: int
    extra: dict | None = None


@dataclass
class Story:
    id: str
    title: str
    score: float
    canonical_article_id: str | None
    first_seen: int
    last_updated: int
    status: str = "active"
    summary: str | None = None
    story_type: str = "news"
```

**Step 5: Run — verify pass**

```bash
PYTHONPATH=. pytest tests/v2/test_models.py -v
```

**Step 6: Commit**

```bash
git add herald/ulid.py herald/models.py tests/v2/test_models.py
git commit -m "feat(v2): models and ULID generator"
```

---

## Task 4: Config v2

**Files:**
- Create: `herald/config.py`
- Create: `tests/v2/test_config.py`

Reference: design doc Section 3, config YAML structure. Reuse logic from `pipeline/config.py` where applicable. New YAML schema:

```yaml
sources:
  - id: hn
    name: Hacker News
    adapter: hn_algolia
    weight: 0.3
    category: community
    config:
      min_points: 100
clustering:
  threshold: 0.65
  max_time_gap_days: 7
  min_title_words: 4
  canonical_delta: 0.1
schedule:
  interval_hours: 4
topics:
  # reuse v1 topic rules format
```

**Step 1: Write failing tests**

Test: load config from YAML string, defaults for missing fields, sources parsed into Source objects, clustering params have defaults.

**Step 2: Run — verify fail**

**Step 3: Implement config.py**

- `HeraldConfig` dataclass with `sources: list[Source]`, `clustering: ClusterConfig`, `schedule: ScheduleConfig`, `topics: dict`
- `ClusterConfig` dataclass with threshold=0.65, max_time_gap_days=7, min_title_words=4, canonical_delta=0.1
- `load_config(path: Path) -> HeraldConfig` — YAML → validated config
- `resolve_config(preset_name: str, user_override: Path | None) -> HeraldConfig` — preset + overlay (reuse v1 overlay logic)

**Step 4: Run — verify pass**

**Step 5: Commit**

```bash
git add herald/config.py tests/v2/test_config.py
git commit -m "feat(v2): config loader with source/clustering/schedule params"
```

---

## Task 5: Scoring Module

**Files:**
- Create: `herald/scoring.py`
- Create: `tests/v2/test_scoring.py`

**Step 1: Write failing tests**

```python
# tests/v2/test_scoring.py
import math
from herald.scoring import article_score_base, story_score


def test_article_baseline():
    # source_weight=0.3, points=0, density=0, not release
    assert article_score_base(source_weight=0.3, points=0,
                               keyword_density=0.0, is_release=False) == 0.3


def test_article_points_cap():
    # min(1500/500, 3.0) = 3.0
    score = article_score_base(0.2, points=1500, keyword_density=0.0, is_release=False)
    assert score == 0.2 + 3.0


def test_article_points_partial():
    # min(250/500, 3.0) = 0.5
    score = article_score_base(0.2, points=250, keyword_density=0.0, is_release=False)
    assert score == 0.2 + 0.5


def test_article_release_boost():
    score = article_score_base(0.2, 0, 0.0, is_release=True)
    assert score == 0.2 + 0.2


def test_article_density():
    score = article_score_base(0.2, 0, keyword_density=0.5, is_release=False)
    assert score == 0.2 + 0.5 * 0.2


def test_story_single_source():
    # max_score=1.0, source_count=1, has_recent=False
    # 1.0 + ln(1)*0.3 + 0.0 = 1.0
    assert story_score(max_article_score=1.0, source_count=1, has_recent=False) == 1.0


def test_story_multi_source():
    # 1.0 + ln(3)*0.3 + 0.0
    expected = 1.0 + math.log(3) * 0.3
    assert abs(story_score(1.0, 3, False) - expected) < 0.001


def test_story_momentum():
    expected = 1.0 + 0.0 + 0.2  # ln(1)=0
    assert story_score(1.0, 1, has_recent=True) == expected
```

**Step 2: Run — verify fail**

**Step 3: Implement scoring.py**

```python
# herald/scoring.py
"""Scoring formulas for articles and stories."""
import math


def article_score_base(
    source_weight: float,
    points: int,
    keyword_density: float,
    is_release: bool,
) -> float:
    return (
        source_weight
        + min(points / 500, 3.0)
        + keyword_density * 0.2
        + (0.2 if is_release else 0.0)
    )


def story_score(
    max_article_score: float,
    source_count: int,
    has_recent: bool,
) -> float:
    coverage = math.log(max(source_count, 1)) * 0.3
    momentum = 0.2 if has_recent else 0.0
    return max_article_score + coverage + momentum
```

**Step 4: Run — verify pass**

**Step 5: Commit**

```bash
git add herald/scoring.py tests/v2/test_scoring.py
git commit -m "feat(v2): scoring formulas for articles and stories"
```

---

## Task 6: Collect v2

**Files:**
- Create: `herald/collect.py`
- Create: `tests/v2/test_collect.py`

Refactor from `pipeline/collect.py`. Key changes:
- Returns `list[RawItem]` (v2 model, not v1 dict)
- `source_id` comes from config, not hardcoded
- Keep `normalize_url` (already exists in v1) — but delegate canonical to `herald/url.py`
- Keep fault isolation (per-source try/except)
- Keep HN Algolia, RSS/Atom, Tavily adapters

**Step 1: Write failing tests**

Test RSS adapter with mocked httpx, test HN adapter with mocked response, test `collect_all` with mixed success/failure.

Port relevant tests from `tests/test_collect.py` and adapt for v2 RawItem.

**Step 2: Run — verify fail**

**Step 3: Implement collect.py**

Reuse most of `pipeline/collect.py` logic. Main change: return `RawItem` dataclass instead of dict.

```python
# herald/collect.py
"""Stage 1: Collect raw items from sources."""
from herald.models import RawItem, Source
# ... (reuse fetch_rss_feed, fetch_hn_stories, fetch_tavily logic)

def collect_all(sources: list[Source]) -> list[RawItem]:
    items = []
    for source in sources:
        try:
            adapter = _ADAPTERS.get(source.config.get("adapter", "rss"))
            items.extend(adapter(source))
        except Exception as e:
            # log error, continue
            pass
    return items
```

**Step 4: Run — verify pass**

**Step 5: Commit**

```bash
git add herald/collect.py tests/v2/test_collect.py
git commit -m "feat(v2): collect stage — RSS/HN/Tavily adapters"
```

---

## Task 7: Ingest Stage

**Files:**
- Create: `herald/ingest.py`
- Create: `tests/v2/test_ingest.py`

This is the core UPSERT logic: RawItem → canonical URL → UPSERT article → insert mentions → assign topics.

**Step 1: Write failing tests**

```python
# tests/v2/test_ingest.py (key tests)

def test_ingest_new_article(tmp_db):
    """New article creates row with correct fields."""
    item = RawItem(url="https://example.com/post", title="Test Post",
                   source_id="hn", points=100)
    result = ingest_items(tmp_db, [item], sources)
    assert result.articles_new == 1
    row = tmp_db.execute("SELECT url_canonical, title FROM articles").fetchone()
    assert row[0] == "https://example.com/post"


def test_ingest_duplicate_url_updates(tmp_db):
    """Same canonical URL → UPSERT updates points/score."""
    item1 = RawItem(url="https://example.com/post?ref=x", title="Test", source_id="hn", points=50)
    item2 = RawItem(url="https://example.com/post?utm_source=y", title="Test", source_id="rss1", points=200)
    ingest_items(tmp_db, [item1], sources)
    result = ingest_items(tmp_db, [item2], sources)
    assert result.articles_updated == 1
    points = tmp_db.execute("SELECT points FROM articles").fetchone()[0]
    assert points == 200  # max(50, 200)


def test_ingest_creates_mention(tmp_db):
    """Each ingest creates a mention row."""
    item = RawItem(url="https://example.com/post", title="Test", source_id="hn", points=10)
    ingest_items(tmp_db, [item], sources)
    row = tmp_db.execute("SELECT source_id, points FROM mentions").fetchone()
    assert row == ("hn", 10)


def test_ingest_assigns_topics(tmp_db):
    """Topics extracted from title are stored in article_topics."""
    item = RawItem(url="https://x.com/p", title="New PyTorch release for AI training",
                   source_id="hn", points=0)
    ingest_items(tmp_db, [item], sources, topic_rules={"ai": ["pytorch", "ai"]})
    topics = tmp_db.execute("SELECT topic FROM article_topics").fetchall()
    assert ("ai",) in topics
```

**Step 2: Run — verify fail**

**Step 3: Implement ingest.py**

```python
# herald/ingest.py
"""Stage 2: Normalize, score, UPSERT into SQLite."""
from herald.db import Database
from herald.models import RawItem, Source
from herald.url import canonicalize_url
from herald.scoring import article_score_base
from herald.ulid import generate_ulid

@dataclass
class IngestResult:
    articles_new: int = 0
    articles_updated: int = 0

def ingest_items(
    db: Database,
    items: list[RawItem],
    sources: dict[str, Source],
    topic_rules: dict | None = None,
) -> IngestResult:
    result = IngestResult()
    now = int(time.time())

    with db.transaction():
        for item in items:
            source = sources[item.source_id]
            url_canonical = canonicalize_url(item.url)
            score = article_score_base(
                source.weight, item.points, 0.0,
                is_release=_detect_release(item.title))

            # UPSERT article
            cursor = db.execute("""
                INSERT INTO articles (id, url_original, url_canonical, title,
                    origin_source_id, published_at, collected_at, points,
                    story_type, score_base, scored_at, extra)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url_canonical) DO UPDATE SET
                    points = max(articles.points, excluded.points),
                    score_base = excluded.score_base,
                    scored_at = excluded.scored_at
                RETURNING id, changes()
            """, (generate_ulid(), item.url, url_canonical, item.title,
                  item.source_id, item.published_at, now, item.points,
                  _detect_type(item.title), score, now, None))

            row = cursor.fetchone()
            article_id = row[0]
            is_new = row[1] == 0  # changes()=0 means INSERT, not UPDATE

            if is_new:
                result.articles_new += 1
            else:
                result.articles_updated += 1

            # Insert mention
            db.execute("""
                INSERT OR IGNORE INTO mentions (article_id, source_id, url, points, discovered_at)
                VALUES (?, ?, ?, ?, ?)
            """, (article_id, item.source_id, item.url, item.points, now))

            # Assign topics
            if topic_rules:
                _assign_topics(db, article_id, item.title, topic_rules)

    return result
```

**Step 4: Run — verify pass**

**Step 5: Commit**

```bash
git add herald/ingest.py tests/v2/test_ingest.py
git commit -m "feat(v2): ingest stage — UPSERT, mentions, topic assignment"
```

---

## Task 8: Topics Extraction

**Files:**
- Create: `herald/topics.py`
- Create: `tests/v2/test_topics.py`

Reuse `pipeline/topics.py` rule engine (Rule, TopicGroup, match_topic_group). Wrap in a simpler API for v2.

**Step 1: Write failing tests**

Test `extract_topics(title, rules)` returns matching topic names. Test with regex rules, multi-word, filter rules. Port key tests from `tests/test_topics.py`.

**Step 2: Run — verify fail**

**Step 3: Implement topics.py**

Thin wrapper around v1 logic:
```python
def extract_topics(title: str, topic_rules: dict) -> list[str]:
    """Return list of matching topic names for a title."""
```

**Step 4: Run — verify pass**

**Step 5: Commit**

```bash
git add herald/topics.py tests/v2/test_topics.py
git commit -m "feat(v2): topic extraction engine"
```

---

## Task 9: Clustering Algorithm

**Files:**
- Create: `herald/cluster.py`
- Create: `tests/v2/test_cluster.py`

This is the most complex task. Reference: design doc Section 4.

**Step 1: Write failing tests**

```python
# tests/v2/test_cluster.py (key tests)

def test_create_story_from_single_article(tmp_db):
    """Unclustered article creates a new story."""
    _insert_article(tmp_db, "a1", "New Python 3.14 features announced", "hn")
    result = cluster(tmp_db, ClusterConfig())
    stories = tmp_db.execute("SELECT id, title FROM stories").fetchall()
    assert len(stories) == 1
    assert stories[0][1] == "New Python 3.14 features announced"


def test_join_similar_articles(tmp_db):
    """Two articles with similar titles join same story."""
    _insert_article(tmp_db, "a1", "Python 3.14 released with new features", "hn", topic="python")
    cluster(tmp_db, ClusterConfig())
    _insert_article(tmp_db, "a2", "Python 3.14 released with exciting new features", "rss1", topic="python")
    cluster(tmp_db, ClusterConfig())
    stories = tmp_db.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
    assert stories == 1  # both in same story


def test_different_topics_no_merge(tmp_db):
    """Articles with no topic overlap stay separate."""
    _insert_article(tmp_db, "a1", "Python 3.14 released today", "hn", topic="python")
    _insert_article(tmp_db, "a2", "Kubernetes 2.0 released today", "hn", topic="kubernetes")
    cluster(tmp_db, ClusterConfig())
    stories = tmp_db.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
    assert stories == 2


def test_version_guard_prevents_merge(tmp_db):
    """Different version numbers prevent merge."""
    _insert_article(tmp_db, "a1", "iOS 18.1 update brings new features", "hn", topic="apple")
    cluster(tmp_db, ClusterConfig())
    _insert_article(tmp_db, "a2", "iOS 18.2 update brings new features", "rss1", topic="apple")
    cluster(tmp_db, ClusterConfig())
    stories = tmp_db.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
    assert stories == 2


def test_short_title_creates_own_story(tmp_db):
    """Title with <4 words creates standalone story."""
    _insert_article(tmp_db, "a1", "Release notes", "hn", topic="misc")
    _insert_article(tmp_db, "a2", "Release notes updated", "rss1", topic="misc")
    cluster(tmp_db, ClusterConfig())
    stories = tmp_db.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
    assert stories == 2  # no merge (too short)


def test_canonical_reelection(tmp_db):
    """Higher weight source becomes canonical."""
    _insert_source(tmp_db, "blog", weight=0.1)
    _insert_source(tmp_db, "reuters", weight=0.8)
    _insert_article(tmp_db, "a1", "Major security breach at Acme Corp", "blog", topic="security")
    cluster(tmp_db, ClusterConfig())
    _insert_article(tmp_db, "a2", "Major security breach reported at Acme Corp", "reuters", topic="security")
    cluster(tmp_db, ClusterConfig())
    canonical = tmp_db.execute("SELECT canonical_article_id FROM stories").fetchone()[0]
    assert canonical == "a2"  # reuters wins


def test_canonical_hysteresis(tmp_db):
    """Small weight difference doesn't trigger reelection (delta < 0.1)."""
    _insert_source(tmp_db, "s1", weight=0.30)
    _insert_source(tmp_db, "s2", weight=0.35)  # diff = 0.05 < delta 0.1
    _insert_article(tmp_db, "a1", "New AI model released by OpenAI", "s1", topic="ai")
    cluster(tmp_db, ClusterConfig())
    _insert_article(tmp_db, "a2", "New AI model released by OpenAI today", "s2", topic="ai")
    cluster(tmp_db, ClusterConfig())
    canonical = tmp_db.execute("SELECT canonical_article_id FROM stories").fetchone()[0]
    assert canonical == "a1"  # s1 stays (hysteresis)


def test_story_score_recomputed(tmp_db):
    """Story score updated when article joins."""
    _insert_article(tmp_db, "a1", "Rust 2.0 announced with major changes", "hn", topic="rust", points=500)
    cluster(tmp_db, ClusterConfig())
    score_before = tmp_db.execute("SELECT score FROM stories").fetchone()[0]
    _insert_article(tmp_db, "a2", "Rust 2.0 announced with breaking changes", "rss1", topic="rust", points=100)
    cluster(tmp_db, ClusterConfig())
    score_after = tmp_db.execute("SELECT score FROM stories").fetchone()[0]
    assert score_after > score_before  # coverage bonus


def test_new_story_added_to_candidates(tmp_db):
    """Story created mid-run is available for later articles."""
    _insert_article(tmp_db, "a1", "GraphQL federation spec version 3 released", "hn", topic="graphql")
    _insert_article(tmp_db, "a2", "GraphQL federation spec version 3 is here", "rss1", topic="graphql")
    cluster(tmp_db, ClusterConfig())
    stories = tmp_db.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
    assert stories == 1  # a2 joined a1's story


def test_deactivate_stale(tmp_db):
    """Stories older than max_time_gap_days become inactive."""
    old_ts = int(time.time()) - 8 * 86400  # 8 days ago
    _insert_article(tmp_db, "a1", "Old news from last week", "hn", topic="misc", collected_at=old_ts)
    cluster(tmp_db, ClusterConfig())
    # manually set last_updated to old
    tmp_db.execute("UPDATE stories SET last_updated=?", (old_ts,))
    cluster(tmp_db, ClusterConfig())  # runs deactivate at end
    status = tmp_db.execute("SELECT status FROM stories").fetchone()[0]
    assert status == "inactive"
```

**Step 2: Run — verify fail**

**Step 3: Implement cluster.py**

Full implementation per design doc Section 4 with all 5 guards, join_story, create_story, canonical re-election with hysteresis, story_topics sync (top-5 cap), deactivate_stale, in-memory candidates update.

Key functions:
- `normalize_title(title)` — strip prefixes/suffixes, lowercase, collapse whitespace
- `shared_tokens(a, b)` — count shared non-stopword tokens
- `has_conflicting_numbers(a, b)` — check version/number mismatch
- `cluster(db, config)` → `ClusterResult`
- `recluster(db, since_days, config)` — detach + cleanup + cluster

**Step 4: Run — verify pass**

**Step 5: Commit**

```bash
git add herald/cluster.py tests/v2/test_cluster.py
git commit -m "feat(v2): clustering — 5 guards, canonical hysteresis, story lifecycle"
```

---

## Task 10: Project Stage (Brief Generation)

**Files:**
- Create: `herald/project.py`
- Create: `tests/v2/test_project.py`

**Step 1: Write failing tests**

Test `generate_brief(db, limit)` returns markdown string with:
- YAML frontmatter (date, story_count, source_count)
- Stories grouped by top topic, sorted by score
- Each story: title, source count, article list
- FTS search: `search_articles(db, query)` returns matches

**Step 2: Run — verify fail**

**Step 3: Implement project.py**

```python
# herald/project.py
"""Stage 4: Project — generate markdown briefs from SQLite."""

def generate_brief(db: Database, limit: int = 20) -> str:
    """Top stories as markdown with YAML frontmatter."""
    stories = db.execute("""
        SELECT s.id, s.title, s.score, s.story_type, s.first_seen,
               COUNT(sa.article_id) as article_count
        FROM stories s
        JOIN story_articles sa ON sa.story_id = s.id
        WHERE s.status = 'active'
        GROUP BY s.id
        ORDER BY s.score DESC
        LIMIT ?
    """, (limit,)).fetchall()
    # ... format as markdown with YAML frontmatter

def search_articles(db: Database, query: str, limit: int = 20) -> list[dict]:
    """FTS5 search across article titles."""
    return db.execute("""
        SELECT a.id, a.title, a.url_canonical, highlight(articles_fts, 0, '<b>', '</b>') as snippet
        FROM articles_fts
        JOIN articles a ON a.rowid = articles_fts.rowid
        WHERE articles_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """, (query, limit)).fetchall()

def story_detail(db: Database, story_id: str) -> dict:
    """Full story with all articles."""

def topic_stories(db: Database, topic: str, limit: int = 10) -> list[dict]:
    """Stories for a topic, sorted by score."""
```

**Step 4: Run — verify pass**

**Step 5: Commit**

```bash
git add herald/project.py tests/v2/test_project.py
git commit -m "feat(v2): project stage — brief generation, search, topic queries"
```

---

## Task 11: CLI

**Files:**
- Create: `herald/cli.py`
- Create: `herald/__main__.py`
- Create: `tests/v2/test_cli.py`

**Step 1: Write failing tests**

Test CLI argument parsing for each command. Test `--format json` produces valid JSON envelope. Test `--help` works.

```python
# tests/v2/test_cli.py
import json
from herald.cli import parse_args, main

def test_parse_run():
    args = parse_args(["run"])
    assert args.command == "run"

def test_parse_brief_limit():
    args = parse_args(["brief", "--limit", "5"])
    assert args.command == "brief"
    assert args.limit == 5

def test_parse_search():
    args = parse_args(["search", "python release"])
    assert args.command == "search"
    assert args.query == "python release"

def test_parse_json_flag():
    args = parse_args(["stories", "--json"])
    assert args.format == "json"

def test_parse_format():
    args = parse_args(["brief", "--format", "json"])
    assert args.format == "json"
```

**Step 2: Run — verify fail**

**Step 3: Implement cli.py**

argparse with subcommands. Each command calls the relevant module function.

```python
# herald/cli.py
"""Herald v2 CLI — structured news intelligence."""
import argparse
import json
import sys
import time

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="herald", description="News intelligence CLI")
    parser.add_argument("--format", choices=["md", "json"], default="md")
    parser.add_argument("--json", action="store_const", const="json", dest="format")

    sub = parser.add_subparsers(dest="command", required=True)

    # herald run
    sub.add_parser("run", help="Collect + ingest + cluster + project")

    # herald brief
    p = sub.add_parser("brief", help="Show latest brief")
    p.add_argument("--limit", type=int, default=20)

    # herald search
    p = sub.add_parser("search", help="Full-text search")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=20)

    # herald topic
    p = sub.add_parser("topic", help="Stories for topic")
    p.add_argument("name")
    p.add_argument("--limit", type=int, default=10)

    # herald topics
    sub.add_parser("topics", help="List all topics")

    # herald story
    p = sub.add_parser("story", help="Story detail")
    p.add_argument("id")

    # herald stories
    p = sub.add_parser("stories", help="Top stories")
    p.add_argument("--limit", type=int, default=20)

    # herald article
    p = sub.add_parser("article", help="Article detail")
    p.add_argument("id")

    # herald sources
    sub.add_parser("sources", help="List sources")

    # herald source add/remove
    p = sub.add_parser("source", help="Manage sources")
    source_sub = p.add_subparsers(dest="action", required=True)
    add_p = source_sub.add_parser("add")
    add_p.add_argument("url")
    add_p.add_argument("--name")
    add_p.add_argument("--weight", type=float, default=0.2)
    add_p.add_argument("--category", default="community")
    rm_p = source_sub.add_parser("remove")
    rm_p.add_argument("id")

    # herald status
    sub.add_parser("status", help="Database stats and health")

    # herald config
    p = sub.add_parser("config", help="Config management")
    p.add_argument("action", choices=["show", "edit"])

    # herald init
    p = sub.add_parser("init", help="Initialize Herald")
    p.add_argument("preset", nargs="?", default="ai-engineering")

    # herald schedule
    p = sub.add_parser("schedule", help="Scheduler management")
    p.add_argument("action", choices=["install", "uninstall", "status"])

    # herald recluster
    p = sub.add_parser("recluster", help="Rebuild clusters")
    p.add_argument("--since", type=int, default=7, help="Days to recluster")

    return parser.parse_args(argv)
```

**Step 4: Implement __main__.py**

```python
# herald/__main__.py
from herald.cli import main
main()
```

**Step 5: Run — verify pass**

**Step 6: Commit**

```bash
git add herald/cli.py herald/__main__.py tests/v2/test_cli.py
git commit -m "feat(v2): CLI with argparse — all commands from design"
```

---

## Task 12: Pipeline Orchestrator

**Files:**
- Modify: `herald/cli.py` (wire `run` command)
- Create: `herald/pipeline.py`
- Create: `tests/v2/test_pipeline.py`

**Step 1: Write failing test**

```python
def test_pipeline_run_end_to_end(tmp_db, mock_http):
    """Full pipeline: collect → ingest → cluster → project."""
    config = load_test_config()
    result = run_pipeline(tmp_db, config)
    assert result.articles_new > 0
    assert result.brief is not None
    # Verify pipeline_runs table updated
    run = tmp_db.execute("SELECT * FROM pipeline_runs ORDER BY id DESC LIMIT 1").fetchone()
    assert run is not None
```

**Step 2: Run — verify fail**

**Step 3: Implement pipeline.py**

```python
# herald/pipeline.py
"""Full pipeline orchestrator: collect → ingest → cluster → project."""

@dataclass
class PipelineResult:
    articles_new: int = 0
    articles_updated: int = 0
    stories_created: int = 0
    stories_updated: int = 0
    brief: str | None = None
    error: str | None = None

def run_pipeline(db: Database, config: HeraldConfig) -> PipelineResult:
    started_at = int(time.time())
    try:
        # Stage 1: Collect
        raw_items = collect_all(config.sources)

        # Stage 2: Ingest
        sources_map = {s.id: s for s in config.sources}
        ingest_result = ingest_items(db, raw_items, sources_map, config.topics)

        # Stage 3: Cluster
        cluster_result = cluster(db, config.clustering)

        # Stage 4: Project
        brief = generate_brief(db)

        # Record pipeline run
        db.execute("""INSERT INTO pipeline_runs
            (started_at, finished_at, articles_new, articles_updated,
             stories_created, stories_updated)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (started_at, int(time.time()),
             ingest_result.articles_new, ingest_result.articles_updated,
             cluster_result.stories_created, cluster_result.stories_updated))

        return PipelineResult(
            articles_new=ingest_result.articles_new,
            articles_updated=ingest_result.articles_updated,
            stories_created=cluster_result.stories_created,
            stories_updated=cluster_result.stories_updated,
            brief=brief)
    except Exception as e:
        db.execute("INSERT INTO pipeline_runs (started_at, finished_at, error) VALUES (?, ?, ?)",
                   (started_at, int(time.time()), str(e)))
        return PipelineResult(error=str(e))
```

**Step 4: Run — verify pass**

**Step 5: Commit**

```bash
git add herald/pipeline.py tests/v2/test_pipeline.py
git commit -m "feat(v2): pipeline orchestrator — end-to-end run"
```

---

## Task 13: Slash Commands & Skill

**Files:**
- Create: `commands/herald.md`
- Create: `commands/herald-topic.md`
- Create: `commands/herald-search.md`
- Create: `commands/herald-story.md`
- Create: `commands/herald-run.md`
- Update: `skills/news-digest/SKILL.md`

**Step 1: Write slash commands**

Each command is a thin wrapper calling CLI with `--format md`. Example:

```markdown
---
name: herald
description: Show latest news brief
allowed-tools:
  - Bash
---

Run the herald brief command:

\```bash
cd $HERALD_ROOT && python -m herald brief --format md --limit 10
\```

Show the output to the user directly.
```

Similar pattern for `/herald-topic <name>`, `/herald-search <query>`, `/herald-story <id>`, `/herald-run`.

**Step 2: Update SKILL.md**

Update ambient skill to reference v2 commands and capabilities.

**Step 3: Commit**

```bash
git add commands/ skills/
git commit -m "feat(v2): slash commands and skill — thin CLI wrappers"
```

---

## Task 14: Init & Setup

**Files:**
- Modify: `herald/cli.py` (wire `init` command)
- Create: `herald/init.py`
- Create: `tests/v2/test_init.py`

**Step 1: Write failing test**

```python
def test_init_creates_db_and_config(tmp_path):
    init_herald(tmp_path, preset="ai-engineering")
    assert (tmp_path / "herald.db").exists()
    assert (tmp_path / "config.yaml").exists()
    # Verify sources seeded
    db = Database(tmp_path / "herald.db")
    sources = db.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    assert sources > 0
```

**Step 2: Run — verify fail**

**Step 3: Implement init.py**

- Copy preset YAML to user config dir
- Create SQLite database (schema auto-applied)
- Seed sources table from config
- Print setup summary

**Step 4: Run — verify pass**

**Step 5: Commit**

```bash
git add herald/init.py tests/v2/test_init.py
git commit -m "feat(v2): herald init — database creation and config seeding"
```

---

## Task 15: Integration Test & Cleanup

**Files:**
- Create: `tests/v2/test_integration.py`
- Update: `herald/__init__.py` (version)

**Step 1: Write integration test**

```python
def test_full_lifecycle(tmp_path, mock_http):
    """init → run → brief → search → story → recluster."""
    # 1. Init
    init_herald(tmp_path, preset="ai-engineering")
    db = Database(tmp_path / "herald.db")
    config = load_config(tmp_path / "config.yaml")

    # 2. Run pipeline
    result = run_pipeline(db, config)
    assert result.error is None
    assert result.articles_new > 0

    # 3. Brief
    brief = generate_brief(db)
    assert "---" in brief  # YAML frontmatter

    # 4. Search
    results = search_articles(db, "python")
    # (may or may not find results depending on mock data)

    # 5. Story detail
    story_id = db.execute("SELECT id FROM stories LIMIT 1").fetchone()[0]
    detail = story_detail(db, story_id)
    assert detail["title"]

    # 6. Recluster
    recluster(db, since_days=7, config=config.clustering)
    # No crash = success


def test_cli_json_envelope(tmp_path):
    """--format json returns stable envelope."""
    init_herald(tmp_path, preset="ai-engineering")
    # run minimal pipeline with mock data
    result = subprocess.run(
        ["python", "-m", "herald", "status", "--format", "json"],
        capture_output=True, text=True, cwd=str(tmp_path))
    data = json.loads(result.stdout)
    assert data["schema_version"] == 1
    assert "generated_at" in data
    assert "command" in data
    assert "data" in data


def test_clustering_golden(tmp_db):
    """Golden test: known articles → expected groupings."""
    articles = [
        ("a1", "Python 3.14 released with pattern matching improvements", "hn", "python"),
        ("a2", "Python 3.14 released with exciting pattern matching", "rss1", "python"),
        ("a3", "Rust 2.0 brings major breaking changes", "hn", "rust"),
        ("a4", "Kubernetes 1.32 adds new scheduling features", "hn", "kubernetes"),
        ("a5", "Rust 2.0 announced with breaking changes and new features", "rss1", "rust"),
    ]
    for aid, title, src, topic in articles:
        _insert_article(tmp_db, aid, title, src, topic=topic)
    cluster(tmp_db, ClusterConfig())
    stories = tmp_db.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
    assert stories == 3  # python(a1+a2), rust(a3+a5), k8s(a4)
    # Verify python story has 2 articles
    python_story = tmp_db.execute("""
        SELECT s.id FROM stories s
        JOIN story_articles sa ON sa.story_id = s.id
        JOIN articles a ON a.id = sa.article_id
        WHERE a.title LIKE '%Python%'
        GROUP BY s.id HAVING COUNT(*) = 2
    """).fetchone()
    assert python_story is not None
```

**Step 2: Run all v2 tests**

```bash
PYTHONPATH=. pytest tests/v2/ -v --tb=short
```

Expected: all green.

**Step 3: Set version**

```python
# herald/__init__.py
__version__ = "2.0.0"
```

**Step 4: Commit**

```bash
git add tests/v2/test_integration.py herald/__init__.py
git commit -m "feat(v2): integration test and version bump to 2.0.0"
```

---

## Dependency Graph (arbiter-corrected)

```
Task 3 (Models/ULID) ──┐
                        ├──→ Task 1 (DB) ──┐
                        ├──→ Task 2 (URL)   ├──→ Task 8 (Topics) ──→ Task 7 (Ingest) ──→ Task 9 (Clustering)
                        ├──→ Task 4 (Config)┘                                                    │
                        ├──→ Task 5 (Scoring)                                                    ▼
                        └──→ Task 6 (Collect, needs 4)    Task 14 (Init, needs 1+4) ──→ Task 12 (Pipeline)
                                                          Task 10 (Project, needs 1+9) → Task 11 (CLI)
                                                          Task 13 (Commands), Task 15 (Integration)
```

**Execution order:**
1. Task 3 (Models) — true foundation, everything imports from here
2. Tasks 1, 2, 4, 5 — parallel (DB, URL, Config, Scoring)
3. Task 6 (Collect) — depends on 3 + 4
4. Task 8 (Topics) — depends on 1
5. Task 7 (Ingest) — depends on 1, 2, 3, 5, 8
6. Task 9 (Clustering) — depends on 7
7. Tasks 10, 14 — parallel (Project needs 1+9, Init needs 1+4)
8. Tasks 11, 12 — parallel (CLI needs 10, Pipeline needs 7+9+10)
9. Tasks 13, 15 — final (Commands needs 11, Integration needs all)

**Key arbiter corrections:**
- Models (3) is the true prerequisite, not fully parallel with 1-6
- Topics (8) must come before Ingest (7) — ingest calls topic extraction
- Init (14) moved earlier (after DB + Config)
- FTS5 availability check added to Task 1

## Out of Scope (deferred)

- CI/CD pipeline configuration
- v1 deprecation/removal (after v2 stable)
- Data migration from v1 JSONL
- `pyproject.toml` — add minimal for metadata when v2 stable
