"""Per-domain pipeline: homepage + MX, then subpages/GitHub/news/LinkedIn in parallel, then
LLM (or rules) synthesis grounded in what was actually fetched."""
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
from fit import LOW, assess_fit, clean_reason, is_consumer_without_ai, looks_consumer, normalize_tier
from outreach import casual_from_headline, compose_outreach, find_violations, sanitize
from schemas import DecisionMaker, EnrichedCompany, EnrichmentRow
from settings import (
    ALL_SOURCES,
    DEFAULT_SELLER_CONTEXT,
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

POSITION_PREFIXES = [("Launch", "Product"), ("Stack", "Traction"), ("Trust", "Scale")]
LEGACY_PREFIXES = {
    "trigger": "Launch", "news": "Launch", "stack/github": "Stack", "github": "Stack", "tech": "Stack",
    "funding": "Traction", "backing": "Traction", "growth": "Traction", "compliance": "Trust",
    "security": "Trust", "usage": "Scale", "distribution": "Scale",
}
LAUNCH_WORDS = re.compile(r"\b(introducing|new|now available|launch\w*|announc\w+|beta|released?|just shipped)\b", re.I)
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

    @property
    def pricing_page(self) -> Optional[website.PageData]:
        return next((p for p in self.subpages if p.kind == "pricing"), None)

    @property
    def has_any_data(self) -> bool:
        return bool(self.homepage or self.subpages or self.github or self.news or self.linkedin or self.kb)

    def decision_maker_options(self) -> List[dict]:
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
        _guard(search.find_news(client, company_name, domain), "news", []),
        _guard(contacts.find_decision_makers(client, company_name), "linkedin", []),
    )
    bundle = SourceBundle(
        domain=domain,
        company_name=company_name,
        kb=kb,
        homepage=home if home and home.is_useful else None,
        subpages=subpages,
        github=gh,
        news=news,
        linkedin=linkedin,
        mx_hosts=mx_hosts,
    )
    corpus = "\n".join([home.text if home else ""] + [p.text for p in subpages])
    bundle.compliance = website.detect_compliance(corpus)
    return bundle


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
    """Returns (fields, fields filled from reference data, live sources used)."""
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
        gtm = website.infer_gtm_motion(pricing_page.text if pricing_page else "", home.text if home else "")
        if not gtm:
            gtm = "Consumer D2C" if home and looks_consumer(f"{home.title}\n{home.text}") else "Unknown"

    live_text = "\n".join(
        [home.text if home else ""] + [p.text for p in bundle.subpages] + [f"{h.title}. {h.snippet}" for h in bundle.news]
    )
    launch_line = next((ln for ln in website.signal_lines(home.text) if LAUNCH_WORDS.search(ln)), "") if home else ""
    if bundle.news:
        top = bundle.news[0]
        first = f"Launch: {_trim_words(_clean_headline(top.title), 14)}" + (f" ({top.date})" if top.date else "")
        used.add(SOURCE_NEWS)
    elif kb_signals[0]:
        first = kb_signals[0]
        fallbacks.append("launch")
    elif launch_line:
        first = f"Launch: {_trim_words(launch_line, 14)}"
    elif home and (home.meta_description or home.headings):
        first = f"Product: {_trim_words(_first_sentence(home.meta_description or home.headings[0]), 14)}"
    else:
        first = "Product: no public product details found"

    traction = website.detect_traction(live_text)
    if bundle.github:
        second = f"Stack: {github.describe_github(bundle.github)}"
        used.add(SOURCE_GITHUB)
    elif traction:
        second = f"Traction: {traction}"
    elif kb_signals[1]:
        second = kb_signals[1]
        fallbacks.append("stack_or_traction")
    else:
        second = "Traction: no public funding, GitHub or hiring signals found"

    scale = website.detect_scale(live_text)
    if bundle.compliance:
        third = f"Trust: {', '.join(bundle.compliance)}"
    elif scale:
        third = f"Scale: {scale}"
    elif kb_signals[2]:
        third = kb_signals[2]
        fallbacks.append("trust_or_scale")
    else:
        third = "Scale: no public usage metrics found"

    fields = {
        "domain": bundle.domain,
        "company_name": bundle.company_name,
        "product_and_icp": product,
        "gtm_motion": gtm,
        "pricing_tier_summary": pricing,
        "tech_and_live_signals": [first, second, third],
    }
    return fields, fallbacks, used


