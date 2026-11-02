"""Decision-maker discovery (LinkedIn source) and work-email inference."""
from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote_plus

import httpx

from settings import DNS_TIMEOUT
from sources.search import SearchHit, web_search

log = logging.getLogger("miniclay.contacts")

LINKEDIN_PROFILE_RE = re.compile(r"^https?://([a-z]{2,3}\.)?(www\.)?linkedin\.com/in/([^/?#]+)/?", re.I)

# Technical leaders first, then founders/CEOs so small startups still resolve to a founder.
ROLE_RULES: List[Tuple[str, str, int]] = [
    (r"\bCTO\b|Chief Technology Officer", "CTO", 100),
    (r"Chief AI Officer|\bCAIO\b", "Chief AI Officer", 96),
    (r"Head of (?:Applied )?AI\b|Head of (?:Data (?:&|and) )?AI\b|Head of Machine Learning|Head of ML\b", "Head of AI", 92),
    (r"\bVP,? (?:of )?Engineering\b|Vice President,? (?:of )?Engineering|SVP,? (?:of )?Engineering", "VP of Engineering", 88),
    (r"Head of Engineering|Engineering Director|Director of Engineering", "Head of Engineering", 82),
    (r"\bManaging Partner\b|\bGeneral Partner\b|\bFounding Partner\b", "Managing Partner", 84),
    (r"\bCo-?founder\b", "Co-Founder", 80),
    (r"\bFounder\b", "Founder", 78),
    (r"\bCEO\b|Chief Executive Officer", "CEO", 76),
    (r"\bPartner\b(?!\s*(?:Manager|Success|Marketing|Engineer)\b)", "Partner", 70),
    (r"Chief Product Officer|\bCPO\b", "Chief Product Officer", 66),
    (r"\bPrincipal\b(?!\s+(?:Engineer|Software|Scientist|Designer|Product|Architect|Consultant|Data|Research|Analyst|Program|Applied))",
     "Principal", 64),
]
INVESTOR_LABELS = {"Managing Partner", "Partner", "Principal"}
HONORIFIC_RE = re.compile(r"^(?:dr|mr|mrs|ms|mx|prof|sir|shri|sri|smt)\.?\s+", re.I)
NON_TECH_ROLE_RE = re.compile(r"\b(sales|marketing|recruit\w*|talent|partnerships?|account|people|finance|legal|GTM)\b", re.I)
FORMER_RE = re.compile(r"\b(former|formerly|ex-|previously|past|alum(?:nus|ni)?)\b", re.I)
NAME_TOKEN = r"[A-ZÀ-Ý][A-Za-zÀ-ÿ'’.\-]+"
NAME_RE = re.compile(rf"^{NAME_TOKEN}(?:\s+(?:{NAME_TOKEN}|van|de|der|von|da|di|la|le|del|bin)){{1,3}}$")
CREDENTIAL_SUFFIX_RE = re.compile(r",?\s+(?:CPA|PhD|Ph\.D\.|MBA|CFA|PMP|MD|Jr\.?|Sr\.?|III|II)\b.*$")


@dataclass
class Candidate:
    full_name: str
    role: str
    linkedin_url: str
    score: int
    evidence: str = ""


def linkedin_query(company_name: str) -> str:
    return (
        f'site:linkedin.com/in/ "{company_name}" '
        '("Founder" OR "Co-Founder" OR "CEO" OR "CTO" OR "Head of AI" OR "VP Engineering" OR "VP of Engineering")'
    )


def strip_honorific(full_name: str) -> str:
    """'Dr. Vivek Raghavan' -> 'Vivek Raghavan'."""
    return HONORIFIC_RE.sub("", (full_name or "").strip())


def name_key(full_name: str) -> str:
    return strip_honorific(full_name).lower()


def linkedin_search_url(full_name: str, company_name: str) -> str:
    keywords = f"{strip_honorific(full_name)} {company_name}"
    return f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(keywords)}"


