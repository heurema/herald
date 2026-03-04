"""Herald v2 Collect stage: RSS, Hacker News, and Tavily adapters."""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from herald.models import RawItem, Source


def _parse_published(value: str | None) -> int | None:
    """Convert a date string to unix timestamp. Returns None if parsing fails."""
    if not value:
        return None
    try:
        # Try ISO 8601 first
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except (ValueError, AttributeError):
        pass
    try:
        # Try RFC 2822 (common in RSS feeds)
        dt = parsedate_to_datetime(value)
        return int(dt.timestamp())
    except Exception:
        pass
    return None


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


def _post_with_retry(client: httpx.Client, url: str, *, json: dict, headers: dict, retries: int = 3) -> httpx.Response | None:
    """POST with exponential backoff (1s, 2s, 4s). Returns None on all failures."""
    delay = 1.0
    for attempt in range(retries):
        try:
            resp = client.post(url, json=json, headers=headers)
            resp.raise_for_status()
            return resp
        except Exception as exc:
            if attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
            else:
                print(f"[collect] ERROR posting {url}: {exc}", file=sys.stderr)
    return None


def fetch_rss(source: Source, *, timeout: int = 10, retries: int = 3) -> list[RawItem]:
    """Fetch and parse a single RSS/Atom feed. Returns empty list on failure."""
    import fastfeedparser

    if not source.url:
        return []

    items: list[RawItem] = []
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = _fetch_with_retry(client, source.url, retries=retries)
            if resp is None:
                return []
            if len(resp.content) > 10 * 1024 * 1024:
                print(
                    f"[collect] SKIP {source.name}: response too large ({len(resp.content)} bytes)",
                    file=sys.stderr,
                )
                return []
            content = resp.text

        result = fastfeedparser.parse(content)
        entries = getattr(result, "entries", []) or []

        for entry in entries:
            entry_url = getattr(entry, "link", None) or getattr(entry, "id", None)
            if not entry_url:
                continue
            title = getattr(entry, "title", "") or ""
            published_str = None
            for attr in ("published", "updated", "created", "pubDate"):
                val = getattr(entry, attr, None)
                if val:
                    published_str = str(val)
                    break

            items.append(RawItem(
                url=entry_url,
                title=title.strip(),
                source_id=source.id,
                published_at=_parse_published(published_str),
                points=0,
                extra=None,
            ))
    except Exception as exc:
        print(f"[collect] ERROR parsing feed {source.name} ({source.url}): {exc}", file=sys.stderr)

    return items


def fetch_hn(source: Source, *, min_points: int = 100, limit: int = 200, timeout: int = 10, retries: int = 3) -> list[RawItem]:
    """Fetch HN front-page stories via Algolia API, filter by min_points."""
    api_url = f"https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage={limit}"
    items: list[RawItem] = []

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = _fetch_with_retry(client, api_url, retries=retries)
            if resp is None:
                return []
            data = resp.json()

        for hit in data.get("hits", []):
            points = hit.get("points") or 0
            if points < min_points:
                continue
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
            title = hit.get("title") or ""
            published_str = hit.get("created_at") or None
            items.append(RawItem(
                url=url,
                title=title,
                source_id=source.id,
                published_at=_parse_published(published_str),
                points=int(points),
                extra=None,
            ))
    except Exception as exc:
        print(f"[collect] ERROR fetching HN stories: {exc}", file=sys.stderr)

    return items


def fetch_tavily(source: Source, *, queries: list[str] | None = None, timeout: int = 10, retries: int = 3) -> list[RawItem]:
    """Search via Tavily API. Returns [] silently when TAVILY_API_KEY is not set."""
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return []

    if not queries:
        queries = [source.name]

    items: list[RawItem] = []
    with httpx.Client(timeout=timeout) as client:
        for query in queries:
            try:
                payload = {"query": query, "max_results": 5, "search_depth": "basic"}
                headers = {"Authorization": f"Bearer {api_key}"}
                resp = _post_with_retry(client, "https://api.tavily.com/search", json=payload, headers=headers, retries=retries)
                if resp is None:
                    continue
                data = resp.json()
                for result in data.get("results", []):
                    url = result.get("url") or ""
                    if not url:
                        continue
                    title = result.get("title") or ""
                    published_str = result.get("published_date") or None
                    items.append(RawItem(
                        url=url,
                        title=title,
                        source_id=source.id,
                        published_at=_parse_published(published_str),
                        points=0,
                        extra=None,
                    ))
            except Exception as exc:
                print(f"[collect] ERROR Tavily query '{query}': {exc}", file=sys.stderr)

    return items


_ADAPTER_NAMES = {"rss", "hn", "tavily"}


def collect_all(
    sources: list[Source],
    *,
    adapter_map: dict[str, str] | None = None,
) -> list[RawItem]:
    """Dispatch fetch per source using adapter_map (source.id -> adapter name).

    Each source is isolated: an exception in one source does not stop others.
    adapter_map keys are source ids; values are one of 'rss', 'hn', 'tavily'.
    If adapter_map is None or a source id is not in it, defaults to 'rss'.
    """
    adapter_map = adapter_map or {}
    all_items: list[RawItem] = []
    _module = sys.modules[__name__]

    for source in sources:
        adapter_name = adapter_map.get(source.id, "rss")
        if adapter_name not in _ADAPTER_NAMES:
            print(f"[collect] WARN unknown adapter '{adapter_name}' for source '{source.id}'", file=sys.stderr)
            continue
        fetch_fn = getattr(_module, f"fetch_{adapter_name}")
        try:
            items = fetch_fn(source)
            print(f"[collect] {source.name}: {len(items)} items", file=sys.stderr)
            all_items.extend(items)
        except Exception as exc:
            print(f"[collect] ERROR source '{source.id}': {exc}", file=sys.stderr)

    return all_items
