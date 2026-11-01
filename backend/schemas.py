"""Pydantic models for the structured enrichment output.

`DecisionMaker` and `EnrichedCompany` are the strict schema the LLM must fill.
`EnrichmentRow` is what the API returns: the same fields plus pipeline metadata.
Optional/List typing is used (not `X | None`) so this runs on Python 3.9.
"""
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class DecisionMaker(BaseModel):
    full_name: str = Field(description="Real person's name, copied from the LinkedIn candidates.")
    role: str = Field(description='Exact title, e.g. "Co-Founder & CTO".')
    linkedin_url: str = Field(description="Full https://www.linkedin.com/in/... URL from the candidates.")
    work_email: str = Field(description='Inferred work email, e.g. "tuomas@linear.app".')
    email_status: str = Field(description='"MX Verified" or "Pattern Inferred".')


class EnrichedCompany(BaseModel):
    domain: str
    company_name: str
    product_and_icp: str = Field(
        description="One crisp sentence, no buzzwords: what they build and who buys it."
    )
    gtm_motion: str = Field(
        description='e.g. "Usage-Based", "Freemium PLG", "Sales-Led Enterprise", "Self-Serve SaaS".'
    )
    pricing_tier_summary: str = Field(
        description='Concrete pricing, e.g. "$20/user/mo + usage", "2.9% + 30¢ per tx".'
    )
    tech_and_live_signals: List[str] = Field(
        description='Exactly 3 items prefixed "Trigger: ", "Stack/GitHub: ", "Compliance: ".'
    )
    decision_maker: DecisionMaker
    ai_outreach: str = Field(description="3-sentence cold email, 55-65 words, to the decision maker.")
    sources_used: List[str] = Field(
        description='Subset of ["Website", "Pricing", "GitHub", "News", "LinkedIn"]. Never "AI".'
    )


class EnrichmentRow(EnrichedCompany):
    status: str = "success"
    error: Optional[str] = None
    cached: bool = False
    generated_by: str = "rules"  # "llm" | "rules" | "research-snapshot"
    email_alternates: List[str] = []
    source_urls: Dict[str, List[str]] = {}
    fallbacks: List[str] = []  # fields filled from curated reference data
    snapshot_date: Optional[str] = None
    elapsed_ms: Optional[int] = None
