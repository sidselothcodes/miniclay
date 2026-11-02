"""OpenAI structured extraction: evidence bundle -> EnrichedCompany."""
from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, List, Optional

from pydantic import ValidationError

from outreach import BANNED_DISPLAY, find_violations
from schemas import EnrichedCompany
from settings import LLM_TIMEOUT, OPENAI_MODEL
from sources.contacts import first_name_of

if TYPE_CHECKING:
    from enrichment import SourceBundle

log = logging.getLogger("miniclay.llm")

MAX_CONTEXT_CHARS = 14000

SYSTEM_PROMPT = f"""You are a senior B2B GTM research analyst. You turn raw evidence scraped about ONE company into a strict JSON record for outbound sales. The company may be a large enterprise, a 5-person startup, or a consumer brand; adapt to what the evidence shows.

Ground rules:
- Use only facts present in the evidence blocks ([Website], [Pricing], [GitHub], [News], [Team], [People], [Contacts], [Reference]). Never invent URLs, numbers, launches, funding or certifications. The only exception is decision_maker rule 2 below.
- Prefer the most recent dated evidence. When evidence for a field is missing, say so plainly instead of guessing.

Fields:
- company_name: the short global brand name. Never add a country or region suffix picked up from a geo-redirected regional page (write "Razorpay", not "Razorpay USA").
  Many sites are built on Notion, Webflow, Framer, WordPress, Wix, Squarespace, Substack or Carrd, or served through Cloudflare or Vercel. Never name or describe that tool as the company unless the TARGET domain is the tool's own site; identify the company from the TARGET domain and its own page content (e.g. inuka.vc is Inuka, not Notion).
- product_and_icp: ONE sentence, max 22 words, no buzzwords: what they build and who buys it (team, role or company type).
- gtm_motion: 1-3 words, e.g. "Usage-Based", "Freemium PLG", "Sales-Led Enterprise", "Self-Serve SaaS", "Consumer D2C".
- pricing_tier_summary: concrete figures copied from [Pricing], max 70 characters, e.g. "$20/user/mo + usage", "2.9% + 30¢ per tx". If no figures: "Custom / contact sales" or "Pricing not public".
- tech_and_live_signals: exactly 3 short bullets (max 16 words each) whose bold prefix adapts to the company:
  1. "Launch: ..." a recent feature, launch or release (with month/year if known), OR "Product: ..." the core workflow or product wedge when nothing recent is public.
  2. "Stack: ..." public GitHub repos, SDKs, APIs or integrations (dev and B2B tools), OR "Traction: ..." backing (YC batch, seed/Series round), customer vertical, or hiring/growth signals (small startups and consumer apps).
  3. "Trust: ..." compliance (SOC 2, ISO 27001, HIPAA, PCI DSS) for enterprise sellers, OR "Scale: ..." a usage/volume metric, distribution channel, or operational bottleneck for startups and consumer companies.
- Investment firms (VC funds, angel networks, family offices): gtm_motion is "Early-Stage VC", "Multi-Stage VC" or "Venture Fund"; pricing_tier_summary is their stage or check focus (e.g. "Seed to Pre-Series A", "Seed to Growth"), never "Custom / contact sales" or "Pricing not public"; tech_and_live_signals use "Focus: ..." (stages, sectors, geographies), "Portfolio: ..." (count, notable companies) and "Scale: ..." (AUM, fund size) or "Stack: ..." (the firm's own tools). Describe the fund itself, never one portfolio company's product.
- fit_tier: how well the SELLER's product solves a problem this company has today. One of "Strong Fit", "Moderate Fit", "Low Fit".
  Strong: evidence shows they run the exact workflow the seller's product addresses. Moderate: adjacent or early signals. Low: no evidence of that workflow (consumer brands, offline businesses, unrelated products).
  Never invent AI, LLM or other usage to manufacture a fit. A bakery or apparel brand is "Low Fit" for an LLM tool. When unsure, pick the lower tier.
  Count AI launches listed in [Reference] or [News] even when the fetched page is a regional variant. For investment firms, fit can come from their own AI tooling or from what their portfolio builds.
- fit_reason: ONE sentence, max 20 words, specific to this company and the seller, e.g. "Consumer retail brand with no customer-facing LLM workflows in production."
- decision_maker: the best point of contact, chosen in this order:
  1. A person the evidence names ([Contacts], [People], [Team], [News], [Website]) as a CURRENT Founder, Co-Founder, CEO, CTO, Head of AI or VP of Engineering at THIS company, or a Managing Partner, General Partner, Partner or Principal at an investment firm. Prefer CTO > Head of AI > VP of Engineering; at startups under ~20 people prefer the Founder/CEO or Co-Founder/CTO. Set source "evidence".
  2. If the scraped pages and search results name nobody (search is often rate-limited), you MUST use your own knowledge to name the real Founder, Co-Founder, CEO, CTO or Managing Partner of the company if you know who founded or leads it, e.g. Maitreya Wagh or Prateek Sachan for bolna.ai, Harshil Mathur or Shashank Kumar for razorpay.com, Aadit Palicha or Kaivalya Vohra for zeptonow.com, Nitin Saluja or Raghav Verma for chaayos.com, Rahul Agarwalla or Shubham Titare for senseai.ai, Krish Subramanian for chargebee.com. Set source "knowledge". Do not guess names you don't actually know.
  3. Otherwise full_name "Not found", role "", source "none".
  full_name: the person's name without honorifics like "Dr." or "Mr.".
  linkedin_url: copy an exact linkedin.com/in/ URL only if it appears in the evidence for that person; otherwise "". confidence: how sure you are this person holds this role today.
- sources_used: only labels of evidence blocks you actually used, from ["Website", "Pricing", "GitHub", "News", "LinkedIn"]. Never output "AI" or "Reference".
- ai_outreach: a short cold email from the SELLER to the decision maker. If fit_tier is "Low Fit", return an empty string.

Outreach rules (strict; it must read like a real person typed it):
1. Start exactly with "Hey <FirstName>," using the decision_maker's first name (or "Hey <Company> team," if decision_maker is "Not found"), then continue sentence 1 casually, e.g. "Hey Emily, saw you're rolling out agent checkout on Link."
2. 2-3 short sentences, 30-40 words total.
3. Mention their product the way an insider would, in 4-6 casual words. Never recite conference names, dates, version numbers or feature lists back to them, and no parentheses.
4. Sentence 2: one plain-English line about the specific headache the seller's product solves for that feature.
5. Sentence 3: a low-pressure question, e.g. "Are you building that in-house, or open to a quick look?"
   Only mention evals or evaluation if the SELLER CONTEXT is about evaluation; otherwise talk about what the seller actually sells.
6. Never use em-dashes (—), en-dashes or double hyphens (--). Use commas and periods. No exclamation marks, no emojis, no sign-off.
7. Banned words and phrases: {", ".join(f'"{w}"' for w in BANNED_DISPLAY)}.

Style examples (only for a seller of LLM evaluation and observability; copy the tone, not the words):
"Hey Emily, saw you're rolling out agent checkout on Link. We help teams catch hallucinated cart items and policy misses before an agent actually triggers a charge. Are you building evals for that in-house, or open to a quick look?"
"Hey Tuomas, been playing with the new Linear Agent for auto-triage. How are you testing that prompt or model updates don't quietly mislabel bug priorities? We built a simple way to replay real triage traces if you're ever curious."
"""


