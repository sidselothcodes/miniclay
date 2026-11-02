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

GITHUB_LINK_RE = re.compile(r"github\.com/([A-Za-z0-9][A-Za-z0-9-]{0,38})(?=[/\"'?#\s<)\\]|$)", re.I)
GITHUB_RESERVED = {
    "about", "apps", "blog", "collections", "contact", "customer-stories", "enterprise", "events",
    "explore", "features", "github", "home", "join", "login", "marketplace", "mobile", "new",
    "nonprofit", "notifications", "orgs", "pricing", "readme", "security", "settings", "site",
    "sponsors", "team", "topics", "trending", "solutions", "resources", "signup", "logout",
    "education", "copilot", "premium-support", "codespaces", "issues", "pulls", "search",
}

TEAM_SLUGS = ["leadership", "team", "our-team", "founders", "people", "about", "about-us", "company"]
LEADER_HINT_RE = re.compile(r"\b(?:co-?founder|founder|CEO|CTO|managing partner|partner|principal|head of)\b", re.I)

# Cloud servers are often served a regional site ("Razorpay USA"); retry once as an Indian visitor.
REGION_WORDS = r"USA|US|U\.S\.|United States|UK|United Kingdom|UAE|Singapore|Malaysia|Australia|Canada|Europe|EU"
REGION_SUBDOMAINS = {"us", "uk", "sg", "my", "au", "ae", "ca", "eu"}
INDIA_HEADERS = {"Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8"}

# Site builders and hosts whose branding leaks into customers' pages ("Notion" for a VC's Notion site).
# brand -> (HTML markers, the brand's own domains)
HOSTING_PLATFORMS: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...]]] = {
    "Notion": (("notion-static.com", "notion.site", "notion.so/", "notionusercontent"), ("notion.so", "notion.com", "notion.site")),
    "Webflow": (("data-wf-site", "webflow.com", "website-files.com"), ("webflow.com", "webflow.io")),
    "Framer": (("framerusercontent.com", 'content="Framer', "framer.com/"), ("framer.com", "framer.website")),
    "WordPress": (('content="WordPress', "/wp-content/", "/wp-includes/"), ("wordpress.com", "wordpress.org")),
    "Wix": (("wixstatic.com", 'content="Wix.com'), ("wix.com",)),
    "Squarespace": (("squarespace.com", "static1.squarespace"), ("squarespace.com",)),
    "Substack": (("substackcdn.com", "substack.com"), ("substack.com",)),
    "Carrd": (("carrd.co",), ("carrd.co",)),
    "Super": (("super.so",), ("super.so",)),
    "Cloudflare": ((), ("cloudflare.com",)),
    "Vercel": ((), ("vercel.com", "vercel.app")),
}
HOSTING_BOILERPLATE_RE = re.compile(
    r"all-in-one (?:connected )?workspace|connected workspace|blends your everyday work apps|"
    r"(?:built|made|created) (?:with|in|on) (?:notion|framer|webflow|wix|squarespace|carrd|super)|"
    r"powered by (?:notion|webflow|wordpress|framer|squarespace|wix)|website builder",
    re.I,
)

# "$20/user/mo", "$8 per seat per month", "€10", "2.9% + 30¢"
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
    regional: bool = False
    host_platform: str = ""

    @property
    def is_useful(self) -> bool:
        return len(self.title) + len(self.meta_description) + len(self.text) >= 60


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
    seen, ordered = set(), []
    for login, _ in counts.most_common():
        if login.lower() not in seen:
            seen.add(login.lower())
            ordered.append(login)
    return ordered


def looks_like_challenge(title: str, text: str) -> bool:
    blob = f"{title} {text[:400]}".lower()
    return any(marker in blob for marker in CHALLENGE_MARKERS) and len(text) < 1500


def is_hosting_brand(name: str, domain: str) -> bool:
    """True when `name` is a site builder/host ("Notion") and `domain` isn't that brand's own site."""
    squashed = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    for brand, (_, own_domains) in HOSTING_PLATFORMS.items():
        if squashed == brand.lower():
            return not any(domain == d or domain.endswith("." + d) for d in own_domains)
    return False


