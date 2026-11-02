"""Manually verified reference data for the default domains, used only to fill gaps when live
sources are blocked. `fit` and `outreach_default` apply to the default seller context only."""
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
            "Launch: Link agent mode and the Machine Payments Protocol with Tempo (Sessions, Apr 2026).",
            "Stack: official stripe-node, stripe-python and stripe-go SDKs plus an agent toolkit for LLM tool-calling.",
            "Trust: PCI DSS Level 1; SOC 1 and SOC 2 Type II.",
        ],
        "fit": {
            "tier": "Strong Fit",
            "reason": "Agentic checkout puts LLM decisions on the payment path, where a hallucinated cart item becomes a real charge.",
        },
        "decision_maker": {
            "full_name": "Emily Glassberg Sands",
            "role": "Head of Data & AI",
            "linkedin_url": "https://www.linkedin.com/in/egsands",
        },
        "casual": "saw you're rolling out agent checkout on Link",
        "outreach_default": (
            "Hey Emily, saw you're rolling out agent checkout on Link. We help teams catch hallucinated cart "
            "items and policy misses before an agent actually triggers a charge. Are you building evals for "
            "that in-house, or open to a quick look?"
        ),
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
            "Launch: Custom Agents on metered credits (May 2026), plus a Developer Platform for Workers and external agents.",
            "Stack: makenotion/notion-sdk-js (TypeScript) and notion-mcp-server on the public REST API.",
            "Trust: SOC 2 Type II, ISO 27001, GDPR; HIPAA BAA on Enterprise.",
        ],
        "fit": {
            "tier": "Strong Fit",
            "reason": "Custom Agents retrieve across permissioned workspace pages, so retrieval regressions reach users directly.",
        },
        "decision_maker": {
            "full_name": "Max Schoening",
            "role": "CTO",
            "linkedin_url": "https://www.linkedin.com/in/max-schoening",
        },
        "casual": "been testing Notion's custom agents across workspace docs and Slack",
        "outreach_default": (
            "Hey Max, been testing Notion's custom agents across workspace docs and Slack. How are you guys "
            "making sure a model or index update doesn't quietly pull from a stale page? Built a lightweight "
            "tool to replay agent runs if you're open to a peek."
        ),
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
            "Launch: AI Gateway per-user budgets and multi-provider fallbacks; Vercel Sandbox GA on Fluid compute.",
            "Stack: vercel/next.js, vercel/ai (AI SDK) and turborepo; TypeScript-first with Rust tooling.",
            "Trust: SOC 2 Type 2, ISO 27001:2022, PCI DSS; HIPAA BAA on Pro and Enterprise.",
        ],
        "fit": {
            "tier": "Strong Fit",
            "reason": "AI Gateway routes production LLM traffic across providers, so fallback latency and quality shifts are core risks.",
        },
        "decision_maker": {
            "full_name": "Malte Ubl",
            "role": "CTO",
            "linkedin_url": "https://www.linkedin.com/in/malteubl",
        },
        "casual": "saw AI Gateway is handling multi-provider fallbacks on Fluid compute now",
        "outreach_default": (
            "Hey Malte, saw AI Gateway is handling multi-provider fallbacks on Fluid compute now. When a request "
            "falls back to a backup model, how are teams tracking shifts in answer quality vs latency? Open to "
            "seeing how we score fallback paths?"
        ),
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
            "Launch: Linear Agent went GA (Jun 2026) alongside Triage rules, Diffs and guided code reviews.",
            "Stack: linear/linear monorepo with the TypeScript SDK for the GraphQL API, plus an MCP server.",
            "Trust: SOC 2 Type II; HIPAA listed on linear.app/security.",
        ],
        "fit": {
            "tier": "Moderate Fit",
            "reason": "Triage and review agents are real LLM workflows, but still a feature layer on a non-AI core product.",
        },
        "decision_maker": {
            "full_name": "Tuomas Artman",
            "role": "Co-Founder & CTO",
            "linkedin_url": "https://www.linkedin.com/in/tuomasartman",
        },
        "casual": "been playing with the new Linear Agent for auto-triage",
        "outreach_default": (
            "Hey Tuomas, been playing with the new Linear Agent for auto-triage. How are you testing that prompt "
            "or model updates don't quietly mislabel bug priorities? We built a simple way to replay real triage "
            "traces if you're ever curious."
        ),
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
            "Launch: accounting agents that run close and reconciliation, plus an AI-agent card with Visa.",
            "Traction: reported $60B valuation round (Oct 2026), four months after a $44B Series F.",
            "Trust: SOC 1 and SOC 2 Type II, ISO 27001, PCI DSS (trust.ramp.com).",
        ],
        "fit": {
            "tier": "Strong Fit",
            "reason": "Accounting agents extract invoices and post to ledgers, where one hallucinated line item becomes a financial error.",
        },
        "decision_maker": {
            "full_name": "Rahul Sengottuvelu",
            "role": "CTO",
            # No public profile URL could be verified, so this is a LinkedIn people search.
            "linkedin_url": "https://www.linkedin.com/search/results/people/?keywords=Rahul+Sengottuvelu+Ramp",
        },
        "casual": "saw Ramp's accounting agents are handling invoice close and vendor payouts directly now",
        "outreach_default": (
            "Hey Rahul, saw Ramp's accounting agents are handling invoice close and vendor payouts directly now. "
            "How is your team testing that prompt changes don't let a bad line item slip into the ledger? Open to "
            "a quick look at how we run invoice evals?"
        ),
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


