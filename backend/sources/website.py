"""Homepage + subpage scraping (Website & Pricing sources)."""
from __future__ import annotations

import asyncio
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import httpx

from settings import PAGE_TIMEOUT
from sources.http import fetch_html, parse_html

SUBPAGE_PRIORITY = ["pricing", "security", "enterprise", "customers", "about"]
SUBPAGE_SLUGS = {
    "pricing": {"pricing", "plans", "plans-and-pricing"},
    "security": {"security", "trust"},
    "enterprise": {"enterprise"},
    "customers": {"customers", "customer-stories", "case-studies"},
    "about": {"about", "about-us", "company"},
}
MAX_SUBPAGES = 2

BOILERPLATE_TAGS = [
    "script", "style", "noscript", "svg", "nav", "footer", "header", "form", "iframe",
    "template", "button", "select", "canvas", "picture", "video", "audio", "aside",
]
CHALLENGE_MARKERS = (
    "just a moment", "attention required", "enable javascript and cookies",
    "verify you are human", "access denied", "checking your browser",
)
TEXT_LIMITS = {"home": 3500, "pricing": 4000}
DEFAULT_TEXT_LIMIT = 2200

# github.com/<org> links (org logins are 1-39 chars of letters, digits, hyphens).
GITHUB_LINK_RE = re.compile(r"github\.com/([A-Za-z0-9][A-Za-z0-9-]{0,38})(?=[/\"'?#\s<)\\]|$)", re.I)
GITHUB_RESERVED = {
    "about", "apps", "blog", "collections", "contact", "customer-stories", "enterprise", "events",
    "explore", "features", "github", "home", "join", "login", "marketplace", "mobile", "new",
    "nonprofit", "notifications", "orgs", "pricing", "readme", "security", "settings", "site",
    "sponsors", "team", "topics", "trending", "solutions", "resources", "signup", "logout",
    "education", "copilot", "premium-support", "codespaces", "issues", "pulls", "search",
}

# Price tokens: "$20/user/mo", "$8 per seat per month", "€10", "2.9% + 30¢".
PRICE_RE = re.compile(
    r"(?:US)?[$€£]\s?\d[\d,]*(?:\.\d{1,2})?(?:\s?[kKmM]\b)?"
    r"(?:\s?(?:/|per)\s?(?:active\s)?(?:user|seat|member|editor|month|mo|year|yr|host|device)s?\b"
    r"(?:\s?(?:/|per)\s?(?:month|mo|year|yr)\b)?)?",
    re.I,
)
PERCENT_FEE_RE = re.compile(
    r"\d+(?:\.\d+)?\s?%\s?\+\s?(?:\d+\s?¢|[$€£]\s?0?\.\d{2}|\d+\s?cents?)", re.I
)
CUSTOM_PRICING_RE = re.compile(r"contact sales|talk to sales|custom pricing|request a quote|get a demo", re.I)
FREE_RE = re.compile(r"\bfree\b", re.I)

COMPLIANCE_PATTERNS: List[Tuple[str, str]] = [
    ("SOC 2 Type II", r"SOC\s?2(?:®)?\s?(?:Type\s?(?:II|2))"),
    ("SOC 2", r"SOC\s?2\b"),
    ("SOC 1", r"SOC\s?1\b"),
    ("ISO 27001", r"ISO(?:/IEC)?\s?27001"),
    ("ISO 42001", r"ISO(?:/IEC)?\s?42001"),
    ("HIPAA", r"\bHIPAA\b"),
    ("PCI DSS", r"PCI[\s-]?DSS|PCI\s(?:Level\s?1|compliant|compliance)"),
    ("GDPR", r"\bGDPR\b"),
    ("FedRAMP", r"\bFedRAMP\b"),
    ("CCPA", r"\bCCPA\b"),
]

SIGNAL_LINE_RE = re.compile(
    r"\b(AI|agents?|LLMs?|models?|API|SDK|MCP|launch(?:ed|es)?|introducing|announc\w+|now available|beta|GA)\b"
)


@dataclass
class PageData:
    url: str
    kind: str
    title: str = ""
    meta_description: str = ""
    site_name: str = ""
    headings: List[str] = field(default_factory=list)
    text: str = ""
    links: List[str] = field(default_factory=list)
    github_orgs: List[str] = field(default_factory=list)

    @property
    def is_useful(self) -> bool:
        return len(self.title) + len(self.meta_description) + len(self.text) >= 120


