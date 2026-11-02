"""Free web search: DDGS library -> DuckDuckGo HTML -> Bing HTML. A provider that errors
(e.g. rate-limited on a cloud IP) is skipped for COOLDOWN_SECONDS."""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from settings import SEARCH_TIMEOUT
from sources.http import parse_html

log = logging.getLogger("miniclay.search")

COOLDOWN_SECONDS = 90
_cooldown_until: Dict[str, float] = {}


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str = ""
    date: str = ""


def _ddgs_class():
    try:
        from ddgs import DDGS  # Python 3.10+
        return DDGS
    except ImportError:
        pass
    try:
        from duckduckgo_search import DDGS  # Python 3.9
        return DDGS
    except ImportError:
        return None


def _ddgs_text_sync(query: str, max_results: int) -> List[SearchHit]:
    DDGS = _ddgs_class()
    if DDGS is None:
        raise RuntimeError("ddgs not installed")
    rows = DDGS(timeout=int(SEARCH_TIMEOUT)).text(query, max_results=max_results) or []
    return [
        SearchHit(title=r.get("title", ""), url=r.get("href") or r.get("url", ""), snippet=r.get("body", ""))
        for r in rows
    ]


def _ddgs_news_sync(query: str, max_results: int) -> List[SearchHit]:
    DDGS = _ddgs_class()
    if DDGS is None:
        raise RuntimeError("ddgs not installed")
    rows = DDGS(timeout=int(SEARCH_TIMEOUT)).news(query, max_results=max_results, timelimit="y") or []
    return [
        SearchHit(
            title=r.get("title", ""),
            url=r.get("url") or r.get("href", ""),
            snippet=r.get("body", ""),
            date=(r.get("date") or "")[:10],
        )
        for r in rows
    ]


def _unwrap_ddg_href(href: str) -> str:
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(target) if target else href
    return href


def parse_ddg_html(html: str, max_results: int) -> List[SearchHit]:
    soup = parse_html(html)
    hits: List[SearchHit] = []
    for result in soup.select("div.result"):
        if "result--ad" in (result.get("class") or []):
            continue
        link = result.select_one("a.result__a")
        if not link or not link.get("href"):
            continue
        snippet = result.select_one(".result__snippet")
        hits.append(SearchHit(
            title=link.get_text(" ", strip=True),
            url=_unwrap_ddg_href(link["href"]),
            snippet=snippet.get_text(" ", strip=True) if snippet else "",
        ))
        if len(hits) >= max_results:
            break
    return hits


def parse_bing_html(html: str, max_results: int) -> List[SearchHit]:
    soup = parse_html(html)
    hits: List[SearchHit] = []
    for item in soup.select("li.b_algo"):
        link = item.select_one("h2 a")
        if not link or not link.get("href"):
            continue
        snippet = item.select_one(".b_caption p, p.b_lineclamp2, p.b_lineclamp3, p.b_lineclamp4")
        hits.append(SearchHit(
            title=link.get_text(" ", strip=True),
            url=link["href"],
            snippet=snippet.get_text(" ", strip=True) if snippet else "",
        ))
        if len(hits) >= max_results:
            break
    return hits


async def _ddg_html(client: httpx.AsyncClient, query: str, max_results: int) -> List[SearchHit]:
    resp = await client.post(
        "https://html.duckduckgo.com/html/", data={"q": query, "kl": "us-en"}, timeout=SEARCH_TIMEOUT
    )
    resp.raise_for_status()
    return parse_ddg_html(resp.text, max_results)


async def _bing_html(client: httpx.AsyncClient, query: str, max_results: int) -> List[SearchHit]:
    resp = await client.get(
        "https://www.bing.com/search",
        params={"q": query, "setlang": "en", "count": "15"},
        timeout=SEARCH_TIMEOUT,
    )
    resp.raise_for_status()
    return parse_bing_html(resp.text, max_results)


async def web_search(
    client: httpx.AsyncClient, query: str, max_results: int = 6, news: bool = False
) -> List[SearchHit]:
    """Run `query` through the provider chain; returns hits from the first provider that answers."""
    sync_fn = _ddgs_news_sync if news else _ddgs_text_sync
    providers: List[Tuple[str, Callable]] = [
        ("ddgs-news" if news else "ddgs", lambda: asyncio.to_thread(sync_fn, query, max_results)),
    ]
    if not news:
        providers += [
            ("ddg-html", lambda: _ddg_html(client, query, max_results)),
            ("bing-html", lambda: _bing_html(client, query, max_results)),
        ]
    for name, run in providers:
        if _cooldown_until.get(name, 0) > time.monotonic():
            continue
        try:
            hits = await asyncio.wait_for(run(), timeout=SEARCH_TIMEOUT + 2)
        except Exception as exc:
            log.info("search provider %s failed: %s", name, type(exc).__name__)
            _cooldown_until[name] = time.monotonic() + COOLDOWN_SECONDS
            continue
        hits = [h for h in hits if h.url.startswith("http")]
        if hits:
            log.info("search provider %s answered %r", name, query[:60])
            return hits
    return []


def _mentions(company_name: str, hit: SearchHit) -> bool:
    pattern = rf"\b{re.escape(company_name)}\b"
    return bool(re.search(pattern, f"{hit.title} {hit.snippet}", re.I))


def news_query(company_name: str, domain: str, today: Optional[dt.date] = None) -> str:
    year = (today or dt.date.today()).year
    return (
        f'"{company_name}" ({domain}) (launch OR API OR AI OR funding OR enterprise OR changelog) '
        f"{year - 1}..{year}"
    )


async def find_news(client: httpx.AsyncClient, company_name: str, domain: str) -> List[SearchHit]:
    hits = await web_search(client, news_query(company_name, domain), max_results=8)
    if len(hits) < 3:
        hits += await web_search(client, f'"{company_name}" launch OR AI OR funding', max_results=6, news=True)

    seen, relevant = set(), []
    for hit in hits:
        key = hit.url.split("#")[0].rstrip("/")
        if key in seen or "linkedin.com/in/" in key or not _mentions(company_name, hit):
            continue
        seen.add(key)
        relevant.append(hit)
    return relevant[:5]
