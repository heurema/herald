"""News collector: RSS feeds, HN Algolia API, Tavily search."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
import yaml

# Parameters to strip from URLs
_STRIP_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_name", "utm_reader", "utm_brand", "utm_cid",
    "ref", "ref_src", "ref_url",
    "fbclid", "gclid", "gclsrc", "dclid",
    "mc_cid", "mc_eid",
    "_hsenc", "_hsmi",
    "mkt_tok",
    "igshid",
}


def normalize_url(url: str) -> str:
    """Strip tracker params, trailing slash, force https."""
    parsed = urlparse(url)

    # Force https
    scheme = "https" if parsed.scheme == "http" else parsed.scheme

    # Strip tracker query params; keep everything not in the strip set and not utm_*
    qs = parse_qs(parsed.query, keep_blank_values=True)
    filtered = {
        k: v
        for k, v in qs.items()
        if k.lower() not in _STRIP_PARAMS and not k.lower().startswith("utm_")
    }

    # Rebuild query string (sorted for determinism)
    new_query = urlencode(sorted((k, v[0]) for k, v in filtered.items())) if filtered else ""

    # Strip trailing slash from path (but preserve bare "/")
    path = parsed.path.rstrip("/") if parsed.path != "/" else parsed.path

    rebuilt = urlunparse((scheme, parsed.netloc, path, parsed.params, new_query, ""))
    return rebuilt


@dataclass
class RawItem:
    """Single collected news item."""
    url: str
    title: str
    source: str
    published: str
    extra: dict = field(default_factory=dict)
    collected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "source": self.source,
            "published": self.published,
            "extra": self.extra,
            "collected_at": self.collected_at,
        }


def load_config(path: str) -> dict:
    """Parse sources.yaml and return config dict."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _fetch_with_retry(client: httpx.Client, url: str, retries: int = 3) -> httpx.Response | None:
    """GET with exponential backoff (1s, 2s, 4s). Returns None on all failures."""
    delay = 1.0
    for attempt in range(retries):
        try:
            resp = client.get(url)
            resp.raise_for_status()
            return resp
        except Exception as exc:
            if attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
            else:
                print(f"[collect] ERROR fetching {url}: {exc}", file=sys.stderr)
    return None


def fetch_rss_feed(feed: dict) -> list[RawItem]:
    """Fetch and parse a single RSS/Atom feed. Returns empty list on failure."""
    import fastfeedparser

    url = feed["url"]
    source = feed["name"]
    items: list[RawItem] = []

    try:
        transport = httpx.HTTPTransport(retries=3)
        with httpx.Client(timeout=10, transport=transport, follow_redirects=True) as client:
            resp = _fetch_with_retry(client, url)
            if resp is None:
                return []
            content = resp.text

        result = fastfeedparser.parse(content)
        entries = getattr(result, "entries", []) or []

        for entry in entries:
            entry_url = getattr(entry, "link", None) or getattr(entry, "id", None)
            if not entry_url:
                continue
            title = getattr(entry, "title", "") or ""
            published = ""
            for attr in ("published", "updated", "created", "pubDate"):
                val = getattr(entry, attr, None)
                if val:
                    published = str(val)
                    break

            items.append(RawItem(
                url=entry_url,
                title=title.strip(),
                source=source,
                published=published,
            ))
    except Exception as exc:
        print(f"[collect] ERROR parsing feed {source} ({url}): {exc}", file=sys.stderr)

    return items