def canonical_profile_url(url: str) -> Optional[str]:
    match = LINKEDIN_PROFILE_RE.match(url.strip())
    if not match:
        return None
    return f"https://www.linkedin.com/in/{match.group(3)}"


def score_role(text: str) -> Tuple[int, List[str]]:
    labels, best = [], 0
    for pattern, label, score in ROLE_RULES:
        if re.search(pattern, text, re.I):
            labels.append(label)
            best = max(best, score)
    if best and NON_TECH_ROLE_RE.search(text):
        best -= 40  # "Head of AI Sales", "VP Engineering Recruiting", ...
    if "CTO" in labels and re.search(r"CTO\s*\(", text):
        best -= 8  # "CTO (Security)" is a narrower seat than "CTO"
    if "CTO" in labels and "Co-Founder" in labels:
        best += 4
    elif "CEO" in labels and ("Co-Founder" in labels or "Founder" in labels):
        best += 2
    return best, labels


def _clean_role(raw: str, company_name: str, labels: List[str]) -> str:
    role = re.sub(rf"\s+(?:at|@)\s+{re.escape(company_name)}.*$", "", raw, flags=re.I)
    role = re.sub(rf"\b{re.escape(company_name)}\b", "", role, flags=re.I)
    role = re.sub(r"\s{2,}", " ", role).strip(" ,|-–—·")
    if role and len(role) <= 60 and any(re.search(p, role, re.I) for p, _, _ in ROLE_RULES):
        return role.replace("Cofounder", "Co-Founder").replace("Co-founder", "Co-Founder")
    return _canonical_role(labels)


def _canonical_role(labels: List[str]) -> str:
    founder = "Co-Founder" if "Co-Founder" in labels else ("Founder" if "Founder" in labels else "")
    for seat in ("CTO", "CEO"):
        if founder and seat in labels:
            return f"{founder} & {seat}"
    return labels[0] if labels else ""


def parse_linkedin_hit(hit: SearchHit, company_name: str) -> Optional[Candidate]:
    url = canonical_profile_url(hit.url)
    if not url:
        return None
    title = re.sub(r"\s*[|·]\s*LinkedIn.*$", "", hit.title, flags=re.I)
    title = re.sub(r"\s+[-–—]\s+LinkedIn\s*$", "", title, flags=re.I).strip()
    parts = [p.strip() for p in re.split(r"\s+[-–—|]\s+", title) if p.strip()]
    if not parts:
        return None

    name = CREDENTIAL_SUFFIX_RE.sub("", parts[0]).strip()
    if not NAME_RE.match(name) or re.search(r"\d", name):
        return None

    company_re = re.compile(rf"\b{re.escape(company_name)}\b", re.I)
    rest = " - ".join(parts[1:])
    in_title = bool(company_re.search(rest))
    in_snippet = bool(company_re.search(hit.snippet))
    if not (in_title or in_snippet):
        return None

    role_source = rest
    snippet_role = re.search(
        rf"([A-Z][\w&,/ \-]{{1,60}}?)\s+(?:at|@)\s+{re.escape(company_name)}\b", hit.snippet
    )
    score, labels = score_role(rest)
    if snippet_role:
        s_score, s_labels = score_role(snippet_role.group(1))
        if s_score > score:
            score, labels, role_source = s_score, s_labels, snippet_role.group(1)
    if score <= 0 or (set(labels) <= INVESTOR_LABELS and not in_title):
        return None

    if not in_title:
        score -= 10
    # Only a past role at *this* company counts; "Previously at Uber" is fine.
    former_in_snippet = re.search(
        rf"{FORMER_RE.pattern}[^.]{{0,60}}\b{re.escape(company_name)}\b", hit.snippet, re.I
    )
    if FORMER_RE.search(rest) or former_in_snippet:
        score -= 35

    role = _clean_role(role_source, company_name, labels)
    return Candidate(full_name=name, role=role, linkedin_url=url, score=score, evidence=hit.title[:160])


