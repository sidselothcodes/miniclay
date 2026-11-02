"""Evidence-based fit tiers: the no-LLM fallback and the honesty floor for LLM output."""
from __future__ import annotations

import re
from typing import List, Tuple

from outreach import DASH_RE, derive_pain

STRONG, MODERATE, LOW = "Strong Fit", "Moderate Fit", "Low Fit"
TIERS = (STRONG, MODERATE, LOW)
MAX_REASON_WORDS = 20

AI_SELLER_RE = re.compile(
    r"\b(LLMs?|AI|evals?|evaluation|hallucinat\w*|agents?|models?|RAG|retrieval|prompts?|inference|"
    r"machine learning|ML|gen ?AI|generative)\b",
    re.I,
)
AI_USAGE: List[Tuple[str, str]] = [
    ("AI agents", r"\bagents?\b|\bagentic\b"),
    ("LLM features", r"\bLLMs?\b|\bGPT[-\s]?\d|\blarge language models?\b|\bprompts?\b"),
    ("AI-powered workflows", r"\bAI\b|\bartificial intelligence\b|\bgen(?:erative)? ?AI\b"),
    ("assistants", r"\bcopilots?\b|\bassistants?\b|\bchatbots?\b"),
    ("model routing", r"\binference\b|\bmodel (?:routing|fallbacks?|providers?)\b|\bAI Gateway\b|\bAI SDK\b"),
    ("retrieval", r"\bRAG\b|\bretrieval\b|\bembeddings?\b|\bsemantic search\b|\bvector\b"),
]
CONSUMER_RE = re.compile(
    r"add to (?:cart|bag)|shop now|free shipping|order online|our menu|bakery|baked|pastr(?:y|ies)|"
    r"apparel|clothing|boutique|skincare|jewel(?:ry|lery)|restaurant|caf[eé]|size guide|"
    r"returns? (?:&|and) exchanges|gift cards?|new arrivals",
    re.I,
)
STOPWORDS = set(
    "about above across after again against also because before being below between build builds built "
    "company companies could during engine every their there these those through under until using "
    "where which while within without would workflows workflow platform teams automated production "
    "product products customers software solution solutions help helps that this with from into your".split()
)


def normalize_tier(raw: str) -> str:
    text = (raw or "").lower()
    if "strong" in text or "high" in text:
        return STRONG
    if "moderate" in text or "medium" in text or "partial" in text:
        return MODERATE
    if "low" in text or "weak" in text or "poor" in text or "no fit" in text:
        return LOW
    return ""


def clean_reason(reason: str) -> str:
    reason = DASH_RE.sub(", ", re.sub(r"\s+", " ", reason or "").strip())
    words = reason.split()
    if len(words) > MAX_REASON_WORDS:
        reason = " ".join(words[:MAX_REASON_WORDS]).rstrip(",;:") + "."
    return reason


def looks_consumer(evidence: str) -> bool:
    # Needs two distinct storefront cues so a B2B site mentioning "gift cards" once isn't flagged.
    return len({m.group(0).lower() for m in CONSUMER_RE.finditer(evidence)}) >= 2


def _ai_hits(evidence: str) -> List[str]:
    return [label for label, pattern in AI_USAGE if re.search(pattern, evidence, re.I)]


def is_consumer_without_ai(seller_context: str, evidence: str) -> bool:
    return bool(AI_SELLER_RE.search(seller_context)) and looks_consumer(evidence) and not _ai_hits(evidence)


def assess_fit(seller_context: str, company_name: str, evidence: str) -> Tuple[str, str]:
    if not evidence.strip():
        return LOW, "Not enough public information to judge fit; verify manually before reaching out."

    if AI_SELLER_RE.search(seller_context):
        hits = _ai_hits(evidence)
        pain = derive_pain(seller_context) or "the problems you solve"
        if not hits and looks_consumer(evidence):
            return LOW, "Consumer retail brand with no customer-facing LLM workflows in production."
        if not hits:
            return LOW, "No customer-facing AI or LLM workflows found in public sources, so little for you to evaluate."
        if len(hits) >= 3:
            return STRONG, clean_reason(f"Public pages show {hits[0]} and {hits[1]}, where {pain} would hit their users.")
        return MODERATE, clean_reason(f"Mentions {hits[0]}, but AI looks like a side feature rather than the core product.")

    terms = []
    for word in re.findall(r"[a-zA-Z][a-zA-Z-]{4,}", seller_context.lower()):
        stem = word[:-1] if word.endswith("s") else word
        if stem not in STOPWORDS and word not in STOPWORDS and stem not in terms:
            terms.append(stem)
    matched = [t for t in terms if re.search(rf"\b{re.escape(t)}", evidence, re.I)]
    if len(matched) >= 3:
        return STRONG, clean_reason(f"Their public pages mention {matched[0]}, {matched[1]} and {matched[2]}, which your product addresses.")
    if matched:
        return MODERATE, clean_reason(f"Some overlap on {matched[0]}, but no clear sign they feel the problem your product solves.")
    return LOW, f"No overlap found between what {company_name} does and what you sell."
