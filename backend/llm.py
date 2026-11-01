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

if TYPE_CHECKING:  # pragma: no cover
    from enrichment import SourceBundle

log = logging.getLogger("miniclay.llm")

MAX_CONTEXT_CHARS = 14000

SYSTEM_PROMPT = f"""You are a senior B2B GTM research analyst. You turn raw evidence scraped about ONE company into a strict JSON record for outbound sales.

Ground rules:
- Use only facts present in the evidence blocks ([Website], [Pricing], [GitHub], [News], [LinkedIn], [Reference]). Never invent people, URLs, numbers, launches or certifications.
- Prefer the most recent dated evidence. When evidence for a field is missing, say so plainly instead of guessing.

Fields:
- company_name: the short brand name.
- product_and_icp: ONE sentence, max 22 words, no buzzwords: what they build and who buys it (team, role or company type).
- gtm_motion: 1-3 words, e.g. "Usage-Based", "Freemium PLG", "Sales-Led Enterprise", "Self-Serve SaaS", "Usage-Based PLG".
- pricing_tier_summary: concrete figures copied from [Pricing], max 70 characters, e.g. "$20/user/mo + usage", "2.9% + 30¢ per tx", "Free · $10–$16/user/mo". If no figures exist: "Custom / contact sales".
- tech_and_live_signals: exactly 3 strings, in this order, each max 18 words (scannable, no filler):
  1. "Trigger: ..." the most recent concrete launch, AI feature, funding round or exec change (with month/year when known).
  2. "Stack/GitHub: ..." public repos, SDKs, APIs and languages from [GitHub] (name real repos).
  3. "Compliance: ..." certifications found (SOC 2, ISO 27001, HIPAA, PCI DSS, GDPR, ...). If none: "Compliance: not published on site".
- decision_maker: pick exactly ONE person from the [LinkedIn] candidates (copy full_name, role, linkedin_url, work_email and email_status exactly as given). Prefer CTO > Head of AI > VP of Engineering > technical co-founder.
- sources_used: only labels of evidence blocks you actually used, from ["Website", "Pricing", "GitHub", "News", "LinkedIn"]. Never output "AI" or "Reference".
- ai_outreach: a cold email from the SELLER to the decision maker, following the outreach rules.

Outreach rules (strict):
1. Start exactly with "Hi <FirstName> —" using the decision maker's first name.
2. Exactly 3 sentences, 55-65 words total. No sign-off, no signature, no emojis.
3. Sentence 1 (hook): name ONE specific feature, AI capability or launch from tech_and_live_signals. State it; do not compliment it.
4. Sentence 2 (pain): connect that exact feature to one concrete engineering failure mode the seller's product addresses (e.g. permission-aware RAG regressions, latency spikes across model fallbacks, hallucinated invoice line items).
5. Sentence 3 (CTA): one sharp peer-to-peer engineering question, or an offer of a quick look.
6. Banned words and phrases: {", ".join(f'"{w}"' for w in BANNED_DISPLAY)}, and any exclamation mark.
7. Plain technical tone, like one engineer writing to another."""


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
        blocks.append(
            f"[Website] {home.url}\nTitle: {home.title}\nMeta: {home.meta_description}\n"
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
    candidates = bundle.decision_maker_options()
    if candidates:
        lines = [
            f"{i}. full_name={c['full_name']} | role={c['role']} | linkedin_url={c['linkedin_url']} | "
            f"work_email={c['work_email']} | email_status={c['email_status']} | from={c['origin']}"
            for i, c in enumerate(candidates, 1)
        ]
        blocks.append("[LinkedIn] decision-maker candidates (choose one):\n" + "\n".join(lines))
    if bundle.kb:
        kb = {k: bundle.kb[k] for k in ("company_name", "product_and_icp", "gtm_motion", "pricing_tier_summary", "signals") if k in bundle.kb}
        blocks.append(
            "[Reference] curated, manually verified notes; use only to fill gaps the live evidence doesn't cover:\n"
            + json.dumps(kb, ensure_ascii=False)
        )
    text = "\n\n".join(blocks)
    return text[:MAX_CONTEXT_CHARS]


async def _repair_outreach(client, draft: str, issues: List[str], first_name: str, seller_context: str, signals: List[str]) -> Optional[str]:
    prompt = (
        f"Rewrite this cold email so it fixes: {'; '.join(issues)}.\n"
        f'Rules: start with "Hi {first_name} —"; exactly 3 sentences; 55-65 words; no exclamation marks; '
        f"none of these words: {', '.join(BANNED_DISPLAY)}. Keep the same facts.\n"
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

    first_name = (result.decision_maker.full_name or "").split()[0] if result.decision_maker.full_name else None
    issues = find_violations(result.ai_outreach, first_name)
    if issues:
        try:
            fixed = await _repair_outreach(client, result.ai_outreach, issues, first_name or "there", seller_context, result.tech_and_live_signals)
            if fixed:
                result.ai_outreach = fixed
        except Exception as exc:
            log.info("outreach repair failed: %s", exc)
    return result