def available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def _client():
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=LLM_TIMEOUT, max_retries=1)


def build_evidence(bundle: "SourceBundle", seller_context: str) -> str:
    from sources.website import pricing_lines, signal_lines

    blocks: List[str] = [
        f"SELLER CONTEXT (what the sender sells):\n{seller_context}",
        f"TARGET: {bundle.domain} (working name: {bundle.company_name})",
    ]
    home = bundle.homepage
    if home:
        regional_note = (
            "Note: this is a geo-redirected regional page served to a US server; describe the company's main "
            "business and use its global brand name.\n" if home.regional else ""
        )
        if home.host_platform:
            regional_note += (
                f"Note: this site is built on {home.host_platform}; ignore {home.host_platform}'s own branding and "
                f"describe {bundle.domain}.\n"
            )
        blocks.append(
            f"[Website] {home.url}\nTitle: {home.title}\nMeta: {home.meta_description}\n{regional_note}"
            f"Headings: {' | '.join(home.headings[:10])}\n"
            f"Product/AI lines: {' | '.join(signal_lines(home.text))}\nText:\n{home.text[:2500]}"
        )
    for page in bundle.subpages:
        label = "Pricing" if page.kind == "pricing" else f"Website:{page.kind}"
        extra = ""
        if page.kind == "pricing":
            extra = "Price lines:\n" + "\n".join(pricing_lines(page.text)) + "\n"
        blocks.append(f"[{label}] {page.url}\nTitle: {page.title}\n{extra}Text:\n{page.text[:2500]}")
    if bundle.compliance:
        blocks.append(f"Detected compliance keywords on site: {', '.join(bundle.compliance)}")
    if bundle.github:
        gh = bundle.github
        repos = "; ".join(
            f"{r['name']} (★{r['stars']}, {r['language'] or 'n/a'}) {r['description']}" for r in gh.get("top_repos", [])
        )
        blocks.append(
            f"[GitHub] {gh['url']} ({gh.get('discovered_via', '')})\nOrg: {gh.get('name')} — {gh.get('description')}\n"
            f"Public repos: {gh.get('public_repos')}\nTop repos: {repos}\nLanguages: {', '.join(gh.get('languages', []))}"
        )
    if bundle.news:
        lines = [
            f"{i}. {h.title}{f' ({h.date})' if h.date else ''} — {h.snippet[:260]} <{h.url}>"
            for i, h in enumerate(bundle.news, 1)
        ]
        blocks.append("[News]\n" + "\n".join(lines))
    if bundle.team_page:
        blocks.append(f"[Team] {bundle.team_page.url}\n{bundle.team_page.text[:2000]}")
    if bundle.people_hits:
        lines = [f"{i}. {h.title} \u00b7 {h.snippet[:240]} <{h.url}>" for i, h in enumerate(bundle.people_hits[:10], 1)]
        blocks.append("[People] leadership search results:\n" + "\n".join(lines))
    candidates = bundle.decision_maker_options()
    if candidates:
        lines = [
            f"{i}. full_name={c['full_name']} | role={c['role']} | linkedin_url={c['linkedin_url']} | from={c['origin']}"
            for i, c in enumerate(candidates, 1)
        ]
        blocks.append("[Contacts] people already parsed from the evidence:\n" + "\n".join(lines))
    if bundle.kb:
        keys = ("company_name", "product_and_icp", "gtm_motion", "pricing_tier_summary", "signals")
        kb = {k: bundle.kb[k] for k in keys if k in bundle.kb}
        if bundle.kb.get("casual"):
            kb["opener_hint"] = bundle.kb["casual"]
        blocks.append(
            "[Reference] curated, manually verified notes; use them to fill gaps the live evidence doesn't cover. "
            "If opener_hint is present, build sentence 1 of the email around it:\n" + json.dumps(kb, ensure_ascii=False)
        )
    text = "\n\n".join(blocks)
    return text[:MAX_CONTEXT_CHARS]


