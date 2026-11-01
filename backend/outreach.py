"""Guardrails for the AI OUTREACH column + a deterministic composer used without an LLM."""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

MIN_WORDS = 45
MAX_WORDS = 70  # 55-65 target; small tolerance so the greeting isn't the deciding word
MAX_SENTENCES = 3

# (pattern, safe replacement). Patterns are case-insensitive.
BANNED: List[Tuple[str, str]] = [
    (r"\bI (?:really |truly )?admire\b", "I noticed"),
    (r"\bempowering\b", "helping"),
    (r"\bempowers\b", "helps"),
    (r"\bempower(?:ed)?\b", "help"),
    (r"\bsynerg(?:y|ies|istic)\b", "overlap"),
    (r"\bthrilled\b", "glad"),
    (r"\bgame[\s-]?changers?\b", "big shift"),
    (r"\bgame[\s-]?changing\b", "notable"),
    (r"\bstreamlines\b", "simplifies"),
    (r"\bstreamlined\b", "simplified"),
    (r"\bstreamlining\b", "simplifying"),
    (r"\bstreamline\b", "simplify"),
    (r"\beffortless(?:ly)?\b", ""),
    (r"\blove how you\b", "noticed you"),
    (r"\bseamless(?:ly)?\b", ""),
    (r"\brevolutioniz(?:e|es|ing)\b", "change"),
    (r"\bcutting[\s-]edge\b", "new"),
    (r"\bleverag(?:e|es|ing)\b", "use"),
    (r"\bexcited\b", "curious"),
    (r"\bunlock(?:s|ing)?\b", "open up"),
]
BANNED_DISPLAY = [
    "I admire", "empower", "synergies", "thrilled", "game changer", "streamlines",
    "effortlessly", "love how you", "seamless", "revolutionize", "cutting-edge",
    "leverage", "excited", "unlock",
]


def word_count(text: str) -> int:
    return len([w for w in re.split(r"\s+", text.strip()) if re.search(r"\w", w)])


def split_sentences(text: str) -> List[str]:
    body = re.sub(r"^\s*Hi [^—\-,]+[—\-,]\s*", "", text.strip())
    parts = re.split(r"(?<=[.?])\s+(?=[A-Z\"“])", body)
    return [p for p in parts if p.strip()]


def find_violations(text: str, first_name: Optional[str]) -> List[str]:
    issues: List[str] = []
    for pattern, _ in BANNED:
        match = re.search(pattern, text, re.I)
        if match:
            issues.append(f'banned phrase "{match.group(0)}"')
    if "!" in text:
        issues.append("exclamation mark")
    if first_name and not re.match(rf"^\s*Hi {re.escape(first_name)}\s*[—\-,]", text):
        issues.append(f'must start with "Hi {first_name} —"')
    words = word_count(text)
    if words > MAX_WORDS:
        issues.append(f"too long ({words} words, max 65)")
    if words < MIN_WORDS:
        issues.append(f"too short ({words} words, min 55)")
    if len(split_sentences(text)) > MAX_SENTENCES:
        issues.append("more than 3 sentences")
    return issues


def sanitize(text: str, first_name: Optional[str]) -> str:
    """Last-resort cleanup: strip banned phrasing, fix the greeting, cap to 3 sentences."""
    for pattern, replacement in BANNED:
        text = re.sub(pattern, replacement, text, flags=re.I)
    text = text.replace("!", ".")
    text = re.sub(r"\s{2,}", " ", text).replace(" .", ".").replace(" ,", ",").strip()
    sentences = split_sentences(text)[:MAX_SENTENCES]
    greeting = f"Hi {first_name} —" if first_name else "Hi there —"
    return f"{greeting} {' '.join(sentences)}".strip()


# ---------------------------- rules-based composer ----------------------------

PAIN_RE = re.compile(
    r"\b(?:catch(?:es)?|detect(?:s)?|flag(?:s)?|prevent(?:s)?|find(?:s)?|monitor(?:s)?|"
    r"track(?:s)?|reduce(?:s)?|eliminate(?:s)?|fix(?:es)?|stop(?:s)?)\s+(.+?)(?:\s+(?:in|across|for)\s+.+?)?\.?$",
    re.I,
)


def derive_pain(seller_context: str) -> Optional[str]:
    """'...engine that catches hallucinations, retrieval regressions, and latency spikes in prod' ->
    'hallucinations, retrieval regressions, and latency spikes'."""
    match = PAIN_RE.search(seller_context.strip())
    if not match:
        return None
    pain = match.group(1).strip().rstrip(".")
    return pain if 2 <= len(pain.split()) <= 14 else None


def _seller_clause(seller_context: str) -> str:
    clause = seller_context.strip().rstrip(".")
    clause = re.sub(r"^(?:we|our team|i)\s+", "", clause, flags=re.I)
    words = clause.split()
    return " ".join(words[:16])


def compose_outreach(
    first_name: Optional[str],
    company_name: str,
    hook_sentence: str,
    seller_context: str,
    surface: Optional[str] = None,
) -> str:
    greeting = f"Hi {first_name} —" if first_name else f"Hi {company_name} team —"
    subject = surface or "that"
    pain = derive_pain(seller_context)
    if pain:
        ai_seller = re.search(r"\b(evals?|evaluation|LLMs?|AI|models?|hallucinat\w*)\b", seller_context, re.I)
        tail = "before any offline eval flags them" if ai_seller else "before anyone downstream notices"
        pain_sentence = f"Once {subject} runs on live customer data, {pain} tend to surface in production {tail}."
    else:
        pain_sentence = (
            f"We work on the layer underneath {subject} ({_seller_clause(seller_context)}), "
            "which is usually where the first scaling issue shows up."
        )
    cta = "How are you catching those today — open to a 15-minute look at how we'd trace it on your stack?"
    text = f"{greeting} {hook_sentence.strip()} {pain_sentence} {cta}"
    # Keep it inside the word budget by shortening the CTA, then the hook.
    if word_count(text) > 65:
        cta = "Open to a quick look at how we'd trace that on your stack?"
        text = f"{greeting} {hook_sentence.strip()} {pain_sentence} {cta}"
    if word_count(text) > 65:
        words = hook_sentence.split()
        trimmed = " ".join(words[: max(8, len(words) - (word_count(text) - 65))]).rstrip(",;:") + "."
        text = f"{greeting} {trimmed} {pain_sentence} {cta}"
    return sanitize(text, first_name) if first_name else text


def hook_from_headline(company_name: str, headline: str) -> str:
    """Turn a news/changelog headline into a neutral first sentence."""
    headline = re.sub(r"\s+[|\-–—]\s+[^|\-–—]{2,40}$", "", headline).strip().rstrip(".")
    words = headline.split()
    if len(words) > 14:
        headline = " ".join(words[:14]) + "…"
    return f"Saw the recent {company_name} news: “{headline}”."
