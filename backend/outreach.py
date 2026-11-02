"""Outreach draft guardrails and the no-LLM composer."""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

MIN_WORDS = 20
TARGET_MAX_WORDS = 40
MAX_WORDS = 45
MAX_SENTENCES = 3

# Replacement None means the phrase can't be patched in place; the draft is rewritten instead.
BANNED: List[Tuple[str, Optional[str]]] = [
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
    (r"\blove how you\b", "like how you"),
    (r"\bseamless(?:ly)?\b", ""),
    (r"\brevolutioniz(?:e|es|ing)\b", "change"),
    (r"\bcutting[\s-]edge\b", "new"),
    (r"\bleverag(?:e|es|ing)\b", "use"),
    (r"\bexcited\b", "curious"),
    (r"\bunlock(?:s|ing)?\b", "open up"),
    (r"\bsupport your (?:efforts|goals)\b", None),
    (r"\bexplore how we can\b", None),
    (r"\blet[\u2019']?s connect\b", None),
    (r"\bbrief discussion\b", None),
    (r"\b(?:I see|noticed) (?:that )?you ship\b", None),
    (r"\bI appreciate the\b", None),
    (r"\bmight complement each other\b", None),
    (r"\benhance (?:their|your)\b", None),
]
BANNED_DISPLAY = [
    "I admire", "empower", "synergies", "thrilled", "game changer", "streamlines",
    "effortlessly", "love how you", "seamless", "revolutionize", "cutting-edge",
    "leverage", "excited", "unlock", "support your efforts", "support your goals", "explore how we can",
    "let's connect", "brief discussion", "I see you ship", "I appreciate the", "might complement each other",
    "enhance their",
]

# Em-dash, double hyphen, or a spaced en-dash.
DASH_RE = re.compile(r"\s*(?:—|-{2,}|\s–\s)\s*")
GREETING_RE = re.compile(r"^\s*(?:hey|hi|hello)\s+[^,\u2014\u2013\n]{1,40}?(?:,|\u2014|\u2013|\s-{1,2})\s*", re.I)
CASUAL_OPENERS = {"saw", "been", "noticed", "curious", "seeing", "caught", "read", "looks", "quick", "loved"}


def word_count(text: str) -> int:
    return len([w for w in re.split(r"\s+", text.strip()) if re.search(r"\w", w)])


