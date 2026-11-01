"""Decision-maker discovery (LinkedIn source) and work-email inference."""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import List, Optional, Tuple
from urllib.parse import quote_plus, urlparse

import httpx

from settings import DNS_TIMEOUT
from sources.search import SearchHit, web_search

log = logging.getLogger("miniclay.contacts")

LINKEDIN_PROFILE_RE = re.compile(r"^https?://([a-z]{2,3}\.)?(www\.)?linkedin\.com/in/([^/?#]+)/?", re.I)

# (pattern, canonical label, score). Highest score wins when several match.
ROLE_RULES: List[Tuple[str, str, int]] = [
    (r"\bCTO\b|Chief Technology Officer", "CTO", 100),
    (r"Chief AI Officer|\bCAIO\b", "Chief AI Officer", 96),
    (r"Head of (?:Applied )?AI\b|Head of (?:Data (?:&|and) )?AI\b|Head of Machine Learning|Head of ML\b", "Head of AI", 92),
    (r"\bVP,? (?:of )?Engineering\b|Vice President,? (?:of )?Engineering|SVP,? (?:of )?Engineering", "VP of Engineering", 88),
    (r"Head of Engineering|Engineering Director|Director of Engineering", "Head of Engineering", 78),
    (r"\bCo-?founder\b", "Co-Founder", 72),
    (r"Chief Product Officer|\bCPO\b", "Chief Product Officer", 66),
    (r"\bFounder\b", "Founder", 60),
]
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

    @property
    def first_name(self) -> str:
        return self.full_name.split()[0]


def linkedin_query(company_name: str) -> str:
    return (
        f'site:linkedin.com/in/ "{company_name}" '
        '("CTO" OR "VP of Engineering" OR "Head of AI" OR "Co-Founder" OR "VP Engineering")'
    )


def linkedin_search_url(full_name: str, company_name: str) -> str:
    return f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(f'{full_name} {company_name}')}"


def canonical_profile_url(url: str) -> Optional[str]:
    match = LINKEDIN_PROFILE_RE.match(url.strip())
    if not match:
        return None
    return f"https://www.linkedin.com/in/{match.group(3)}"


def _score_role(text: str) -> Tuple[int, List[str]]:
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
    return best, labels


def _clean_role(raw: str, company_name: str, labels: List[str]) -> str:
    role = re.sub(rf"\s+(?:at|@)\s+{re.escape(company_name)}.*$", "", raw, flags=re.I)
    role = re.sub(rf"\b{re.escape(company_name)}\b", "", role, flags=re.I)
    role = re.sub(r"\s{2,}", " ", role).strip(" ,|-–—·")
    if role and len(role) <= 60 and any(re.search(p, role, re.I) for p, _, _ in ROLE_RULES):
        return role.replace("Cofounder", "Co-Founder").replace("Co-founder", "Co-Founder")
    if "Co-Founder" in labels and "CTO" in labels:
        return "Co-Founder & CTO"
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

    # Role text: title segments first, then "<role> at <Company>" phrasing in the snippet.
    role_source = rest
    snippet_role = re.search(
        rf"([A-Z][\w&,/ \-]{{1,60}}?)\s+(?:at|@)\s+{re.escape(company_name)}\b", hit.snippet
    )
    score, labels = _score_role(rest)
    if snippet_role:
        s_score, s_labels = _score_role(snippet_role.group(1))
        if s_score > score:
            score, labels, role_source = s_score, s_labels, snippet_role.group(1)
    if score <= 0:
        return None

    if not in_title:
        score -= 10
    # "Former VP Eng at <Company>" in the headline, or "previously ... <Company>" in the snippet.
    # A past role at some *other* company ("Previously at Uber") is fine.
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


async def find_decision_makers(
    client: httpx.AsyncClient, company_name: str
) -> Tuple[List[Candidate], str]:
    hits, provider = await web_search(client, linkedin_query(company_name), max_results=10)
    ranked = [c for c in rank_candidates(hits, company_name) if c.score >= 50]
    return ranked[:3], provider


# ---------------------------- email inference ----------------------------

def _ascii_token(token: str) -> str:
    folded = unicodedata.normalize("NFKD", token).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", folded.lower())


def email_candidates(full_name: str, domain: str) -> List[str]:
    tokens = [t for t in re.split(r"[\s]+", CREDENTIAL_SUFFIX_RE.sub("", full_name)) if t and not t.endswith(".")]
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

    # DNS-over-HTTPS fallback for hosts where UDP/53 is blocked.
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


def is_linkedin_profile(url: str) -> bool:
    return bool(url) and "/in/" in urlparse(url).path