def rank_candidates(hits: List[SearchHit], company_name: str) -> List[Candidate]:
    best: dict = {}
    for hit in hits:
        cand = parse_linkedin_hit(hit, company_name)
        if cand and (cand.linkedin_url not in best or cand.score > best[cand.linkedin_url].score):
            best[cand.linkedin_url] = cand
    return sorted(best.values(), key=lambda c: c.score, reverse=True)


def people_query(company_name: str) -> str:
    return f'"{company_name}" ("CEO" OR "Co-Founder" OR "Founder" OR "CTO" OR "VP Engineering")'


async def search_people(client: httpx.AsyncClient, company_name: str) -> List[SearchHit]:
    """LinkedIn-scoped and general leadership searches, merged. Either may come back empty on cloud IPs."""
    batches = await asyncio.gather(
        web_search(client, linkedin_query(company_name), max_results=10),
        web_search(client, people_query(company_name), max_results=10),
    )
    seen, hits = set(), []
    for hit in batches[0] + batches[1]:
        if hit.url not in seen:
            seen.add(hit.url)
            hits.append(hit)
    return hits


def profile_urls(hits: List[SearchHit]) -> Dict[str, str]:
    """Exact linkedin.com/in/ URLs from search results, keyed by the lowercased person name in the title."""
    urls: Dict[str, str] = {}
    for hit in hits:
        url = canonical_profile_url(hit.url)
        if not url:
            continue
        name = CREDENTIAL_SUFFIX_RE.sub("", re.split(r"\s+[-\u2013\u2014|]\s+", hit.title)[0]).strip()
        if NAME_RE.match(name):
            urls.setdefault(name_key(name), url)
    return urls


PEOPLE_ROLE = (
    r"(?i:co-?founder(?:\s*(?:,|&|and)\s*(?:CEO|CTO|chief executive(?: officer)?|chief technology officer))?"
    r"|founder(?:\s*(?:,|&|and)\s*(?:CEO|CTO))?|CEO|CTO|chief executive(?: officer)?|chief technology officer"
    r"|head of (?:applied )?AI|head of engineering|VP,? (?:of )?engineering|vice president,? (?:of )?engineering"
    r"|(?:founding\s*(?:&|and)\s*)?managing partner|general partner|founding partner|venture partner|partner|principal)"
)
PERSON = r"(?P<name>[A-Z][a-z\u00e0-\u00ff'\u2019\-]+(?:\s+[A-Z][a-z\u00e0-\u00ff'\u2019\-]+){1,2})"
ROLE = rf"(?P<role>{PEOPLE_ROLE})"
NOT_NAME_WORDS = {
    "Our", "The", "Meet", "Team", "Leadership", "About", "Company", "Board", "Investors", "Contact",
    "Careers", "Join", "Us", "Founders", "Founder", "Executive", "Management", "News", "Press",
}
TRAILING_WORDS = {"Says", "Said", "Announces", "Talks", "Joins", "Explains", "Shares", "On", "At", "In", "And"}


def _person_name(raw: str) -> Optional[str]:
    tokens = raw.split()
    while tokens and tokens[-1] in TRAILING_WORDS:
        tokens.pop()
    if len(tokens) < 2 or any(t in NOT_NAME_WORDS for t in tokens):
        return None
    name = " ".join(tokens)
    return name if NAME_RE.match(name) else None