def strip_www(host: str) -> str:
    host = host.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def clean_lines(raw: str, limit: int) -> str:
    seen = set()
    out: List[str] = []
    total = 0
    for line in raw.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if len(line) < 3 or line.lower() in seen:
            continue
        seen.add(line.lower())
        out.append(line)
        total += len(line) + 1
        if total >= limit:
            break
    return "\n".join(out)[:limit]


def extract_github_orgs(html: str) -> List[str]:
    counts: Counter = Counter()
    for match in GITHUB_LINK_RE.finditer(html):
        login = match.group(1)
        if login.lower() in GITHUB_RESERVED:
            continue
        counts[login] += 1
    # Most-linked org first; case-insensitive dedupe.
    seen, ordered = set(), []
    for login, _ in counts.most_common():
        if login.lower() not in seen:
            seen.add(login.lower())
            ordered.append(login)
    return ordered


def looks_like_challenge(title: str, text: str) -> bool:
    blob = f"{title} {text[:400]}".lower()
    return any(marker in blob for marker in CHALLENGE_MARKERS) and len(text) < 1500


def parse_page(html: str, url: str, kind: str) -> PageData:
    soup = parse_html(html)
    title = soup.title.get_text(" ", strip=True) if soup.title else ""

    def meta(*selectors: Dict[str, str]) -> str:
        for attrs in selectors:
            tag = soup.find("meta", attrs=attrs)
            if tag and tag.get("content"):
                return re.sub(r"\s+", " ", tag["content"]).strip()
        return ""

    meta_description = meta({"name": "description"}, {"property": "og:description"})
    site_name = meta({"property": "og:site_name"}, {"name": "application-name"})

    links: List[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        links.append(urljoin(url, href))

    headings: List[str] = []
    for tag in soup.find_all(["h1", "h2", "h3"]):
        text = tag.get_text(" ", strip=True)
        if text and text not in headings and len(text) < 160:
            headings.append(text)
        if len(headings) >= 15:
            break

    for tag in soup(BOILERPLATE_TAGS):
        tag.decompose()
    for tag in soup.select('[role="navigation"], [role="banner"], [role="contentinfo"], [aria-hidden="true"]'):
        tag.decompose()
    for tag in soup.select('[id*="cookie" i], [class*="cookie" i]'):
        tag.decompose()

    text = clean_lines(soup.get_text("\n"), TEXT_LIMITS.get(kind, DEFAULT_TEXT_LIMIT))
    return PageData(
        url=url,
        kind=kind,
        title=title,
        meta_description=meta_description,
        site_name=site_name,
        headings=headings,
        text=text,
        links=links,
        github_orgs=extract_github_orgs(html),
    )


async def fetch_homepage(client: httpx.AsyncClient, domain: str) -> Optional[PageData]:
    for url in (f"https://{domain}", f"https://www.{domain}"):
        fetched = await fetch_html(client, url)
        if not fetched:
            continue
        final_url, html = fetched
        page = parse_page(html, final_url, "home")
        if looks_like_challenge(page.title, page.text):
            continue
        return page
    return None


def discover_subpages(domain: str, home: Optional[PageData]) -> List[Tuple[str, str]]:
    """Candidate (kind, url) pairs: links found on the homepage first, then common paths."""
    base = home.url if home else f"https://{domain}"
    host = strip_www(urlparse(base).netloc) or domain
    found: Dict[str, str] = {}
    for link in home.links if home else []:
        parsed = urlparse(link)
        if parsed.netloc and strip_www(parsed.netloc) != host:
            continue
        segments = [s for s in parsed.path.lower().split("/") if s]
        if not segments or len(segments) > 2:
            continue
        for kind, slugs in SUBPAGE_SLUGS.items():
            if kind not in found and segments[-1] in slugs:
                found[kind] = f"{parsed.scheme or 'https'}://{parsed.netloc or urlparse(base).netloc}{parsed.path}"

    candidates: List[Tuple[str, str]] = []
    for kind in SUBPAGE_PRIORITY:
        urls = [found[kind]] if kind in found else []
        urls.append(urljoin(base, f"/{kind}"))
        for url in urls:
            if url.rstrip("/") not in {c[1].rstrip("/") for c in candidates}:
                candidates.append((kind, url))
    return candidates


def _is_soft_404(page: PageData, final_url: str, home: Optional[PageData]) -> bool:
    path = urlparse(final_url).path.strip("/")
    if not path:
        return True  # redirected back to the homepage
    if home and page.title and page.title == home.title and page.text[:300] == home.text[:300]:
        return True
    return "page not found" in page.title.lower() or page.title.strip().startswith("404")


async def _fetch_subpage(
    client: httpx.AsyncClient, kind: str, url: str, home: Optional[PageData]
) -> Optional[PageData]:
    fetched = await fetch_html(client, url, timeout=PAGE_TIMEOUT)
    if not fetched:
        return None
    final_url, html = fetched
    page = parse_page(html, final_url, kind)
    if _is_soft_404(page, final_url, home) or looks_like_challenge(page.title, page.text):
        return None
    return page if page.is_useful else None


async def fetch_subpages(
    client: httpx.AsyncClient, domain: str, home: Optional[PageData], limit: int = MAX_SUBPAGES
) -> List[PageData]:
    """Fetch up to `limit` reachable subpages, always preferring /pricing."""
    candidates = discover_subpages(domain, home)
    # Wave 1: pricing + security candidates in parallel. Wave 2 only if we still need pages.
    first_wave = [c for c in candidates if c[0] in ("pricing", "security")]
    second_wave = [c for c in candidates if c not in first_wave]

    chosen: Dict[str, PageData] = {}
    for wave in (first_wave, second_wave):
        if len(chosen) >= limit:
            break
        pages = await asyncio.gather(*(_fetch_subpage(client, k, u, home) for k, u in wave))
        for (kind, _), page in zip(wave, pages):
            if page and kind not in chosen:
                chosen[kind] = page
    ordered = [chosen[k] for k in SUBPAGE_PRIORITY if k in chosen]
    return ordered[:limit]


# ---------- deterministic extractors (used for LLM context + rules fallback) ----------

def extract_price_points(text: str, limit: int = 4) -> List[str]:
    tokens: List[str] = []
    for regex in (PERCENT_FEE_RE, PRICE_RE):
        for match in regex.finditer(text):
            token = re.sub(r"\s+", " ", match.group(0)).strip()
            token = re.sub(r"\s?(/|per)\s?", r"/", token) if "%" not in token else token
            if token.lower() not in {t.lower() for t in tokens}:
                tokens.append(token)
            if len(tokens) >= limit:
                return tokens
    return tokens


def pricing_lines(text: str, limit: int = 14) -> List[str]:
    lines = []
    for line in text.splitlines():
        if PRICE_RE.search(line) or PERCENT_FEE_RE.search(line) or CUSTOM_PRICING_RE.search(line):
            lines.append(line[:220])
        if len(lines) >= limit:
            break
    return lines


def summarize_pricing(text: str) -> str:
    if not text:
        return ""
    tokens = extract_price_points(text, limit=3)
    parts: List[str] = []
    if FREE_RE.search(text) and not any("%" in t for t in tokens):
        parts.append("Free tier")
    parts.extend(tokens)
    if CUSTOM_PRICING_RE.search(text):
        parts.append("Enterprise custom")
    return " · ".join(parts)


def detect_compliance(text: str) -> List[str]:
    found: List[str] = []
    for label, pattern in COMPLIANCE_PATTERNS:
        if label == "SOC 2" and "SOC 2 Type II" in found:
            continue
        if re.search(pattern, text, re.I):
            found.append(label)
    return found


def signal_lines(text: str, limit: int = 6) -> List[str]:
    lines = []
    for line in text.splitlines():
        if 30 <= len(line) <= 240 and SIGNAL_LINE_RE.search(line):
            lines.append(line)
        if len(lines) >= limit:
            break
    return lines


def infer_gtm_motion(pricing_text: str, home_text: str = "") -> str:
    blob = f"{pricing_text}\n{home_text}"
    if PERCENT_FEE_RE.search(blob) or re.search(r"per transaction|pay as you go|usage[- ]based|per request", blob, re.I):
        return "Usage-Based"
    has_prices = bool(PRICE_RE.search(pricing_text))
    if has_prices and FREE_RE.search(pricing_text):
        return "Freemium PLG"
    if has_prices:
        return "Self-Serve SaaS"
    if CUSTOM_PRICING_RE.search(blob):
        return "Sales-Led Enterprise"
    return "Sales-Led Enterprise" if pricing_text else ""
