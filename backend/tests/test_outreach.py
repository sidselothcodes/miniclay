import pytest

from outreach import compose_outreach, derive_pain, find_violations, sanitize, word_count
from settings import DEFAULT_SELLER_CONTEXT

SLOP = (
    "Hi Tuomas — I admire how Linear empowers teams and streamlines triage effortlessly! "
    "Our synergies would be a game changer. I love how you ship."
)


def test_find_violations_flags_banned_words_and_exclamations():
    issues = " | ".join(find_violations(SLOP, "Tuomas"))
    for phrase in ("I admire", "empowers", "streamlines", "effortlessly", "synergies", "game changer", "love how you"):
        assert phrase in issues
    assert "exclamation mark" in issues


def test_find_violations_checks_greeting():
    assert any("must start with" in i for i in find_violations("Hello Tuomas, quick note.", "Tuomas"))


def test_sanitize_removes_every_banned_phrase():
    cleaned = sanitize(SLOP, "Tuomas")
    remaining = [i for i in find_violations(cleaned, "Tuomas") if not i.startswith("too ")]
    assert remaining == []
    assert cleaned.startswith("Hi Tuomas —")


def test_derive_pain_from_seller_context():
    assert derive_pain(DEFAULT_SELLER_CONTEXT) == "hallucinations, retrieval regressions, and latency spikes"
    assert derive_pain("We sell office furniture.") is None


@pytest.mark.parametrize("context", [
    DEFAULT_SELLER_CONTEXT,
    "We build a data-quality platform that detects schema drift and broken joins in warehouse pipelines.",
    "We sell a managed vector database for retrieval workloads.",
])
def test_composed_outreach_passes_guardrails(context):
    hook = "Saw Linear Agent go GA alongside Diffs and guided reviews, so model output now lands directly in triage and code review."
    text = compose_outreach("Tuomas", "Linear", hook, context, surface="automated triage")
    assert find_violations(text, "Tuomas") == [], text
    assert 45 <= word_count(text) <= 65
