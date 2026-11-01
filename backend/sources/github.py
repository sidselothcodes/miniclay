"""GitHub org discovery (GitHub source).

Order: org linked from the homepage -> slug guesses checked against the org's `blog`
field -> GitHub user search. Repo data comes from the REST API, with an HTML scrape
of github.com/<org> as the fallback when the API is rate-limited.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Dict, List, Optional
from urllib.parse import urlparse

import httpx

from settings import GITHUB_TOKEN
from sources.http import fetch_html, parse_html

log = logging.getLogger("miniclay.github")

API = "https://api.github.com"


def _headers() -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "MiniClay-Enrichment/2.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


class RateLimited(Exception):
    pass


async def _get_json(client: httpx.AsyncClient, url: str, params: Optional[dict] = None):
    try:
        resp = await client.get(url, params=params, headers=_headers(), timeout=8.0)
    except Exception as exc:
        log.info("github api error %s: %s", url, type(exc).__name__)
        return None
    if resp.status_code in (403, 429) and "rate limit" in resp.text.lower():
        raise RateLimited(url)
    if resp.status_code != 200:
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def _domain_label(domain: str) -> str:
    return domain.split(".")[0].lower()


def _org_matches(org: dict, domain: str, company_name: str) -> bool:
    blog = (org.get("blog") or "").strip().lower()
    blog_host = urlparse(blog if "//" in blog else f"https://{blog}").netloc.split(":")[0] if blog else ""
    blog_host = blog_host[4:] if blog_host.startswith("www.") else blog_host
    if blog_host and (blog_host == domain or blog_host.endswith("." + domain)):
        return True
    # Same brand on another TLD (e.g. notion.so vs notion.com) only when the org name matches exactly.
    name = (org.get("name") or "").strip().lower()
    same_label = not blog_host or blog_host.split(".")[0] == _domain_label(domain)
    return bool(name) and name == company_name.strip().lower() and same_label and org.get("public_repos", 0) > 0


def _slug_guesses(domain: str, company_name: str) -> List[str]:
    label = _domain_label(domain)
    slug = re.sub(r"[^a-z0-9-]", "", company_name.lower().replace(" ", "-"))
    guesses = [label, slug, f"{label}hq", f"{label}app", f"{label}-inc", f"{label}labs", f"make{label}", f"{label}-public"]
    seen, out = set(), []
    for g in guesses:
        if g and g not in seen:
            seen.add(g)
            out.append(g)
    return out


def _summarize_repos(repos: List[dict]) -> Dict[str, list]:
    usable = [r for r in repos if not r.get("fork") and not r.get("archived")]
    usable.sort(key=lambda r: r.get("stargazers_count", 0), reverse=True)
    top = [
        {
            "name": r.get("name", ""),
            "stars": r.get("stargazers_count", 0),
            "language": r.get("language") or "",
            "description": (r.get("description") or "")[:140],
            "url": r.get("html_url", ""),
        }
        for r in usable[:5]
    ]
    weights: Counter = Counter()
    for r in usable[:30]:
        if r.get("language"):
            weights[r["language"]] += 1 + r.get("stargazers_count", 0)
    return {"top_repos": top, "languages": [lang for lang, _ in weights.most_common(4)]}


async def _load_org_api(client: httpx.AsyncClient, login: str, org: Optional[dict] = None) -> Optional[dict]:
    org = org or await _get_json(client, f"{API}/orgs/{login}") or await _get_json(client, f"{API}/users/{login}")
    if not org:
        return None
    owner_kind = "users" if org.get("type") == "User" else "orgs"
    repos = await _get_json(
        client,
        f"{API}/{owner_kind}/{org.get('login', login)}/repos",
        params={"per_page": 100, "type": "public" if owner_kind == "orgs" else "owner", "sort": "pushed"},
    ) or []
    summary = _summarize_repos(repos if isinstance(repos, list) else [])
    return {
        "login": org.get("login", login),
        "url": org.get("html_url") or f"https://github.com/{login}",
        "name": org.get("name") or login,
        "description": org.get("description") or org.get("bio") or "",
        "blog": org.get("blog") or "",
        "public_repos": org.get("public_repos", len(repos)),
        **summary,
    }


async def _load_org_html(client: httpx.AsyncClient, login: str) -> Optional[dict]:
    fetched = await fetch_html(client, f"https://github.com/{login}")
    if not fetched:
        return None
    final_url, html = fetched
    return parse_org_html(html, login, final_url)


def parse_org_html(html: str, login: str, url: str) -> Optional[dict]:
    soup = parse_html(html)
    public_repos = 0
    counter = soup.select_one('a[href$="repositories"] .Counter, a[href*="tab=repositories"] .Counter')
    if counter:
        digits = re.sub(r"[^\d]", "", counter.get("title") or counter.get_text())
        public_repos = int(digits) if digits else 0
    top_repos = []
    for item in soup.select(".pinned-item-list-item, li.Box-row")[:6]:
        name_tag = item.select_one("span.repo, a[itemprop='name codeRepository'], h3 a")
        if not name_tag:
            continue
        lang = item.select_one("[itemprop='programmingLanguage']")
        stars_tag = item.select_one("a[href$='/stargazers']")
        stars_text = re.sub(r"[^\d.k]", "", (stars_tag.get_text() if stars_tag else "0").lower())
        stars = int(float(stars_text[:-1]) * 1000) if stars_text.endswith("k") else int(float(stars_text or 0))
        top_repos.append({
            "name": name_tag.get_text(strip=True),
            "stars": stars,
            "language": lang.get_text(strip=True) if lang else "",
            "description": "",
            "url": f"https://github.com/{login}/{name_tag.get_text(strip=True)}",
        })
    if not top_repos and not public_repos:
        return None
    top_repos.sort(key=lambda r: r["stars"], reverse=True)
    desc = soup.find("meta", attrs={"name": "description"})
    languages = []
    for r in top_repos:
        if r["language"] and r["language"] not in languages:
            languages.append(r["language"])
    return {
        "login": login,
        "url": url,
        "name": login,
        "description": desc["content"] if desc and desc.get("content") else "",
        "blog": "",
        "public_repos": public_repos or len(top_repos),
        "top_repos": top_repos[:5],
        "languages": languages[:4],
    }


async def discover_github(
    client: httpx.AsyncClient, domain: str, company_name: str, homepage_orgs: List[str]
) -> Optional[dict]:
    try:
        # 1. An org linked from the company's own homepage is trusted as-is.
        for login in homepage_orgs[:3]:
            data = await _load_org_api(client, login)
            if data:
                data["discovered_via"] = "homepage link"
                return data

        # 2. Slug guesses, accepted only when the org's profile points back to the domain.
        for login in _slug_guesses(domain, company_name):
            org = await _get_json(client, f"{API}/orgs/{login}")
            if org and _org_matches(org, domain, company_name):
                data = await _load_org_api(client, login, org)
                if data:
                    data["discovered_via"] = "org profile match"
                    return data

        # 3. GitHub user search for organizations.
        found = await _get_json(
            client, f"{API}/search/users", params={"q": f"{company_name} type:org", "per_page": 5}
        )
        for item in (found or {}).get("items", [])[:3]:
            org = await _get_json(client, f"{API}/orgs/{item.get('login')}")
            if org and _org_matches(org, domain, company_name):
                data = await _load_org_api(client, item["login"], org)
                if data:
                    data["discovered_via"] = "github search"
                    return data
    except RateLimited:
        log.info("github api rate-limited; falling back to HTML")

    # 4. HTML fallback (no API quota): homepage-linked org or the domain label.
    for login in (homepage_orgs[:1] or [_domain_label(domain)]):
        data = await _load_org_html(client, login)
        if data:
            data["discovered_via"] = "github.com page"
            return data
    return None


def describe_github(data: Optional[dict]) -> str:
    """Short human summary used by the rules fallback, e.g. 'stripe-node (★4.1k, TypeScript)'."""
    if not data:
        return ""

    def fmt_stars(n: int) -> str:
        return f"{n / 1000:.1f}k".replace(".0k", "k") if n >= 1000 else str(n)

    repos = ", ".join(
        f"{r['name']} (★{fmt_stars(r['stars'])})" for r in data.get("top_repos", [])[:3] if r.get("name")
    )
    langs = "/".join(data.get("languages", [])[:3])
    parts = [f"github.com/{data['login']}: {data.get('public_repos', 0)} public repos"]
    if repos:
        parts.append(f"top {repos}")
    if langs:
        parts.append(langs)
    return " · ".join(parts)