def detect_host_platform(html: str, domain: str) -> str:
    sample = html[:300_000]
    for brand, (markers, own_domains) in HOSTING_PLATFORMS.items():
        if any(domain == d or domain.endswith("." + d) for d in own_domains):
            return ""
        if markers and any(marker in sample for marker in markers):
            return brand
    return ""


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

    # Drop the site builder's own branding so "Notion" never becomes the company.
    domain = strip_www(urlparse(url).netloc)
    platform = detect_host_platform(html, domain)
    if is_hosting_brand(site_name, domain):
        platform, site_name = platform or site_name, ""
    if platform:
        brand_re = re.compile(rf"\b{re.escape(platform)}\b", re.I)
        if HOSTING_BOILERPLATE_RE.search(meta_description) or brand_re.search(meta_description):
            meta_description = ""
        def without_brand(line: str) -> str:
            segments = re.split(r"\s+[|\u2013\u2014\-:\u00b7]\s+", line)
            return " | ".join(seg for seg in segments if not brand_re.fullmatch(seg.strip()))

        title = without_brand(title)
        text = "\n".join(
            without_brand(ln) for ln in text.splitlines() if not HOSTING_BOILERPLATE_RE.search(ln) and without_brand(ln)
        )
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
        host_platform=platform,
    )


def is_regional_variant(page: PageData, domain: str) -> bool:
    host = strip_www(urlparse(page.url).netloc)
    if host != domain and host.split(".")[0] in REGION_SUBDOMAINS:
        return True
    label = re.escape(domain.split(".")[0])
    pattern = rf"\b{label}\s+(?:{REGION_WORDS})\b|\bfor (?:{REGION_WORDS}) (?:businesses|companies)\b"
    return bool(re.search(pattern, page.title, re.I))


def strip_region_suffix(name: str, domain: str) -> str:
    """'Razorpay USA' -> 'Razorpay' (only when what's left is the domain's brand)."""
    match = re.match(rf"^(.+?)\s+(?:{REGION_WORDS})$", name.strip())
    squash = lambda t: re.sub(r"[^a-z0-9]", "", t.lower())  # noqa: E731
    if match and squash(match.group(1)) == squash(domain.split(".")[0]):
        return match.group(1)
    return name


async def _fetch_home(client: httpx.AsyncClient, url: str, headers: Optional[dict] = None) -> Optional[PageData]:
    fetched = await fetch_html(client, url, headers=headers)
    if not fetched:
        return None
    page = parse_page(fetched[1], fetched[0], "home")
    return None if looks_like_challenge(page.title, page.text) else page


async def fetch_homepage(client: httpx.AsyncClient, domain: str) -> Optional[PageData]:
    for url in (f"https://{domain}", f"https://www.{domain}"):
        page = await _fetch_home(client, url)
        if not page:
            continue
        if is_regional_variant(page, domain):
            retry = await _fetch_home(client, url, headers=INDIA_HEADERS)
            if retry and not is_regional_variant(retry, domain):
                return retry
            page.regional = True
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
        return True
    if home and page.title and page.title == home.title and page.text[:300] == home.text[:300]:
        return True
    return "page not found" in page.title.lower() or page.title.strip().startswith("404")


async def _fetch_subpage(
    client: httpx.AsyncClient, kind: str, url: str, home: Optional[PageData], min_chars: int = 120
) -> Optional[PageData]:
    fetched = await fetch_html(client, url, timeout=PAGE_TIMEOUT)
    if not fetched:
        return None
    final_url, html = fetched
    page = parse_page(html, final_url, kind)
    if _is_soft_404(page, final_url, home) or looks_like_challenge(page.title, page.text):
        return None
    return page if len(page.title) + len(page.meta_description) + len(page.text) >= min_chars else None


async def fetch_subpages(
    client: httpx.AsyncClient, domain: str, home: Optional[PageData], limit: int = MAX_SUBPAGES
) -> List[PageData]:
    """Fetch up to `limit` reachable subpages, always preferring /pricing."""
    candidates = discover_subpages(domain, home)
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