def extract_people(text: str, company_name: str) -> List[Candidate]:
    """Leaders named in news snippets ("Chargebee co-founder and CEO Krish Subramanian") or on a
    team page ("Dana Park" followed by "Founder & CEO")."""
    company = re.escape(company_name)
    patterns = [
        rf"\b{company}(?:'s|\u2019s)?\s+{ROLE}\s+{PERSON}",
        rf"{PERSON},\s+(?:the\s+)?{ROLE}\s+(?:of|at)\s+{company}\b",
        rf"{PERSON},\s+{company}(?:'s|\u2019s)?\s+{ROLE}",
    ]
    found: Dict[str, Candidate] = {}

    def add(raw_name: str, role_text: str, evidence: str) -> None:
        name = _person_name(raw_name)
        score, labels = score_role(role_text)
        if not name or score <= 0:
            return
        role = re.split(r"[.;|(]|,?\s+(?:previously|formerly|ex-)", role_text.strip())[0].strip(" ,")
        if not (role[:1].isupper() and " and " not in role and len(role) <= 40):
            role = _canonical_role(labels)
        cand = Candidate(name, role, linkedin_search_url(name, company_name), score, evidence[:160])
        if name.lower() not in found or cand.score > found[name.lower()].score:
            found[name.lower()] = cand

    for pattern in patterns:
        for match in re.finditer(pattern, text):
            before = text[max(0, match.start() - 25):match.start()]
            if not FORMER_RE.search(before):
                add(match.group("name"), match.group("role"), match.group(0))

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for i, line in enumerate(lines):
        # "Name - Role ..." or "Name Role" (space-only separator only when the title ends the line).
        match = re.fullmatch(rf"{PERSON}\s*[,|\u00b7\-\u2013\u2014]\s*{ROLE}\b.*", line) or re.fullmatch(
            rf"{PERSON}(?:\s+{ROLE})?\s*", line
        )
        if not match:
            continue
        if match.group("role"):
            add(match.group("name"), line[match.start("role"):][:60], line)
        elif i + 1 < len(lines) and re.match(rf"^{PEOPLE_ROLE}\b", lines[i + 1]):
            add(match.group("name"), lines[i + 1][:60], f"{line} {lines[i + 1]}")
    return sorted(found.values(), key=lambda c: c.score, reverse=True)


def first_name_of(full_name: str) -> Optional[str]:
    """First name without honorifics ('Dr. Vivek Raghavan' -> 'Vivek'), or None for placeholders."""
    name = strip_honorific(full_name)
    if not name or name.lower() in {"not found", "unknown", "n/a", "none"}:
        return None
    return name.split()[0]


def _ascii_token(token: str) -> str:
    folded = unicodedata.normalize("NFKD", token).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", folded.lower())


def email_candidates(full_name: str, domain: str) -> List[str]:
    clean = CREDENTIAL_SUFFIX_RE.sub("", strip_honorific(full_name))
    tokens = [t for t in re.split(r"\s+", clean) if t and not t.endswith(".")]
    if not tokens:
        return []
    first = _ascii_token(tokens[0])
    last = _ascii_token(tokens[-1]) if len(tokens) > 1 else ""
    if not first:
        return []
    emails = [f"{first}@{domain}"]
    if last:
        emails += [f"{first[0]}{last}@{domain}", f"{first}.{last}@{domain}"]
    return emails


async def lookup_mx(client: httpx.AsyncClient, domain: str) -> Optional[List[str]]:
    """MX hosts for `domain`. [] = confirmed none, None = lookup failed/unknown.

    A negative answer from the local resolver is not trusted on its own (sandboxed or
    filtered resolvers often answer NXDOMAIN for everything); DoH must confirm it."""
    try:
        import dns.asyncresolver

        answer = await dns.asyncresolver.resolve(domain, "MX", lifetime=DNS_TIMEOUT)
        hosts = sorted(str(r.exchange).rstrip(".") for r in answer)
        if hosts:
            return hosts
    except Exception as exc:
        log.info("dnspython MX lookup for %s: %s", domain, type(exc).__name__)

    for endpoint in ("https://cloudflare-dns.com/dns-query", "https://dns.google/resolve"):
        try:
            resp = await client.get(
                endpoint,
                params={"name": domain, "type": "MX"},
                headers={"accept": "application/dns-json"},
                timeout=DNS_TIMEOUT,
            )
            data = resp.json()
        except Exception:
            continue
        if data.get("Status") == 3:
            return []
        if data.get("Status") == 0:
            return sorted(
                a["data"].split()[-1].rstrip(".") for a in data.get("Answer", []) if a.get("type") == 15
            )
    return None


def email_status(mx_hosts: Optional[List[str]]) -> str:
    if mx_hosts:
        return "MX Verified"
    if mx_hosts == []:
        return "No MX Records"
    return "Pattern Inferred"
