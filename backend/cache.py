"""SQLite cache for enriched rows, keyed by (domain, seller context).

Falls back to an in-memory dict if the database file can't be opened
(e.g. a read-only filesystem), so caching problems never break enrichment.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import threading
import time
from typing import Dict, Optional, Tuple

from settings import CACHE_TTL_HOURS, DB_PATH

log = logging.getLogger("miniclay.cache")


# Bump when the row schema or outreach style changes so stale cached rows aren't served.
CACHE_VERSION = "v5"


def cache_key(domain: str, seller_context: str) -> str:
    normalized = re.sub(r"\s+", " ", seller_context.strip().lower())
    return hashlib.sha256(f"{CACHE_VERSION}|{domain.lower()}|{normalized}".encode()).hexdigest()[:32]


class EnrichmentCache:
    def __init__(self, path: str = DB_PATH):
        self._lock = threading.Lock()
        self._memory: Dict[str, Tuple[float, dict]] = {}
        self._conn: Optional[sqlite3.Connection] = None
        try:
            self._conn = sqlite3.connect(path, check_same_thread=False)
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS enrichments ("
                " key TEXT PRIMARY KEY, domain TEXT NOT NULL, payload TEXT NOT NULL, created_at REAL NOT NULL)"
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            log.warning("SQLite cache unavailable (%s); using in-memory cache", exc)
            self._conn = None

    def get(self, key: str, max_age_hours: float = CACHE_TTL_HOURS) -> Optional[dict]:
        cutoff = time.time() - max_age_hours * 3600
        with self._lock:
            if self._conn is None:
                hit = self._memory.get(key)
                return dict(hit[1]) if hit and hit[0] >= cutoff else None
            row = self._conn.execute(
                "SELECT payload, created_at FROM enrichments WHERE key = ?", (key,)
            ).fetchone()
        if not row or row[1] < cutoff:
            return None
        return json.loads(row[0])

    def set(self, key: str, domain: str, payload: dict) -> None:
        with self._lock:
            if self._conn is None:
                self._memory[key] = (time.time(), payload)
                return
            self._conn.execute(
                "INSERT OR REPLACE INTO enrichments (key, domain, payload, created_at) VALUES (?, ?, ?, ?)",
                (key, domain, json.dumps(payload), time.time()),
            )
            self._conn.commit()