async def fetch_team_page(client: httpx.AsyncClient, domain: str, home: Optional[PageData]) -> Optional[PageData]:
    """Leadership/team/about page: linked pages first, plus /team, /about-us and /about; prefers one naming leaders."""
    base = home.url if home else f"https://{domain}"
    host = strip_www(urlparse(base).netloc) or domain
    linked: Dict[str, str] = {}
    for link in home.links if home else []:
        parsed = urlparse(link)
        segments = [seg for seg in parsed.path.lower().split("/") if seg]
        if (parsed.netloc and strip_www(parsed.netloc) != host) or not segments or len(segments) > 2:
            continue
        if segments[-1] in TEAM_SLUGS and segments[-1] not in linked:
            linked[segments[-1]] = f"{parsed.scheme or 'https'}://{parsed.netloc or urlparse(base).netloc}{parsed.path}"
    urls: List[str] = []
    for url in [linked[slug] for slug in TEAM_SLUGS if slug in linked][:2] + [
        urljoin(base, path) for path in ("/team", "/about-us", "/about")
    ]:
        if url.rstrip("/") not in {u.rstrip("/") for u in urls}:
            urls.append(url)
    pages = [p for p in await asyncio.gather(*(_fetch_subpage(client, "team", u, home, min_chars=20) for u in urls)) if p]
    return next((p for p in pages if LEADER_HINT_RE.search(p.text)), pages[0] if pages else None)


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


YC_RE = re.compile(
    r"\b(?:Y\s?Combinator|YC)\b[^.\n]{0,25}?\b([WSFX]\d{2}|(?:Winter|Summer|Fall|Spring)\s+20\d{2})\b"
    r"|\bYC\s?([WSFX]\d{2})\b",
    re.I,
)
FUNDING_RE = re.compile(
    r"\b(?:rais(?:ed|es|ing)|closes?|closed|secur(?:ed|es)|lands?)\b[^.\n]{0,30}?"
    r"[$€£]\s?\d[\d.,]*\s?(?:[MBK]\b|million|billion)[^.\n]{0,40}",
    re.I,
)
ROUND_RE = re.compile(r"\b(pre-seed|seed round|seed funding|Series [A-F])\b", re.I)
BACKER_RE = re.compile(r"\bbacked by ([A-Z][\w&.' ]{2,60}?)(?:[.,\n]|$)")
HIRING_RE = re.compile(r"\bwe(?:'re|’re| are) hiring\b|\bopen roles\b|\bjoin (?:our|the) team\b", re.I)
SCALE_RE = re.compile(
    r"\b(?:(?:over|more than|trusted by|used by|serving|powering|loved by|helping)\s+)?"
    r"\d[\d,.]*\s?(?:k|K|M|B|million|billion)?\+?\s+"
    r"(?:[A-Za-z&/-]+\s){0,2}?"
    r"(?:customers|users|teams|companies|businesses|developers|shops|stores|merchants|downloads|"
    r"members|clinics|restaurants|contractors|brands|creators|patients|orders|transactions)\b",
    re.I,
)


def detect_traction(text: str) -> str:
    """'Backed by Y Combinator (W25) · raised $3M seed' style summary, or ''."""
    parts: List[str] = []
    yc = YC_RE.search(text)
    if yc:
        parts.append(f"Y Combinator ({(yc.group(1) or yc.group(2)).upper()})")
    else:
        backer = BACKER_RE.search(text)
        if backer:
            parts.append(f"backed by {backer.group(1).strip()}")
    funding = FUNDING_RE.search(text)
    if funding:
        parts.append(re.sub(r"\s+", " ", funding.group(0)).strip(" ,.")[:70])
    elif ROUND_RE.search(text):
        parts.append(f"{ROUND_RE.search(text).group(1)} stage")
    if HIRING_RE.search(text):
        parts.append("actively hiring")
    return " · ".join(parts[:2])


def detect_scale(text: str) -> str:
    match = SCALE_RE.search(text)
    if not match:
        return ""
    phrase = re.sub(r"\s+", " ", match.group(0)).strip()
    return phrase[:1].upper() + phrase[1:]


