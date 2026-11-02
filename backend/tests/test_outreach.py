import pytest

from fit import LOW, MODERATE, STRONG, assess_fit, normalize_tier
from outreach import (
    MAX_WORDS,
    casual_from_headline,
    compose_outreach,
    derive_pain,
    find_violations,
    has_dash,
    sanitize,
    word_count,
)
from settings import DEFAULT_SELLER_CONTEXT

SLOP = (
    "Hi Tuomas — I admire how Linear empowers teams and streamlines triage effortlessly! "
    "Our synergies would be a game changer -- I love how you ship."
)
LECTURE = (
    "Hey Emily, Sessions 2026 (Apr) put agents directly on the payment path, from Link's agent mode "
    "to the Machine Payments Protocol with Tempo, so we should talk about evals for all of it soon."
)


def test_find_violations_flags_banned_words_dashes_and_exclamations():
    issues = " | ".join(find_violations(SLOP, "Tuomas"))
    for phrase in ("I admire", "empowers", "streamlines", "effortlessly", "synergies", "game changer", "love how you"):
        assert phrase in issues
    assert "exclamation mark" in issues
    assert "em-dash" in issues
    assert 'must start with "Hey Tuomas,"' in issues


def test_find_violations_flags_lecturing():
    issues = " | ".join(find_violations(LECTURE, "Emily"))
    assert "date/year" in issues
    assert "parenthetical" in issues


def test_dash_detection():
    assert has_dash("Hey Max — quick question")
    assert has_dash("quick question -- really")
    assert has_dash("quick – question")
    assert not has_dash("in-house auto-triage multi-provider")


def test_sanitize_produces_a_clean_human_greeting():
    cleaned = sanitize(SLOP, "Tuomas")
    assert cleaned.startswith("Hey Tuomas, ")
    assert not has_dash(cleaned)
    remaining = [i for i in find_violations(cleaned, "Tuomas") if not i.startswith("too ")]
    assert remaining == []


def test_derive_pain_from_seller_context():
    assert derive_pain(DEFAULT_SELLER_CONTEXT) == "hallucinations, retrieval regressions, and latency spikes"
    assert derive_pain("We sell office furniture.") is None


def test_casual_mention_from_headline():
    assert casual_from_headline("Acme AI", "Acme AI launches Agents API for replaying production traces - TechCrunch") == (
        "saw you just launched Agents API for replaying production traces"
    )
    assert casual_from_headline("Ramp", "Quarterly fintech roundup") == "saw the recent Ramp news"


@pytest.mark.parametrize("context", [
    DEFAULT_SELLER_CONTEXT,
    "We build a data-quality platform that detects schema drift and broken joins in warehouse pipelines.",
    "We sell a managed vector database for retrieval workloads.",
    "An AI SDR that books qualified meetings for home-service companies.",
])
def test_composed_outreach_is_short_and_human(context):
    text = compose_outreach("Tuomas", "Linear", "been playing with the new Linear Agent for auto-triage", context)
    assert text.startswith("Hey Tuomas, been playing")
    assert find_violations(text, "Tuomas") == [], text
    assert 25 <= word_count(text) <= 40
    assert not has_dash(text)


# ------------------------------ fit ------------------------------

def test_normalize_tier():
    assert normalize_tier("strong") == STRONG
    assert normalize_tier("Moderate fit") == MODERATE
    assert normalize_tier("LOW FIT") == LOW
    assert normalize_tier("???") == ""


def test_consumer_brand_is_low_fit_for_ai_seller():
    tier, reason = assess_fit(
        DEFAULT_SELLER_CONTEXT, "Sweet Crumb",
        "Fresh pastries baked daily. Add to cart for delivery. Free shipping on cookie boxes. Gift cards.",
    )
    assert tier == LOW
    assert reason == "Consumer retail brand with no customer-facing LLM workflows in production."


def test_ai_product_is_strong_fit_and_reason_is_short():
    tier, reason = assess_fit(
        DEFAULT_SELLER_CONTEXT, "Acme AI",
        "Evals for LLM agents. Replay any production trace against a new model. RAG retrieval debugging.",
    )
    assert tier == STRONG
    assert len(reason.split()) <= 20
    assert not has_dash(reason)


def test_non_ai_seller_uses_keyword_overlap():
    seller = "We build a data-quality platform that detects schema drift and broken joins in warehouse pipelines."
    tier, _ = assess_fit(seller, "Acme", "Our warehouse sync catches schema drift before dashboards break.")
    assert tier in (STRONG, MODERATE)
    tier, reason = assess_fit(seller, "Sweet Crumb", "Fresh pastries baked daily.")
    assert tier == LOW and "Sweet Crumb" in reason


def test_word_ceiling_is_45():
    assert MAX_WORDS == 45
