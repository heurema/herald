"""Tests for herald/collect.py (v2 Collect stage)."""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import httpx
import pytest

# Stub fastfeedparser if not installed so import of herald.collect succeeds
if "fastfeedparser" not in sys.modules:
    _ffp = types.ModuleType("fastfeedparser")
    _ffp.parse = MagicMock()  # type: ignore[attr-defined]
    sys.modules["fastfeedparser"] = _ffp

from herald.collect import (  # noqa: E402
    _fetch_with_retry,
    collect_all,
    fetch_hn,
    fetch_rss,
    fetch_tavily,
)
from herald.models import RawItem, Source


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(content: bytes = b"", text: str = "", json_data: dict | None = None, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content if content else text.encode()
    resp.text = text if text else content.decode(errors="replace")
    if json_data is not None:
        resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


def _make_feed_entry(link=None, title="", published=None, entry_id=None) -> MagicMock:
    """Create a mock feed entry mimicking fastfeedparser entry objects."""
    entry = MagicMock(spec=[])
    entry.link = link
    entry.id = entry_id
    entry.title = title
    entry.published = published
    entry.updated = None
    entry.created = None
    entry.pubDate = None
    return entry


def _make_feed_result(entries: list) -> MagicMock:
    result = MagicMock()
    result.entries = entries
    return result


HN_JSON = {
    "hits": [
        {"objectID": "1", "title": "High Score Post", "url": "https://hn-article.com/1", "points": 200, "created_at": "2024-01-01T12:00:00Z"},
        {"objectID": "2", "title": "Low Score Post", "url": "https://hn-article.com/2", "points": 50, "created_at": "2024-01-01T11:00:00Z"},
        {"objectID": "3", "title": "No URL Post", "url": None, "points": 300, "created_at": "2024-01-01T10:00:00Z"},
    ]
}

TAVILY_JSON = {
    "results": [
        {"url": "https://result.com/1", "title": "Tavily Result 1", "published_date": "2024-01-01"},
        {"url": "https://result.com/2", "title": "Tavily Result 2", "published_date": None},
        {"url": "", "title": "No URL Result"},
    ]
}


# ---------------------------------------------------------------------------
# fetch_rss tests
# ---------------------------------------------------------------------------

def test_rss_returns_raw_items_with_source_id():
    source = Source(id="test-rss", name="Test RSS", url="https://example.com/feed.xml")
    mock_resp = _make_response(text="<rss/>")
    entries = [
        _make_feed_entry(link="https://example.com/article-1", title="Article One", published="Mon, 01 Jan 2024 12:00:00 +0000"),
        _make_feed_entry(link="https://example.com/article-2", title="Article Two"),
    ]
    mock_feed_result = _make_feed_result(entries)

    with patch("httpx.Client") as mock_client_cls, \
         patch("fastfeedparser.parse", return_value=mock_feed_result):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_resp

        items = fetch_rss(source)

    assert len(items) == 2
    for item in items:
        assert isinstance(item, RawItem)
        assert item.source_id == "test-rss"
    assert items[0].url == "https://example.com/article-1"
    assert items[0].title == "Article One"


def test_rss_source_id_matches_source():
    """source_id must equal source.id, not a hardcoded string."""
    source = Source(id="my-custom-id", name="My Feed", url="https://example.com/feed.xml")
    mock_resp = _make_response(text="<rss/>")
    entries = [
        _make_feed_entry(link="https://example.com/article-1", title="A"),
    ]
    mock_feed_result = _make_feed_result(entries)

    with patch("httpx.Client") as mock_client_cls, \
         patch("fastfeedparser.parse", return_value=mock_feed_result):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_resp

        items = fetch_rss(source)

    assert all(item.source_id == "my-custom-id" for item in items)


def test_rss_no_url_returns_empty():
    """Source without url returns empty list."""
    source = Source(id="no-url-src", name="No URL", url=None)
    items = fetch_rss(source)
    assert items == []


def test_rss_http_failure_returns_empty():
    """When HTTP fails and retries exhausted, returns []."""
    source = Source(id="err-rss", name="Error Feed", url="https://bad.example.com/feed.xml")

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = httpx.ConnectError("connection refused")

        with patch("time.sleep"):
            items = fetch_rss(source)

    assert items == []


def test_rss_entry_no_url_skipped():
    """RSS entries without link or id are silently skipped."""
    source = Source(id="rss-partial", name="Partial Feed", url="https://example.com/feed.xml")
    mock_resp = _make_response(text="<rss/>")
    entries = [
        _make_feed_entry(link="https://example.com/ok", title="Has Link"),
        _make_feed_entry(link=None, entry_id=None, title="No Link No Id"),
    ]
    mock_feed_result = _make_feed_result(entries)

    with patch("httpx.Client") as mock_client_cls, \
         patch("fastfeedparser.parse", return_value=mock_feed_result):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_resp

        items = fetch_rss(source)

    assert len(items) == 1
    assert items[0].url == "https://example.com/ok"


def test_rss_oversized_response_returns_empty():
    """Responses over 10MB are rejected without raising."""
    source = Source(id="big-rss", name="Big Feed", url="https://example.com/huge.xml")
    big_content = b"x" * (10 * 1024 * 1024 + 1)
    mock_resp = _make_response(content=big_content)

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_resp

        items = fetch_rss(source)

    assert items == []


# ---------------------------------------------------------------------------
# fetch_hn tests
# ---------------------------------------------------------------------------

def test_hn_returns_raw_items_with_source_id():
    source = Source(id="hn", name="Hacker News")
    mock_resp = _make_response(json_data=HN_JSON)

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_resp

        items = fetch_hn(source)

    # Only items with points >= 100 (default min_points)
    assert len(items) == 2
    for item in items:
        assert isinstance(item, RawItem)
        assert item.source_id == "hn"


def test_hn_source_id_matches_source():
    """source_id must be source.id, not hardcoded 'Hacker News'."""
    source = Source(id="custom-hn-id", name="Hacker News")
    mock_resp = _make_response(json_data=HN_JSON)

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_resp

        items = fetch_hn(source)

    assert all(item.source_id == "custom-hn-id" for item in items)


def test_hn_points_populated():
    """points field must be set from the HN API response."""
    source = Source(id="hn", name="Hacker News")
    mock_resp = _make_response(json_data=HN_JSON)

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_resp

        items = fetch_hn(source)

    points_values = {item.points for item in items}
    assert 200 in points_values
    assert 300 in points_values


def test_hn_no_url_falls_back_to_hn_permalink():
    """Items without url get a news.ycombinator.com permalink."""
    source = Source(id="hn", name="Hacker News")
    hn_data = {
        "hits": [
            {"objectID": "99", "title": "Ask HN", "url": None, "points": 500, "created_at": None},
        ]
    }
    mock_resp = _make_response(json_data=hn_data)

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_resp

        items = fetch_hn(source)

    assert len(items) == 1
    assert "99" in items[0].url
    assert "ycombinator" in items[0].url


def test_hn_http_failure_returns_empty():
    source = Source(id="hn", name="Hacker News")

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = httpx.ConnectError("fail")

        with patch("time.sleep"):
            items = fetch_hn(source)

    assert items == []


# ---------------------------------------------------------------------------
# fetch_tavily tests
# ---------------------------------------------------------------------------

def test_tavily_returns_empty_when_no_api_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    source = Source(id="tavily-src", name="Tavily")
    items = fetch_tavily(source)
    assert items == []


def test_tavily_returns_items_when_key_set(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    source = Source(id="tavily-src", name="Tavily Search")
    mock_resp = _make_response(json_data=TAVILY_JSON)

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_resp

        items = fetch_tavily(source, queries=["test query"])

    # Only items with non-empty url
    assert len(items) == 2
    for item in items:
        assert isinstance(item, RawItem)
        assert item.source_id == "tavily-src"


def test_tavily_source_id_matches_source(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    source = Source(id="my-tavily", name="My Tavily")
    mock_resp = _make_response(json_data=TAVILY_JSON)

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_resp

        items = fetch_tavily(source, queries=["q"])

    assert all(item.source_id == "my-tavily" for item in items)


def test_tavily_skips_results_with_no_url(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    source = Source(id="tv", name="Tavily")
    mock_resp = _make_response(json_data=TAVILY_JSON)

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_resp

        items = fetch_tavily(source, queries=["q"])

    urls = [item.url for item in items]
    assert "" not in urls
    assert all(url for url in urls)


# ---------------------------------------------------------------------------
# collect_all tests
# ---------------------------------------------------------------------------

def test_collect_all_dispatches_by_adapter_map():
    """collect_all uses adapter_map to dispatch each source."""
    source_rss = Source(id="blog", name="Blog", url="https://blog.example.com/feed.xml")
    source_hn = Source(id="hn", name="Hacker News")

    rss_item = RawItem(url="https://blog.example.com/a", title="A", source_id="blog")
    hn_item = RawItem(url="https://hn.example.com/b", title="B", source_id="hn", points=150)

    with patch("herald.collect.fetch_rss", return_value=[rss_item]) as mock_rss, \
         patch("herald.collect.fetch_hn", return_value=[hn_item]) as mock_hn:

        items = collect_all(
            [source_rss, source_hn],
            adapter_map={"blog": "rss", "hn": "hn"},
        )

    mock_rss.assert_called_once_with(source_rss)
    mock_hn.assert_called_once_with(source_hn)
    assert len(items) == 2


def test_collect_all_aggregates_results():
    """collect_all returns items from all sources combined."""
    sources = [
        Source(id="s1", name="Source 1", url="https://s1.example.com/feed.xml"),
        Source(id="s2", name="Source 2", url="https://s2.example.com/feed.xml"),
    ]
    item1 = RawItem(url="https://s1.example.com/a", title="A", source_id="s1")
    item2 = RawItem(url="https://s2.example.com/b", title="B", source_id="s2")

    with patch("herald.collect.fetch_rss", side_effect=[[item1], [item2]]):
        items = collect_all(sources, adapter_map={"s1": "rss", "s2": "rss"})

    assert len(items) == 2
    urls = {item.url for item in items}
    assert "https://s1.example.com/a" in urls
    assert "https://s2.example.com/b" in urls


def test_collect_all_defaults_to_rss():
    """Sources not in adapter_map default to rss adapter."""
    source = Source(id="unlisted", name="Unlisted", url="https://example.com/feed.xml")
    item = RawItem(url="https://example.com/x", title="X", source_id="unlisted")

    with patch("herald.collect.fetch_rss", return_value=[item]) as mock_rss:
        items = collect_all([source])  # no adapter_map

    mock_rss.assert_called_once_with(source)
    assert len(items) == 1


# ---------------------------------------------------------------------------
# Fault isolation tests
# ---------------------------------------------------------------------------

def test_collect_all_fault_isolation_one_source_raises():
    """A source that raises during fetch must not stop other sources."""
    source_ok = Source(id="ok", name="OK Source", url="https://ok.example.com/feed.xml")
    source_bad = Source(id="bad", name="Bad Source", url="https://bad.example.com/feed.xml")
    good_item = RawItem(url="https://ok.example.com/a", title="Good", source_id="ok")

    def _fetch_side_effect(source):
        if source.id == "bad":
            raise RuntimeError("network error")
        return [good_item]

    with patch("herald.collect.fetch_rss", side_effect=_fetch_side_effect):
        items = collect_all(
            [source_bad, source_ok],
            adapter_map={"ok": "rss", "bad": "rss"},
        )

    assert len(items) == 1
    assert items[0].source_id == "ok"


def test_collect_all_fault_all_sources_fail_returns_empty():
    """When all sources fail, returns empty list without raising."""
    sources = [
        Source(id="s1", name="S1", url="https://s1.example.com/feed.xml"),
        Source(id="s2", name="S2", url="https://s2.example.com/feed.xml"),
    ]

    with patch("herald.collect.fetch_rss", side_effect=RuntimeError("fail")):
        items = collect_all(sources, adapter_map={"s1": "rss", "s2": "rss"})

    assert items == []


# ---------------------------------------------------------------------------
# _fetch_with_retry tests
# ---------------------------------------------------------------------------

def test_retry_returns_none_after_all_failures():
    """_fetch_with_retry returns None when all attempts fail."""
    mock_client = MagicMock()
    mock_client.get.side_effect = httpx.ConnectError("fail")

    with patch("time.sleep"):
        result = _fetch_with_retry(mock_client, "https://example.com", retries=3)

    assert result is None


def test_retry_exponential_backoff_sleep_calls():
    """_fetch_with_retry sleeps with exponential backoff (1s, 2s for retries=3)."""
    mock_client = MagicMock()
    mock_client.get.side_effect = httpx.ConnectError("fail")

    with patch("time.sleep") as mock_sleep:
        result = _fetch_with_retry(mock_client, "https://example.com", retries=3)

    assert result is None
    assert mock_sleep.call_count == 2
    sleep_args = [call.args[0] for call in mock_sleep.call_args_list]
    assert sleep_args[0] == 1.0
    assert sleep_args[1] == 2.0


def test_retry_succeeds_on_first_attempt():
    """_fetch_with_retry returns response when first attempt succeeds."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_client.get.return_value = mock_resp

    with patch("time.sleep") as mock_sleep:
        result = _fetch_with_retry(mock_client, "https://example.com", retries=3)

    assert result is mock_resp
    mock_sleep.assert_not_called()


def test_retry_succeeds_on_second_attempt():
    """_fetch_with_retry retries and succeeds on the second attempt."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_client.get.side_effect = [httpx.ConnectError("first fail"), mock_resp]

    with patch("time.sleep") as mock_sleep:
        result = _fetch_with_retry(mock_client, "https://example.com", retries=3)

    assert result is mock_resp
    assert mock_sleep.call_count == 1
