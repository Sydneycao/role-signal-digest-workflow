"""Fail-closed quality gates for discovered LinkedIn hiring posts."""

from __future__ import annotations

import re
from dataclasses import dataclass

NEGATIVE_HIRING_PATTERNS = (
    r"\bnot hiring\b",
    r"\bno longer hiring\b",
    r"\bstopp(?:ed|ing) hiring\b",
    r"\bhiring freeze\b",
    r"\b(?:we|i|they) (?:were|was) hiring\b",
    r"\bgot hired\b",
    r"\bgetting hired\b",
    r"\bhiring (?:trend|trends|tip|tips|advice|market|process)\b",
    r"\bapplications? (?:are |is )?closed\b",
    r"\bno longer accepting\b",
    r"\b(?:role|position) (?:has been|is) filled\b",
    r"\bi(?:'m| am) (?:currently )?(?:seeking|looking for) .{0,50}"
    r"\b(?:role|opportunity|job)\b",
    r"\bopen to work\b",
    r"\bseeking .{0,50}\b(?:role|opportunity|job)\b",
)

AFFIRMATIVE_HIRING_PATTERNS = (
    r"\bwe(?:'re| are) hiring\b",
    r"\b(?:my|our) team is hiring\b",
    r"\bi(?:'m| am) hiring\b",
    r"\b\w[\w&.' -]{1,50} is hiring\b",
    r"\bhiring (?:a|an|for|multiple|several|our next|their next)\b",
    r"\bjoin (?:my|our|the) team\b",
    r"\bapplications? (?:are |is )?open\b",
    r"\bopen (?:role|roles|position|positions|opening|openings)\b",
    r"\b(?:role|roles|position|positions|opening|openings) (?:is|are) open\b",
    r"\b(?:we(?:'re| are)|i(?:'m| am)) looking for (?:a|an|our next|someone)\b",
    r"\b(?:my|our|the) [\w&' -]{0,40}team is looking for (?:a|an|our next|someone)\b",
)

NON_US_REMOTE_PATTERNS = (
    r"\bremote\s*(?:[-,(]|in|within)?\s*(?:europe|emea|uk|united kingdom|canada|"
    r"india|apac|latam|australia|singapore|worldwide|global|international)\b",
    r"\b(?:europe|emea|uk|united kingdom|canada|india|apac|latam)[ -]?(?:only|remote)\b",
)

TARGET_LOCATION_PATTERNS = (
    (
        r"\bremote\s*(?:[-,(]|in|within)?\s*(?:the\s+)?"
        r"(?:u\.s\.|us|usa|united states)\b",
        "Remote US",
    ),
    (r"\b(?:u\.s\.|us|usa|united states)[ -]?(?:based|only|remote)\b", "Remote US"),
    (
        r"\b(?:anywhere|work) (?:in|within|across) (?:the )?"
        r"(?:u\.s\.|us|united states)\b",
        "Remote US",
    ),
    (r"\b(?:san francisco|sf bay area|bay area)\b", "San Francisco"),
    (r"\b(?:new york city|nyc|new york,?\s+ny|new york)\b", "New York City"),
)


@dataclass(frozen=True)
class PostQuality:
    accepted: bool
    reasons: tuple[str, ...]
    location: str = ""


def _normalized(text: str) -> str:
    return " ".join((text or "").lower().split())


def has_affirmative_hiring_intent(text: str) -> bool:
    """Return true only for a current employer-side hiring statement."""
    normalized = _normalized(text)
    if not normalized:
        return False
    if any(re.search(pattern, normalized) for pattern in NEGATIVE_HIRING_PATTERNS):
        return False
    return any(re.search(pattern, normalized) for pattern in AFFIRMATIVE_HIRING_PATTERNS)


def target_location_from_text(text: str) -> str:
    """Extract a target location only when the post contains explicit evidence."""
    normalized = _normalized(text)
    if any(re.search(pattern, normalized) for pattern in NON_US_REMOTE_PATTERNS):
        return ""
    for pattern, label in TARGET_LOCATION_PATTERNS:
        if re.search(pattern, normalized):
            return label
    return ""


def evaluate_post_quality(text: str) -> PostQuality:
    """Require both affirmative hiring intent and a verifiable target US location."""
    reasons: list[str] = []
    if not has_affirmative_hiring_intent(text):
        reasons.append("not_hiring_post")

    location = target_location_from_text(text)
    if not location:
        reasons.append("wrong_or_unverified_location")

    return PostQuality(not reasons, tuple(reasons), location)
