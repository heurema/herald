"""URL deduplication and title similarity for the news collector pipeline.

Three dedup layers:
  1. SHA-256 URL hash (exact URL match, persistent across runs)
  2. URL normalization (handled upstream, not repeated here)
  3. Title similarity via difflib.SequenceMatcher (catches near-duplicate headlines)
"""

from __future__ import annotations

import difflib
import hashlib
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.collect import RawItem


def _sha256(url: str) -> str:
    """Return the SHA-256 hex digest of a URL string."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp, returning a timezone-aware datetime."""
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class SeenUrls:
    """Persistent set of seen URL hashes with TTL-based pruning.

    File format (one entry per line):
        <sha256_hex> <iso_timestamp>\\n
    """

    def __init__(self, path: Path, max_age_days: int = 90) -> None:
        self._path = path
        self._max_age_days = max_age_days
        self._store: dict[str, str] = {}  # hash -> ISO timestamp
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, url: str) -> None:
        """Record a URL as seen (timestamped now)."""
        h = _sha256(url)
        self._store[h] = _now_utc().isoformat()

    def is_seen(self, url: str) -> bool:
        """Return True if the URL's hash is in the store."""
        return _sha256(url) in self._store

    def save(self) -> None:
        """Atomically write the current store to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        dir_ = self._path.parent
        fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".seen_urls_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                for h, ts in self._store.items():
                    fh.write(f"{h} {ts}\n")
            os.replace(tmp, self._path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load entries from file, pruning those older than max_age_days."""
        if not self._path.exists():
            return
        cutoff = _now_utc() - timedelta(days=self._max_age_days)
        with self._path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(" ", 1)
                if len(parts) != 2:
                    continue
                h, ts_str = parts
                try:
                    ts = _parse_ts(ts_str)
                except ValueError:
                    continue
                if ts >= cutoff:
                    self._store[h] = ts_str


# ---------------------------------------------------------------------------
# Title similarity
# ---------------------------------------------------------------------------

def is_title_duplicate(
    title: str,
    existing_titles: list[str],
    threshold: float = 0.85,
) -> bool:
    """Return True if *title* is too similar to any title in *existing_titles*.

    Uses difflib.SequenceMatcher (ratio > threshold).
    """
    t_lower = title.lower()
    for existing in existing_titles:
        ratio = difflib.SequenceMatcher(
            None, t_lower, existing.lower(), autojunk=False
        ).ratio()
        if ratio > threshold:
            return True
    return False


# ---------------------------------------------------------------------------
# Dedup pipeline
# ---------------------------------------------------------------------------

def dedup_items(items: list[RawItem], seen: SeenUrls) -> list[RawItem]:
    """Filter *items* to only those not yet seen by URL or title.

    For each item:
      1. Skip if URL is already in *seen*.
      2. Skip if title is too similar to an already-accepted title.
      3. Otherwise accept: add URL to *seen* and title to accepted list.

    Returns the list of unique (accepted) items.
    """
    accepted: list[RawItem] = []
    accepted_titles: list[str] = []

    for item in items:
        if seen.is_seen(item.url):
            continue
        if is_title_duplicate(item.title, accepted_titles):
            continue
        # Accept this item
        item.is_new = True
        seen.add(item.url)
        accepted_titles.append(item.title)
        accepted.append(item)

    return accepted