def split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.?!])\s+(?=[A-Z\"“])", text.strip())
    return [p for p in parts if p.strip()]


def has_dash(text: str) -> bool:
    return bool(DASH_RE.search(text))


def find_violations(text: str, greet_name: Optional[str], seller_context: Optional[str] = None) -> List[str]:
    issues: List[str] = []
    for pattern, _ in BANNED:
        match = re.search(pattern, text, re.I)
        if match:
            issues.append(f'banned phrase "{match.group(0)}"')
    if "!" in text:
        issues.append("exclamation mark")
    if has_dash(text):
        issues.append("em-dash or double hyphen (use a comma or period)")
    if greet_name and not re.match(rf"^Hey {re.escape(greet_name)},\s", text):
        issues.append(f'must start with "Hey {greet_name},"')
    if re.search(r"\b(?:19|20)\d{2}\b", text):
        issues.append("mentions a date/year (don't recite their news back to them)")
    if "(" in text:
        issues.append("parenthetical aside")
    eval_words = r"\bevals?\b|\bevaluation\b"
    if seller_context is not None and re.search(eval_words, text, re.I) and not re.search(eval_words, seller_context, re.I):
        issues.append("mentions evals, which the seller doesn't sell")
    words = word_count(text)
    if words > MAX_WORDS:
        issues.append(f"too long ({words} words, aim for 30-40)")
    if words < MIN_WORDS:
        issues.append(f"too short ({words} words, aim for 30-40)")
    if len(split_sentences(text)) > MAX_SENTENCES:
        issues.append("more than 3 sentences")
    return issues


def sanitize(text: str, greet_name: str) -> str:
    for pattern, replacement in BANNED:
        if replacement is not None:
            text = re.sub(pattern, replacement, text, flags=re.I)
    body = GREETING_RE.sub("", text.replace("!", "."), count=1)
    body = DASH_RE.sub(", ", body)
    body = re.sub(r"\s*\([^)]*\)", "", body)
    body = re.sub(r"\s{2,}", " ", body)
    body = re.sub(r"\s+([,.?])", r"\1", body).replace(",,", ",").replace(", .", ".").strip(" ,")
    first_word = body.split(" ", 1)[0].lower() if body else ""
    if first_word in CASUAL_OPENERS:
        body = body[0].lower() + body[1:]
    sentences = split_sentences(body)[:MAX_SENTENCES]
    greeting = f"Hey {greet_name},"
    return f"{greeting} {' '.join(sentences)}".strip()


# Only defect-catching verbs fit "We help teams catch X before they reach users".
PAIN_RE = re.compile(
    r"\b(?:catch(?:es)?|detect(?:s)?|flag(?:s)?|prevent(?:s)?|stop(?:s)?)\s+(.+?)(?:\s+(?:in|across|for)\s+.+?)?\.?$",
    re.I,
)
HEADLINE_VERBS = {
    "launches": "just launched", "launched": "just launched", "raises": "just raised", "raised": "just raised",
    "ships": "just shipped", "introduces": "just introduced", "unveils": "just unveiled",
    "announces": "just announced", "adds": "just added", "releases": "just released", "debuts": "just debuted",
    "acquires": "just acquired", "opens": "just opened", "expands": "are expanding", "rolls out": "are rolling out",
}


def derive_pain(seller_context: str) -> Optional[str]:
    """'...engine that catches hallucinations and latency spikes in prod' -> 'hallucinations and latency spikes'."""
    match = PAIN_RE.search(seller_context.strip())
    if not match:
        return None
    pain = match.group(1).strip().rstrip(".")
    return pain if 2 <= len(pain.split()) <= 14 else None


def _trim(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return " ".join(words).rstrip(",;:.")
    head = " ".join(words[:max_words])
    # Cut at the last natural break rather than mid-phrase.
    cut = max(head.rfind(","), head.rfind(" in "), head.rfind(" for "), head.rfind(" with "))
    return (head[:cut] if cut > len(head) // 2 else head).rstrip(",;:.")


def _value_sentence(seller_context: str) -> str:
    pain = derive_pain(seller_context)
    if pain:
        return f"We help teams catch {pain} before they reach users."
    clause = re.sub(r"\s+", " ", seller_context.strip().rstrip("."))
    match = re.match(r"^(?:we|i|our team)\s+(.*)$", clause, re.I)
    if match:
        return f"We {_trim(match.group(1), 18)}."
    return f"We build {clause[:1].lower()}{_trim(clause[1:], 17)}."


def casual_from_headline(company_name: str, headline: str) -> str:
    """'Acme AI launches Agents API - TechCrunch' -> 'saw you just launched Agents API'."""
    headline = re.sub(r"\s+[|\-–—]\s+[^|\-–—]{2,40}$", "", headline).strip().rstrip(".")
    rest = re.sub(rf"^{re.escape(company_name)}('s)?\s+", "", headline, flags=re.I)
    for verb, phrase in HEADLINE_VERBS.items():
        if rest.lower().startswith(verb + " "):
            return f"saw you {phrase} {_trim(rest[len(verb) + 1:], 6)}"
    return f"saw the recent {company_name} news"


def compose_outreach(greet_name: str, casual: str, seller_context: str) -> str:
    greeting = f"Hey {greet_name},"
    opener = f"{greeting} {casual.strip().rstrip('.')}."
    value = _value_sentence(seller_context)
    question = "Are you handling that in-house, or open to a quick look?"
    text = f"{opener} {value} {question}"
    if word_count(text) > TARGET_MAX_WORDS:
        question = "Open to a quick look?"
        text = f"{opener} {value} {question}"
    if word_count(text) > TARGET_MAX_WORDS:
        opener = f"{greeting} {_trim(casual, max(4, len(casual.split()) - (word_count(text) - TARGET_MAX_WORDS)))}."
        text = f"{opener} {value} {question}"
    return sanitize(text, greet_name)