INVESTOR_TLDS = (".vc", ".capital", ".ventures", ".fund")
# First-person investing language (strong) vs. generic VC vocabulary a vendor for VCs might also use (weak).
INVESTOR_STRONG_RE = re.compile(
    r"\bwe (?:invest|back|partner with|lead|write)\b|\bour (?:portfolio|fund|LPs)\b|\bassets under management\b|"
    r"\bAUM\b|\bfund (?:I{1,3}|IV|V|\d)\b|\bcheck sizes?\b",
    re.I,
)
INVESTOR_WEAK_RE = re.compile(
    r"\bventure (?:capital|fund)\b|\bseed (?:fund|capital)\b|\bportfolio compan(?:y|ies)\b|\bpre-?seed\b|\blimited partners\b",
    re.I,
)
STAGES = [
    ("Pre-Seed", r"\bpre-?seed\b"),
    ("Seed", r"(?<!pre-)(?<!pre)\bseed\b"),
    ("Pre-Series A", r"\bpre-?series\s*a\b"),
    ("Series A", r"(?<!pre-)(?<!pre)\bseries\s*a\b"),
    ("Series B", r"\bseries\s*b\b"),
    ("Growth", r"\bgrowth[- ]stage\b|\bgrowth fund\b"),
    ("Late Stage", r"\blate[- ]stage\b"),
]
AUM_RE = re.compile(
    r"(?:[$₹€£]\s?\d[\d.,]*\s?(?:B|M|bn|billion|million|Cr|crore)\+?)\s*(?:AUM|in assets|under management|"
    r"(?:in )?(?:fund|funds|corpus|committed capital))",
    re.I,
)
PORTFOLIO_RE = re.compile(r"\b\d[\d,]*\+?\s+(?:portfolio\s+)?(?:companies|startups|founders|investments)\b", re.I)
INVEST_STATEMENT_RE = re.compile(r"\bwe (?:invest|back)\b|\binvest(?:s|ing)? (?:in|at)\b", re.I)
FOCUS_RE = re.compile(r"\b(?:backing|focus(?:ed|es)? on)\b", re.I)


def is_investment_firm(domain: str, company_name: str, own_text: str) -> bool:
    """VC/investment firm, judged from the domain and the firm's own pages (not news about it)."""
    if domain.endswith(INVESTOR_TLDS):
        return True
    strong = {m.group(0).lower() for m in INVESTOR_STRONG_RE.finditer(own_text)}
    weak = {m.group(0).lower() for m in INVESTOR_WEAK_RE.finditer(own_text)}
    named_like_fund = re.search(r"\b(?:Ventures|Capital|VC|Fund|Partners)\b", company_name or "")
    return bool(strong) and (len(strong) + len(weak) >= 2 or bool(named_like_fund))


def stage_focus(text: str) -> str:
    """'Seed to Pre-Series A', 'Seed to Growth', 'Seed', or ''."""
    found = [label for label, pattern in STAGES if re.search(pattern, text, re.I)]
    if not found:
        return ""
    return found[0] if len(found) == 1 else f"{found[0]} to {found[-1]}"


def vc_motion(text: str) -> str:
    found = {label for label, pattern in STAGES if re.search(pattern, text, re.I)}
    if found & {"Growth", "Late Stage", "Series B"} and found & {"Pre-Seed", "Seed"}:
        return "Multi-Stage VC"
    if found & {"Pre-Seed", "Seed", "Pre-Series A"} or re.search(r"\bearly[- ]stage\b", text, re.I):
        return "Early-Stage VC"
    return "Venture Fund"


def _first_line(text: str, pattern: "re.Pattern[str]", max_words: int = 16) -> str:
    for line in text.splitlines():
        if pattern.search(line) and 3 <= len(line.split()) <= 40:
            words = line.split()
            return " ".join(words[:max_words]).rstrip(",;:.")
    return ""


def investor_signals(text: str) -> List[str]:
    """Focus / Portfolio / Scale bullets for a fund, from its own pages ('' when not found)."""
    focus = _first_line(text, INVEST_STATEMENT_RE) or _first_line(text, FOCUS_RE)
    portfolio = _first_line(text, PORTFOLIO_RE)
    aum = AUM_RE.search(text)
    fund_size = re.sub(r"\s+", " ", aum.group(0)) if aum else ""
    return [
        f"Focus: {focus}" if focus else "",
        f"Portfolio: {portfolio}" if portfolio else "",
        f"Scale: {fund_size}" if fund_size else "",
    ]