def _casual_mention(bundle: SourceBundle) -> str:
    if bundle.kb and bundle.kb.get("casual"):
        return bundle.kb["casual"]
    if bundle.news:
        return casual_from_headline(bundle.company_name, _clean_headline(bundle.news[0].title))
    if bundle.homepage:
        for line in [*bundle.homepage.headings, *website.signal_lines(bundle.homepage.text)]:
            match = re.match(r"^\s*(?:introducing|meet|announcing)\s+(.{3,60}?)(?:[:,.!]|\s[-\u2013\u2014]\s|$)", line, re.I)
            if match:
                return f"saw you're launching {_trim_words(match.group(1), 6).rstrip('…')}"
    return f"been looking at what {bundle.company_name} is building"


def _normalize_signals(signals: List[str], fallback: List[str]) -> List[str]:
    out: List[str] = []
    for i, allowed in enumerate(POSITION_PREFIXES):
        item = signals[i].strip() if i < len(signals) and signals[i] else ""
        if not item:
            item = fallback[i]
        match = re.match(r"^\s*\**([^:*]{2,24})\**\s*:\s*(.*)$", item, re.S)
        prefix, body = (match.group(1).strip(), match.group(2).strip()) if match else ("", item)
        canonical = next((a for a in allowed if a.lower() == prefix.lower()), None)
        canonical = canonical or LEGACY_PREFIXES.get(prefix.lower())
        if canonical not in allowed:
            canonical, body = allowed[0], (body if prefix else item)
        out.append(f"{canonical}: {body}")
    return out


def fit_evidence(bundle: SourceBundle) -> str:
    parts: List[str] = []
    if bundle.homepage:
        home = bundle.homepage
        parts += [home.title, home.meta_description, " ".join(home.headings), home.text]
    parts += [p.text for p in bundle.subpages]
    parts += [f"{h.title}. {h.snippet}" for h in bundle.news]
    if bundle.github:
        parts.append(" ".join([bundle.github.get("description", "")] + [r.get("description", "") for r in bundle.github.get("top_repos", [])]))
    if bundle.kb:
        parts += [bundle.kb.get("product_and_icp", "")] + list(bundle.kb.get("signals", []))
    return "\n".join(p for p in parts if p)


def _same_context(a: str, b: str) -> bool:
    squash = lambda t: re.sub(r"\s+", " ", t).strip().lower()  # noqa: E731
    return squash(a) == squash(b)


def _placeholder_dm(company_name: str) -> dict:
    return {
        "full_name": "Not found",
        "role": "No public founder, CTO or VP Eng profile found",
        "linkedin_url": contacts.linkedin_search_url("CTO", company_name),
        "work_email": "",
        "email_alternates": [],
        "email_status": "Unknown",
        "origin": "none",
    }


def build_row(bundle: SourceBundle, seller_context: str, llm_result: Optional[EnrichedCompany]) -> EnrichmentRow:
    rules, fallbacks, used = rules_fields(bundle)
    options = bundle.decision_maker_options()

    # The LLM may only pick a decision maker the pipeline actually found.
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
        outreach = ""
        generated_by = "rules"

    # Curated fit only applies to the default pitch; anything else is judged on evidence.
    evidence = fit_evidence(bundle)
    default_pitch = _same_context(seller_context, DEFAULT_SELLER_CONTEXT)
    kb = bundle.kb or {}
    kb_fit = kb.get("fit") if default_pitch else None
    if kb_fit:
        rules_tier, rules_reason = kb_fit["tier"], kb_fit["reason"]
    else:
        rules_tier, rules_reason = assess_fit(seller_context, bundle.company_name, evidence)
    if llm_result:
        fit_tier = normalize_tier(llm_result.fit_tier) or rules_tier
        fit_reason = clean_reason(llm_result.fit_reason) or rules_reason
        if fit_tier != LOW and is_consumer_without_ai(seller_context, evidence):
            fit_tier, fit_reason = rules_tier, rules_reason  # never let the LLM manufacture an AI fit
    else:
        fit_tier, fit_reason = rules_tier, rules_reason
        if kb_fit:
            fallbacks.append("fit")

    if fit_tier == LOW:
        outreach = ""
    else:
        if not outreach:
            same_person = kb.get("decision_maker", {}).get("full_name") == chosen["full_name"]
            if default_pitch and same_person and kb.get("outreach_default"):
                outreach = kb["outreach_default"]
            else:
                outreach = compose_outreach(first_name, bundle.company_name, _casual_mention(bundle), seller_context)
        if find_violations(outreach, first_name):
            cleaned = sanitize(outreach, first_name)
            if find_violations(cleaned, first_name):
                cleaned = compose_outreach(first_name, bundle.company_name, _casual_mention(bundle), seller_context)
            outreach = cleaned

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
        fit_tier=fit_tier,
        fit_reason=fit_reason,
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
    except Exception as exc:  # one bad domain must not break the batch
        log.exception("enrichment failed for %s", domain)
        return error_row(domain, f"enrichment failed ({type(exc).__name__})")
    finally:
        if owns_client:
            await client.aclose()