# Contact-and-context entries for the Indian AI ecosystem demo set (verified 2026-11-02). Partial on
# purpose: no fit/outreach, so drafts are always written live against the user's own value prop.
KNOWLEDGE.update({
    "senseai.ai": {
        "company_name": "SenseAI Ventures",
        "investor": True,
        # Curated by the user for the SenseAI demo; these always win over live extraction.
        "pinned": ["product_and_icp", "gtm_motion", "pricing_tier_summary", "signals"],
        "product_and_icp": "Early-stage venture fund backing AI-native startups across India and globally.",
        "gtm_motion": "Early-Stage VC",
        "pricing_tier_summary": "Seed & Pre-Series A (20+ AI cos)",
        "signals": [
            "Focus: Backs AI-native startups across infra, healthcare & enterprise apps",
            "Portfolio: 20+ AI companies incl. Pipeshift, Confido Health, CureSkin & Skit.ai",
            "Stack: Runs Haystack, an in-house AI platform for sourcing, lead enrichment & deal memos",
        ],
        "decision_maker": {
            "full_name": "Rahul Agarwalla",
            "role": "Founding & Managing Partner",
            "linkedin_url": "https://www.linkedin.com/search/results/people/?keywords=Rahul+Agarwalla+SenseAI",
        },
        "casual": "saw you run sourcing, lead enrichment and deal memos on Haystack",
        "notes": (
            "Shubham Titare is Principal. Portfolio names verified via F4/Inc42; the 20+ count and Haystack "
            "are per senseai.ai (user-provided)."
        ),
    },
    "sarvam.ai": {
        "company_name": "Sarvam AI",
        "product_and_icp": (
            "Sovereign generative AI for India: Indic-language LLMs plus speech, translation and chat APIs for "
            "enterprises, developers and government."
        ),
        "signals": [
            "Launch: Sarvam 30B and 105B models (Feb 2026), in beta as Indus and later open-sourced.",
            "Traction: Series A from Lightspeed, Peak XV and Khosla; reported talks on a $250M round (Mar 2026).",
            "Scale: speech, translation and chat APIs across 10+ Indian languages.",
        ],
        "decision_maker": {
            "full_name": "Vivek Raghavan",
            "role": "Co-Founder",
            "linkedin_url": "https://www.linkedin.com/search/results/people/?keywords=Vivek+Raghavan+Sarvam+AI",
        },
        "casual": "saw the Sarvam 105B open-weights release",
        "notes": "Co-founded with Pratyush Kumar (Aug 2023); sources disagree on which co-founder holds the CEO title.",
    },
    "bolna.ai": {
        "company_name": "Bolna",
        "product_and_icp": (
            "Voice AI platform where enterprises build, test, deploy and monitor multilingual voice agents for "
            "Indian languages."
        ),
        "signals": [
            "Product: platform to build, test, deploy and monitor multilingual enterprise voice agents.",
            "Traction: $6.3M seed led by General Catalyst; Y Combinator F25 batch.",
            "Scale: 500K+ voice conversations a month across 10+ Indian languages (company figure).",
        ],
        "decision_maker": {
            "full_name": "Prateek Sachan",
            "role": "Co-Founder & CTO",
            "linkedin_url": "https://www.linkedin.com/search/results/people/?keywords=Prateek+Sachan+Bolna",
        },
        "casual": "saw Bolna is running voice agents across 10+ Indian languages",
        "notes": "Maitreya Wagh is Co-Founder & CEO.",
    },
    "razorpay.com": {
        "company_name": "Razorpay",
        "product_and_icp": (
            "Payments, banking and payroll stack for Indian businesses, from startups to large enterprises."
        ),
        "signals": [
            "Launch: RAY, an AI account manager on WhatsApp built with IndusInd Bank (Sep 2026).",
            "Stack: Agent Studio on Anthropic's Claude Agent SDK; agentic UPI payments with NPCI.",
            "Scale: reportedly weighing a confidential IPO filing at around a $5B valuation (Apr 2026).",
        ],
        "decision_maker": {
            "full_name": "Harshil Mathur",
            "role": "Co-Founder & CEO",
            "linkedin_url": "https://www.linkedin.com/search/results/people/?keywords=Harshil+Mathur+Razorpay",
        },
        "casual": "saw RAY is taking actions for merchants on WhatsApp now",
        "notes": "Shashank Kumar is Co-Founder & MD. US servers are served the Razorpay USA site.",
    },
    "zeptonow.com": {
        "company_name": "Zepto",
        "product_and_icp": "10-minute grocery and essentials delivery app for urban Indian consumers, run on dark stores.",
        "signals": [
            "Product: 10-minute delivery of groceries and essentials from a dark-store network.",
            "Traction: launch merchant for Razorpay and NPCI agentic UPI payments on Claude (Feb 2026).",
            "",
        ],
        "decision_maker": {
            "full_name": "Aadit Palicha",
            "role": "Co-Founder & CEO",
            "linkedin_url": "https://www.linkedin.com/search/results/people/?keywords=Aadit+Palicha+Zepto",
        },
        "casual": "saw Zepto went live with agentic UPI checkout on Claude",
        "notes": "Kaivalya Vohra is Co-Founder.",
    },
    "chaayos.com": {
        "company_name": "Chaayos",
        "product_and_icp": "Chai cafe chain with dine-in, delivery and packaged chai for urban Indian consumers.",
        "signals": ["Product: made-to-order chai and snacks across cafes and delivery apps.", "", ""],
        "decision_maker": {
            "full_name": "Nitin Saluja",
            "role": "Co-Founder & CEO",
            "linkedin_url": "https://www.linkedin.com/search/results/people/?keywords=Nitin+Saluja+Chaayos",
        },
        "notes": "Co-founded with Raghav Verma.",
    },
    "chargebee.com": {
        "company_name": "Chargebee",
        "product_and_icp": "Subscription billing and revenue management software for SaaS and subscription businesses.",
        "signals": ["Product: subscription billing, invoicing and revenue recognition, including usage-based models.", "", ""],
        "decision_maker": {
            "full_name": "Krish Subramanian",
            "role": "Co-Founder & CEO",
            "linkedin_url": "https://www.linkedin.com/search/results/people/?keywords=Krish+Subramanian+Chargebee",
        },
    },
})

ALIASES = {"notion.com": "notion.so", "linear.com": "linear.app", "tryramp.com": "ramp.com"}


def lookup(domain: str) -> Optional[dict]:
    domain = domain.lower()
    return KNOWLEDGE.get(ALIASES.get(domain, domain))