async def _repair_outreach(client, draft: str, issues: List[str], first_name: str, seller_context: str, signals: List[str]) -> Optional[str]:
    prompt = (
        f"Rewrite this cold email so it fixes: {'; '.join(issues)}.\n"
        f'Rules: start with "Hey {first_name}," then a casual 4-6 word mention of what they ship; 2-3 short '
        "sentences; 30-40 words; no em-dashes, en-dashes or double hyphens; no dates, no parentheses; no "
        f"exclamation marks; none of these words: {', '.join(BANNED_DISPLAY)}. Keep it peer-to-peer and plain.\n"
        f"Seller context: {seller_context}\nSignals: {' | '.join(signals)}\n\nDraft:\n{draft}\n\n"
        "Return only the email text."
    )
    resp = await client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=220,
    )
    return (resp.choices[0].message.content or "").strip().strip('"')


async def synthesize(bundle: "SourceBundle", seller_context: str) -> Optional[EnrichedCompany]:
    """Returns None when no API key is set or the call fails; callers fall back to rules."""
    if not available():
        return None
    client = _client()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_evidence(bundle, seller_context)},
    ]
    result: Optional[EnrichedCompany] = None
    try:
        completion = await client.beta.chat.completions.parse(
            model=OPENAI_MODEL,
            messages=messages,
            response_format=EnrichedCompany,
            temperature=0.3,
            max_tokens=1100,
        )
        message = completion.choices[0].message
        result = message.parsed if not getattr(message, "refusal", None) else None
    except Exception as exc:
        log.warning("structured parse failed (%s); retrying in JSON mode", type(exc).__name__)
        try:
            schema = json.dumps(EnrichedCompany.model_json_schema())
            completion = await client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages + [{"role": "user", "content": f"Return only JSON matching this schema:\n{schema}"}],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=1100,
            )
            result = EnrichedCompany.model_validate_json(completion.choices[0].message.content or "{}")
        except (ValidationError, Exception) as exc2:
            log.warning("LLM synthesis failed: %s", exc2)
            return None

    if result is None:
        return None

    if "low" in (result.fit_tier or "").lower():
        result.ai_outreach = ""
        return result
    first_name = first_name_of(result.decision_maker.full_name) or f"{result.company_name} team"
    issues = find_violations(result.ai_outreach, first_name, seller_context)
    if issues:
        try:
            fixed = await _repair_outreach(client, result.ai_outreach, issues, first_name, seller_context, result.tech_and_live_signals)
            if fixed:
                result.ai_outreach = fixed
        except Exception as exc:
            log.info("outreach repair failed: %s", exc)
    return result
