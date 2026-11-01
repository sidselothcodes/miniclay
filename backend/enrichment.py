"""Enrichment orchestrator.

Per domain:
  stage 1 (parallel): homepage fetch + MX lookup
  stage 2 (parallel): subpages (/pricing first), GitHub org, news search, LinkedIn search
  synthesis: OpenAI structured output when OPENAI_API_KEY is set, otherwise a rules
  engine; either way the decision maker, emails and sources are grounded in what
  the pipeline actually fetched.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Dict, List, Optional, Tuple

import httpx

import knowledge
import llm
from cache import EnrichmentCache, cache_key
from outreach import compose_outreach, find_violations, hook_from_headline, sanitize
from schemas import DecisionMaker, EnrichedCompany, EnrichmentRow
from settings import (
    ALL_SOURCES,
    SOURCE_GITHUB,
    SOURCE_LINKEDIN,
    SOURCE_NEWS,
    SOURCE_PRICING,
    SOURCE_TIMEOUT,
    SOURCE_WEBSITE,
)
from sources import contacts, github, search, website
from sources.http import make_client

log = logging.getLogger("miniclay.enrichment")

SIGNAL_PREFIXES = ["Trigger", "Stack/GitHub", "Compliance"]
_cache: Optional[EnrichmentCache] = None


def get_cache() -> EnrichmentCache:
    global _cache
    if _cache is None:
        _cache = EnrichmentCache()
    return _cache


def normalize_domain(raw: str) -> str:
    domain = raw.strip().lower()
    domain = re.sub(r"^[a-z]+://", "", domain)
    domain = domain.split("/")[0].split("?")[0].split("#")[0]
    return domain[4:] if domain.startswith("www.") else domain


@dataclass
class SourceBundle:
    domain: str
    company_name: str
    kb: Optional[dict] = None
    homepage: Optional[website.PageData] = None
    subpages: List[website.PageData] = field(default_factory=list)
    github: Optional[dict] = None
    news: List[search.SearchHit] = field(default_factory=list)
    linkedin: List[contacts.Candidate] = field(default_factory=list)
    mx_hosts: Optional[List[str]] = None
    compliance: List[str] = field(default_factory=list)
    providers: Dict[str, str] = field(default_factory=dict)

    @property
    def pricing_page(self) -> Optional[website.PageData]:
        return next((p for p in self.subpages if p.kind == "pricing"), None)

    @property
    def has_any_data(self) -> bool:
        return bool(self.homepage or self.subpages or self.github or self.news or self.linkedin or self.kb)

    def decision_maker_options(self) -> List[dict]:
        """Live LinkedIn candidates first, then the curated reference contact."""
        status = contacts.email_status(self.mx_hosts)
        options: List[dict] = []
        for cand in self.linkedin:
            options.append({
                "full_name": cand.full_name, "role": cand.role, "linkedin_url": cand.linkedin_url,
                "origin": "linkedin",
            })
        kb_dm = (self.kb or {}).get("decision_maker")
        if kb_dm and all(o["full_name"].lower() != kb_dm["full_name"].lower() for o in options):
            options.append({**kb_dm, "origin": "reference"})
        for opt in options:
            emails = contacts.email_candidates(opt["full_name"], self.domain)
            opt["work_email"] = emails[0] if emails else ""
            opt["email_alternates"] = emails[1:]
            opt["email_status"] = status
        return options


def derive_company_name(home: Optional[website.PageData], kb: Optional[dict], domain: str) -> str:
    if kb:
        return kb["company_name"]
    label = domain.split(".")[0]
    squash = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())  # noqa: E731
    if home:
        if home.site_name and len(home.site_name.split()) <= 3:
            return home.site_name
        for segment in re.split(r"\s+[|–—\-:·]\s+|:\s+", home.title):
            segment = segment.strip()
            if segment and len(segment.split()) <= 3 and squash(segment).startswith(squash(label)[:4]):
                return segment
    return label.capitalize()


async def _guard(awaitable: Awaitable, label: str, default: Any, timeout: float = SOURCE_TIMEOUT) -> Any:
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout)
    except Exception as exc:
        log.info("source %s failed: %s", label, type(exc).__name__)
        return default


async def collect_sources(client: httpx.AsyncClient, domain: str) -> SourceBundle:
    kb = knowledge.lookup(domain)
    home, mx_hosts = await asyncio.gather(
        _guard(website.fetch_homepage(client, domain), "homepage", None),
        _guard(contacts.lookup_mx(client, domain), "mx", None, timeout=10),
    )
    company_name = derive_company_name(home, kb, domain)

    subpages, gh, news, linkedin = await asyncio.gather(
        _guard(website.fetch_subpages(client, domain, home), "subpages", []),
        _guard(github.discover_github(client, domain, company_name, home.github_orgs if home else []), "github", None),
        _guard(search.find_news(client, company_name, domain), "news", ([], "none")),
        _guard(contacts.find_decision_makers(client, company_name), "linkedin", ([], "none")),
    )
    bundle = SourceBundle(
        domain=domain,
        company_name=company_name,
        kb=kb,
        homepage=home if home and home.is_useful else None,
        subpages=subpages,
        github=gh,
        news=news[0],
        linkedin=linkedin[0],
        mx_hosts=mx_hosts,
        providers={"news": news[1], "linkedin": linkedin[1]},
    )
    corpus = "\n".join([home.text if home else ""] + [p.text for p in subpages])
    bundle.compliance = website.detect_compliance(corpus)
    return bundle


# ------------------------------- rules synthesis -------------------------------

def _first_sentence(text: str, max_words: int = 30) -> str:
    sentence = re.split(r"(?<=[.!?])\s", text.strip())[0]
    words = sentence.split()
    return " ".join(words[:max_words]).rstrip(",;:") + ("." if not sentence.endswith(".") else "")


def _trim_words(text: str, max_words: int) -> str:
    words = text.split()
    return text if len(words) <= max_words else " ".join(words[:max_words]).rstrip(",;:") + "…"


def _clean_headline(title: str) -> str:
    return re.sub(r"\s+[|\-–—]\s+[^|\-–—]{2,40}$", "", title).strip()


def rules_fields(bundle: SourceBundle) -> Tuple[dict, List[str], set]:
    """Deterministic fields. Returns (fields, fallbacks_from_reference, live_sources_used)."""
    kb = bundle.kb or {}
    kb_signals = kb.get("signals", ["", "", ""])
    fallbacks: List[str] = []
    used = set()
    home = bundle.homepage

    if home:
        used.add(SOURCE_WEBSITE)

    if kb.get("product_and_icp"):
        product = kb["product_and_icp"]
        fallbacks.append("product_and_icp")
    elif home and (home.meta_description or home.headings):
        product = _first_sentence(home.meta_description or home.headings[0])
    else:
        product = f"No product description could be fetched from {bundle.domain}."

    pricing_page = bundle.pricing_page
    live_pricing = website.summarize_pricing(pricing_page.text) if pricing_page else ""
    if live_pricing and website.extract_price_points(pricing_page.text):
        pricing = live_pricing[:80]
        used.add(SOURCE_PRICING)
    elif kb.get("pricing_tier_summary"):
        pricing = kb["pricing_tier_summary"]
        fallbacks.append("pricing_tier_summary")
    elif pricing_page:
        pricing = "Custom / contact sales"
        used.add(SOURCE_PRICING)
    else:
        pricing = "Pricing not public"

    if kb.get("gtm_motion"):
        gtm = kb["gtm_motion"]
        fallbacks.append("gtm_motion")
    else:
        gtm = website.infer_gtm_motion(pricing_page.text if pricing_page else "", home.text if home else "") or "Unknown"

    # Signals: live evidence first, curated reference second.
    if bundle.news:
        top = bundle.news[0]
        trigger = f"Trigger: {_trim_words(_clean_headline(top.title), 18)}" + (f" ({top.date})" if top.date else "")
        used.add(SOURCE_NEWS)
    elif kb_signals[0]:
        trigger = kb_signals[0]
        fallbacks.append("trigger")
    elif home and website.signal_lines(home.text):
        trigger = f"Trigger: {_trim_words(website.signal_lines(home.text)[0], 20)}"
    else:
        trigger = "Trigger: no recent launch found in public sources"

    if bundle.github:
        stack = f"Stack/GitHub: {github.describe_github(bundle.github)}"
        used.add(SOURCE_GITHUB)
    elif kb_signals[1]:
        stack = kb_signals[1]
        fallbacks.append("stack")
    else:
        stack = "Stack/GitHub: no public GitHub org found"

    if bundle.compliance:
        compliance = f"Compliance: {', '.join(bundle.compliance)} (per {bundle.domain})"
    elif kb_signals[2]:
        compliance = kb_signals[2]
        fallbacks.append("compliance")
    else:
        compliance = "Compliance: not published on site"

    fields = {
        "domain": bundle.domain,
        "company_name": bundle.company_name,
        "product_and_icp": product,
        "gtm_motion": gtm,
        "pricing_tier_summary": pricing,
        "tech_and_live_signals": [trigger, stack, compliance],
    }
    return fields, fallbacks, used


def _hook_sentence(bundle: SourceBundle) -> str:
    if bundle.kb and bundle.kb.get("hook"):
        return bundle.kb["hook"]
    if bundle.news:
        return hook_from_headline(bundle.company_name, _clean_headline(bundle.news[0].title))
    if bundle.homepage:
        lines = website.signal_lines(bundle.homepage.text)
        if lines:
            return f"Saw this on {bundle.domain}: “{_trim_words(lines[0], 14).rstrip('.')}”."
    return f"Saw {bundle.company_name}'s latest product updates on {bundle.domain}."


def _normalize_signals(signals: List[str], fallback: List[str]) -> List[str]:
    out: List[str] = []
    for i, prefix in enumerate(SIGNAL_PREFIXES):
        item = signals[i].strip() if i < len(signals) and signals[i] else ""
        if not item:
            item = fallback[i]
        if not re.match(rf"^\s*{re.escape(prefix)}\s*:", item, re.I):
            body = re.sub(r"^[^:]{1,20}:\s*", "", item)
            item = f"{prefix}: {body}"
        out.append(item)
    return out


def _placeholder_dm(company_name: str) -> dict:
    return {
        "full_name": "Not found",
        "role": "No public CTO / VP Eng profile found",
        "linkedin_url": contacts.linkedin_search_url("CTO", company_name),
        "work_email": "",
        "email_alternates": [],
        "email_status": "Unknown",
        "origin": "none",
    }


def build_row(bundle: SourceBundle, seller_context: str, llm_result: Optional[EnrichedCompany]) -> EnrichmentRow:
    rules, fallbacks, used = rules_fields(bundle)
    options = bundle.decision_maker_options()

    # Decision maker: whatever the LLM picked must be one of the fetched candidates.
    chosen = None
    if llm_result:
        wanted = re.sub(r"\s+", " ", llm_result.decision_maker.full_name or "").strip().lower()
        chosen = next((o for o in options if o["full_name"].lower() == wanted), None)
    chosen = chosen or (options[0] if options else _placeholder_dm(bundle.company_name))
    if chosen["origin"] == "linkedin":
        used.add(SOURCE_LINKEDIN)
    elif chosen["origin"] == "reference":
        fallbacks.append("decision_maker")
    first_name = chosen["full_name"].split()[0] if chosen["origin"] != "none" else None

    role = chosen["role"]
    if llm_result and chosen["origin"] == "linkedin" and llm_result.decision_maker.role.strip():
        role = llm_result.decision_maker.role.strip()
    decision_maker = DecisionMaker(
        full_name=chosen["full_name"],
        role=role,
        linkedin_url=chosen["linkedin_url"],
        work_email=chosen["work_email"],
        email_status=chosen["email_status"],
    )

    if llm_result:
        fields = {
            "domain": bundle.domain,
            "company_name": llm_result.company_name.strip() or rules["company_name"],
            "product_and_icp": llm_result.product_and_icp.strip() or rules["product_and_icp"],
            "gtm_motion": llm_result.gtm_motion.strip() or rules["gtm_motion"],
            "pricing_tier_summary": llm_result.pricing_tier_summary.strip() or rules["pricing_tier_summary"],
            "tech_and_live_signals": _normalize_signals(llm_result.tech_and_live_signals, rules["tech_and_live_signals"]),
        }
        fetched = {
            SOURCE_WEBSITE: bool(bundle.homepage),
            SOURCE_PRICING: bool(bundle.pricing_page),
            SOURCE_GITHUB: bool(bundle.github),
            SOURCE_NEWS: bool(bundle.news),
        }
        claimed = {s.strip() for s in llm_result.sources_used}
        used = {s for s, ok in fetched.items() if ok and s in claimed} | (used & {SOURCE_LINKEDIN})
        outreach = llm_result.ai_outreach.strip()
        fallbacks = [f for f in fallbacks if f == "decision_maker"]
        generated_by = "llm"
    else:
        fields = rules
        outreach = compose_outreach(
            first_name, bundle.company_name, _hook_sentence(bundle), seller_context,
            surface=(bundle.kb or {}).get("surface"),
        )
        generated_by = "rules"

    # Final guardrail: greeting must match the grounded decision maker; no banned words.
    if first_name and find_violations(outreach, first_name):
        outreach = sanitize(re.sub(r"^\s*Hi [^—\-,]+[—\-,]\s*", "", outreach), first_name)

    source_urls: Dict[str, List[str]] = {}
    if bundle.homepage:
        source_urls[SOURCE_WEBSITE] = [bundle.homepage.url] + [p.url for p in bundle.subpages if p.kind != "pricing"]
    if bundle.pricing_page:
        source_urls[SOURCE_PRICING] = [bundle.pricing_page.url]
    if bundle.github:
        source_urls[SOURCE_GITHUB] = [bundle.github["url"]]
    if bundle.news:
        source_urls[SOURCE_NEWS] = [h.url for h in bundle.news[:3]]
    if chosen["origin"] == "linkedin":
        source_urls[SOURCE_LINKEDIN] = [chosen["linkedin_url"]]

    sources_used = [s for s in ALL_SOURCES if s in used]
    return EnrichmentRow(
        **fields,
        decision_maker=decision_maker,
        ai_outreach=outreach,
        sources_used=sources_used,
        status="success",
        generated_by=generated_by,
        email_alternates=chosen.get("email_alternates", []),
        source_urls={k: v for k, v in source_urls.items() if k in sources_used},
        fallbacks=sorted(set(fallbacks)),
    )


def error_row(domain: str, message: str) -> dict:
    return {
        "domain": domain, "status": "error", "error": message,
        "company_name": None, "product_and_icp": None, "gtm_motion": None, "pricing_tier_summary": None,
        "tech_and_live_signals": [], "decision_maker": None, "ai_outreach": None, "sources_used": [],
    }


async def enrich_company(
    domain: str,
    seller_context: str,
    *,
    client: Optional[httpx.AsyncClient] = None,
    refresh: bool = False,
    use_cache: bool = True,
) -> dict:
    started = time.monotonic()
    domain = normalize_domain(domain)
    key = cache_key(domain, seller_context)
    if use_cache and not refresh:
        cached = get_cache().get(key)
        if cached:
            return {**cached, "cached": True}

    owns_client = client is None
    client = client or make_client()
    try:
        bundle = await collect_sources(client, domain)
        if not bundle.has_any_data:
            return error_row(domain, f"could not reach {domain} or find public data about it")
        llm_result = await _guard(llm.synthesize(bundle, seller_context), "llm", None, timeout=90)
        row = build_row(bundle, seller_context, llm_result)
        row.elapsed_ms = int((time.monotonic() - started) * 1000)
        payload = row.model_dump()
        if use_cache:
            get_cache().set(key, domain, payload)
        return payload
    except Exception as exc:  # never let one domain break the batch
        log.exception("enrichment failed for %s", domain)
        return error_row(domain, f"enrichment failed ({type(exc).__name__})")
    finally:
        if owns_client:
            await client.aclose()
