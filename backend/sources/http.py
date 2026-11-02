from __future__ import annotations

import logging
from typing import Optional, Tuple

import httpx

from settings import BROWSER_HEADERS, PAGE_TIMEOUT

log = logging.getLogger("miniclay.http")

MAX_HTML_CHARS = 1_500_000


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        follow_redirects=True,
        headers=BROWSER_HEADERS,
        timeout=httpx.Timeout(PAGE_TIMEOUT, connect=5.0),
        limits=httpx.Limits(max_connections=40, max_keepalive_connections=20),
    )


def parse_html(html: str):
    from bs4 import BeautifulSoup

    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


async def fetch_html(
    client: httpx.AsyncClient, url: str, timeout: float = PAGE_TIMEOUT, headers: Optional[dict] = None
) -> Optional[Tuple[str, str]]:
    """GET a page. Returns (final_url, html) or None on any failure."""
    try:
        resp = await client.get(url, timeout=timeout, headers=headers)
    except Exception as exc:
        log.info("fetch failed %s: %s", url, type(exc).__name__)
        return None
    if resp.status_code >= 400:
        log.info("fetch %s -> HTTP %s", url, resp.status_code)
        return None
    ctype = resp.headers.get("content-type", "")
    if ctype and "html" not in ctype and "xml" not in ctype:
        return None
    return str(resp.url), resp.text[:MAX_HTML_CHARS]
