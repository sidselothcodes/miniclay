"""LLM output schema (EnrichedCompany) and API row (EnrichmentRow). Uses Optional/List for Python 3.9."""
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
        description='Exactly 3 items with adaptive prefixes: "Launch:"/"Product:", "Stack:"/"Traction:", "Trust:"/"Scale:".'
    )
    fit_tier: str = Field(description='"Strong Fit", "Moderate Fit" or "Low Fit" for the seller\'s product.')
    fit_reason: str = Field(description="One sentence, max 20 words: why this company does or doesn't fit the seller.")
    decision_maker: DecisionMaker
    ai_outreach: str = Field(
        description='2-3 short sentences, 30-40 words, starting "Hey <FirstName>,". Empty string for "Low Fit".'
    )
    sources_used: List[str] = Field(
        description='Subset of ["Website", "Pricing", "GitHub", "News", "LinkedIn"]. Never "AI".'
    )


class EnrichmentRow(EnrichedCompany):
    status: str = "success"
    error: Optional[str] = None
    cached: bool = False
    generated_by: str = "rules"
    email_alternates: List[str] = []
    source_urls: Dict[str, List[str]] = {}
    fallbacks: List[str] = []
    snapshot_date: Optional[str] = None
    elapsed_ms: Optional[int] = None
