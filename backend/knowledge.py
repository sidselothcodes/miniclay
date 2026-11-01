"""Curated, manually verified reference data for the default demo domains.

The live pipeline uses this only to fill gaps when a source is blocked or
rate-limited (common on cloud IPs), so the demo never renders empty cells.
Fields filled from here are listed in the row's `fallbacks`, and they never
add a badge to `sources_used`. Verified via web research on VERIFIED_AT.
"""
from __future__ import annotations

from typing import Dict, Optional

VERIFIED_AT = "2026-11-01"

KNOWLEDGE: Dict[str, dict] = {
    "stripe.com": {
        "company_name": "Stripe",
        "product_and_icp": (
            "Payments, billing and money-movement APIs for internet businesses, from seed-stage "
            "startups to public enterprises and AI labs."
        ),
        "gtm_motion": "Usage-Based",
        "pricing_tier_summary": "2.9% + 30¢ per card tx · custom volume rates",
        "signals": [
            "Trigger: Sessions 2026 (Apr) shipped 288 launches, incl. Machine Payments Protocol with Tempo "
            "and Link agent mode.",
            "Stack/GitHub: official stripe-node, stripe-python and stripe-go SDKs plus an agent toolkit for "
            "LLM tool-calling.",
            "Compliance: PCI DSS Level 1; SOC 1 and SOC 2 Type II.",
        ],
        "decision_maker": {
            "full_name": "Emily Glassberg Sands",
            "role": "Head of Data & AI",
            "linkedin_url": "https://www.linkedin.com/in/egsands",
        },
        "hook": (
            "Saw Sessions 2026 put agents directly on the payment path, from Link's agent mode to the "
            "Machine Payments Protocol with Tempo."
        ),
        "surface": "agent-initiated checkout",
        "source_urls": {
            "Website": ["https://stripe.com/blog/everything-we-announced-at-sessions-2026"],
            "Pricing": ["https://stripe.com/pricing"],
            "GitHub": ["https://github.com/stripe"],
            "News": [
                "https://stripe.com/blog/everything-we-announced-at-sessions-2026",
                "https://www.emarketer.com/content/stripe-releases-hundreds-of-features-stripe-sessions--dials-on-agentic-crypto-solutions",
            ],
            "LinkedIn": ["https://www.linkedin.com/in/egsands"],
        },
        "notes": "CTO seat publicly unfilled since Rahul Patil joined Anthropic (late 2025); Head of Data & AI is the closest technical buyer.",
    },
    "notion.so": {
        "company_name": "Notion",
        "product_and_icp": (
            "Docs, wikis, projects and AI agents in one workspace, adopted bottom-up by teams and expanded "
            "into company-wide contracts."
        ),
        "gtm_motion": "Freemium PLG",
        "pricing_tier_summary": "Free · Plus $10/seat · Business $20/seat · agents $10/1K credits",
        "signals": [
            "Trigger: Custom Agents moved to metered credits (May 2026) alongside a new Developer Platform "
            "for Workers and external agents.",
            "Stack/GitHub: makenotion/notion-sdk-js (TypeScript) and notion-mcp-server on the public REST API.",
            "Compliance: SOC 2 Type II, ISO 27001, GDPR; HIPAA BAA on Enterprise.",
        ],
        "decision_maker": {
            "full_name": "Max Schoening",
            "role": "CTO",
            "linkedin_url": "https://www.linkedin.com/in/max-schoening",
        },
        "hook": (
            "Saw Custom Agents moved to metered credits and can now act across workspace pages and "
            "external tools through the Developer Platform."
        ),
        "surface": "permission-scoped agent retrieval",
        "source_urls": {
            "Website": ["https://www.notion.com/blog/meet-max-schoening-notion-cto"],
            "Pricing": ["https://www.notion.com/help/custom-agent-pricing", "https://www.notion.com/pricing"],
            "GitHub": ["https://github.com/makenotion"],
            "News": ["https://dynamicbusiness.com/ai-tools/notion-developer-platform-for-custom-workflows.html"],
            "LinkedIn": ["https://www.linkedin.com/in/max-schoening"],
        },
    },
    "vercel.com": {
        "company_name": "Vercel",
        "product_and_icp": (
            "Frontend and AI cloud (Next.js hosting, AI SDK, AI Gateway) bought by product engineering "
            "teams shipping web and agent workloads."
        ),
        "gtm_motion": "Usage-Based PLG",
        "pricing_tier_summary": "Hobby free · Pro $20/seat/mo + $20 usage credit · on-demand",
        "signals": [
            "Trigger: AI Gateway added per-user budgets for AI SDK 6 apps; Vercel Sandbox went GA "
            "(Jan 2026) on Fluid compute.",
            "Stack/GitHub: vercel/next.js, vercel/ai (AI SDK) and turborepo; TypeScript-first with Rust tooling.",
            "Compliance: SOC 2 Type 2, ISO 27001:2022, PCI DSS; HIPAA BAA on Pro and Enterprise.",
        ],
        "decision_maker": {
            "full_name": "Malte Ubl",
            "role": "CTO",
            "linkedin_url": "https://www.linkedin.com/in/malteubl",
        },
        "hook": (
            "Saw AI Gateway added per-user budgets in front of AI SDK 6 apps, with multi-provider fallbacks "
            "running on Fluid compute."
        ),
        "surface": "a multi-model fallback chain",
        "source_urls": {
            "Website": ["https://vercel.com/docs/security/compliance"],
            "Pricing": ["https://vercel.com/docs/plans/pro", "https://vercel.com/pricing"],
            "GitHub": ["https://github.com/vercel"],
            "News": ["https://community.vercel.com/t/vercel-weekly-2026-09-07/48955"],
            "LinkedIn": ["https://www.linkedin.com/in/malteubl"],
        },
    },
    "linear.app": {
        "company_name": "Linear",
        "product_and_icp": (
            "Issue tracking and product planning for software teams, adopted bottom-up by engineers and "
            "expanded to whole product orgs."
        ),
        "gtm_motion": "Freemium PLG",
        "pricing_tier_summary": "Free · Basic $10/user/mo · Business $16/user/mo (annual)",
        "signals": [
            "Trigger: Linear Agent went GA (Jun 2026) alongside Triage rules, Diffs and guided code reviews.",
            "Stack/GitHub: linear/linear monorepo with the TypeScript SDK for the GraphQL API, plus an MCP server.",
            "Compliance: SOC 2 Type II; HIPAA listed on linear.app/security.",
        ],
        "decision_maker": {
            "full_name": "Tuomas Artman",
            "role": "Co-Founder & CTO",
            "linkedin_url": "https://www.linkedin.com/in/tuomasartman",
        },
        "hook": (
            "Saw Linear Agent go GA alongside Diffs and guided reviews, so model output now lands directly "
            "in triage and code review."
        ),
        "surface": "automated triage",
        "source_urls": {
            "Website": ["https://linear.app/security"],
            "Pricing": ["https://linear.app/pricing"],
            "GitHub": ["https://github.com/linear"],
            "News": ["https://linear.app/changelog", "https://pricingsaas.com/companies/linear/diffs/2026W23"],
            "LinkedIn": ["https://www.linkedin.com/in/tuomasartman"],
        },
    },
    "ramp.com": {
        "company_name": "Ramp",
        "product_and_icp": (
            "Corporate cards, bill pay, procurement and accounting automation for finance teams from "
            "startups to enterprise."
        ),
        "gtm_motion": "Freemium + Sales-Led",
        "pricing_tier_summary": "Free · Plus $15/user/mo + platform fee · Enterprise custom",
        "signals": [
            "Trigger: reported $60B round (Oct 2026) after a $44B Series F; accounting agents and an "
            "AI-agent card with Visa.",
            "Stack/GitHub: ramp-public/ramp-mcp (Python MCP server over the Developer API); in-house Inspect "
            "coding agent.",
            "Compliance: SOC 1 and SOC 2 Type II, ISO 27001, PCI DSS (trust.ramp.com).",
        ],
        "decision_maker": {
            "full_name": "Rahul Sengottuvelu",
            "role": "CTO (prev. Head of Applied AI)",
            # No public profile URL could be verified, so we link a LinkedIn people search instead.
            "linkedin_url": "https://www.linkedin.com/search/results/people/?keywords=Rahul+Sengottuvelu+Ramp",
        },
        "hook": (
            "Saw Ramp's accounting agents now run close and reconciliation on their own, with an agent "
            "card paying vendors directly."
        ),
        "surface": "invoice extraction",
        "source_urls": {
            "Website": ["https://ramp.com/security"],
            "Pricing": ["https://ramp.com/pricing"],
            "GitHub": ["https://github.com/ramp-public"],
            "News": [
                "https://www.bankingdive.com/news/ramp-names-karim-atiyeh-co-ceo-glyman-cto-Rahul-Sengottuvelu/824229/",
                "https://techcrunch.com/2026/10/15/ramp-reaches-60b-valuation-as-it-pushes-deeper-into-ai",
            ],
        },
        "notes": "Karim Atiyeh (ex-CTO) became co-CEO in mid-2026; Rahul Sengottuvelu took over as CTO.",
    },
}

ALIASES = {"notion.com": "notion.so", "linear.com": "linear.app", "tryramp.com": "ramp.com"}


def lookup(domain: str) -> Optional[dict]:
    domain = domain.lower()
    return KNOWLEDGE.get(ALIASES.get(domain, domain))