def fetch_hn_stories(min_points: int = 100, limit: int = 200) -> list[RawItem]:
    """Fetch HN front-page stories via Algolia API, filter by min_points."""
    api_url = f"https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage={limit}"
    items: list[RawItem] = []

    try:
        transport = httpx.HTTPTransport(retries=3)
        with httpx.Client(timeout=10, transport=transport, follow_redirects=True) as client:
            resp = _fetch_with_retry(client, api_url)
            if resp is None:
                return []
            data = resp.json()

        for hit in data.get("hits", []):
            points = hit.get("points") or 0
            if points < min_points:
                continue
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
            title = hit.get("title") or ""
            published = hit.get("created_at") or ""
            items.append(RawItem(
                url=url,
                title=title,
                source="Hacker News",
                published=published,
                extra={"points": points},
            ))
    except Exception as exc:
        print(f"[collect] ERROR fetching HN stories: {exc}", file=sys.stderr)

    return items


def fetch_tavily(queries: list[str]) -> list[RawItem]:
    """Search via Tavily API. Skips silently if TAVILY_API_KEY is not set."""
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return []

    items: list[RawItem] = []
    transport = httpx.HTTPTransport(retries=3)

    with httpx.Client(timeout=10, transport=transport) as client:
        for query in queries:
            try:
                resp = client.post(
                    "https://api.tavily.com/search",
                    json={"query": query, "max_results": 5, "search_depth": "basic"},
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                resp.raise_for_status()
                data = resp.json()
                for result in data.get("results", []):
                    url = result.get("url") or ""
                    if not url:
                        continue
                    title = result.get("title") or ""
                    published = result.get("published_date") or ""
                    items.append(RawItem(
                        url=url,
                        title=title,
                        source=f"Tavily:{query[:40]}",
                        published=published,
                    ))
            except Exception as exc:
                print(f"[collect] ERROR Tavily query '{query}': {exc}", file=sys.stderr)

    return items


def collect_all(config: dict) -> list[RawItem]:
    """Orchestrate all fetchers. Per-source isolation with try/except. Prints stats."""
    all_items: list[RawItem] = []

    # RSS feeds
    feeds = config.get("feeds", [])
    for feed in feeds:
        try:
            items = fetch_rss_feed(feed)
            print(f"[collect] {feed['name']}: {len(items)} items")
            all_items.extend(items)
        except Exception as exc:
            print(f"[collect] ERROR source '{feed.get('name')}': {exc}", file=sys.stderr)

    # HN via Algolia
    try:
        hn_items = fetch_hn_stories(min_points=100, limit=200)
        print(f"[collect] Hacker News (Algolia): {len(hn_items)} items")
        all_items.extend(hn_items)
    except Exception as exc:
        print(f"[collect] ERROR HN Algolia: {exc}", file=sys.stderr)

    # Tavily
    try:
        queries = config.get("tavily_queries", [])
        tavily_items = fetch_tavily(queries)
        print(f"[collect] Tavily: {len(tavily_items)} items")
        all_items.extend(tavily_items)
    except Exception as exc:
        print(f"[collect] ERROR Tavily: {exc}", file=sys.stderr)

    print(f"[collect] Total: {len(all_items)} items collected")
    return all_items


def write_raw_jsonl(items: list[RawItem], output_path: Path) -> None:
    """Atomic write: write to tempfile in same dir, then os.rename."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=output_path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
        os.rename(tmp_path, output_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Collect news items from configured sources.")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    parser.add_argument("--output", default=None, help="Output JSONL path")
    args = parser.parse_args()

    # Resolve config: if --config points to a config.yaml with preset field, use overlay
    if args.config:
        raw = load_config(args.config)
        if "preset" in raw or "add_feeds" in raw:
            from pipeline.config import resolve_config
            config = resolve_config(user_config_path=Path(args.config))
        else:
            config = raw
    else:
        from pipeline.config import resolve_config
        config = resolve_config()

    items = collect_all(config)

    # Normalize all URLs
    for item in items:
        item.url = normalize_url(item.url)

    if args.output:
        output_path = Path(args.output)
    else:
        from pipeline.paths import raw_dir
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        output_path = raw_dir() / f"{date}.jsonl"

    write_raw_jsonl(items, output_path)
    print(f"[collect] Written {len(items)} items to {output_path}")


if __name__ == "__main__":
    main()
