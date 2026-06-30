"""
Score posts via Claude structured output (messages.parse + Pydantic).
Uses AsyncAnthropic with an asyncio semaphore for concurrency control.
SDK auto-retries rate limits (default 2 retries); we add one more layer.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Optional

import anthropic
from pydantic import BaseModel

from .feedback_learning import apply_feedback_boost, passes_feedback_hard_filters
from .models import Post, ScoredPost

log = logging.getLogger(__name__)

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5")
SCORE_THRESHOLD = int(os.environ.get("SCORE_THRESHOLD", "7"))
MAX_CONCURRENT = 5
RUBRIC_PATH = Path("config/rubric.md")

HIRING_TERMS = (
    "hiring",
    "we're looking",
    "we are looking",
    "looking for",
    "join our",
    "opening",
    "open role",
    "role",
    "position",
    "apply",
)
TARGET_TERMS = (
    "ai enablement",
    "applied ai",
    "ai transformation",
    "ai automation",
    "internal ai",
    "internal tooling",
    "gtm engineer",
    "automation",
    "automations",
    "agent",
    "agents",
    "llm",
    "llms",
    "workflow",
    "founder's office",
)
REJECT_TERMS = (
    "account executive",
    "applied scientist",
    "client success",
    "customer success",
    "director",
    "founder associate",
    "machine learning research",
    "ml research",
    "non-technical strategy",
    "phd",
    "postdoc",
    "principal scientist",
    "research scientist",
    "sales executive",
    "solutions engineer",
    "vice president",
)
NON_US_LOCATION_TERMS = (
    "abu dhabi",
    "canada",
    "europe",
    "india",
    "london",
    "mumbai",
    "texas",
    "uk",
    "united kingdom",
)
TOO_SENIOR_TERMS = (
    "director",
    "principal",
    "staff",
    "vice president",
    "vp",
)
CANDIDATE_JOB_SEARCH_PATTERNS = (
    r"\bi(?:'| a)?m currently seeking\b",
    r"\bi(?:'| a)?m seeking\b",
    r"\bi(?:'| a)?m looking for (?:a|my next|new|an?) .{0,40}\b(role|opportunity|job)\b",
    r"\bopen to work\b",
    r"\bseeking (?:a|my next|new|an?) .{0,40}\b(role|opportunity|job)\b",
)
EXPIRED_POST_TERMS = (
    "applications are closed",
    "applications closed",
    "broken link",
    "no longer accepting",
    "no longer available",
    "no longer exists",
    "position has been filled",
    "role has been filled",
    "role is filled",
)


class _ScoreResult(BaseModel):
    score: int
    role_match: bool
    reason: str
    poster_name: str
    poster_url: str


def _rubric() -> str:
    return RUBRIC_PATH.read_text()


def _matches_word(term: str, text: str) -> bool:
    return re.search(r"\b" + re.escape(term.lower()) + r"\b", text) is not None


def _requires_too_many_years(text: str, max_years: int = 6) -> bool:
    for match in re.finditer(r"(\d+)\s*\+?\s*years?", text):
        if int(match.group(1)) > max_years:
            return True
    return False


def _looks_like_candidate_job_search(post_text: str) -> bool:
    return any(re.search(pattern, post_text) for pattern in CANDIDATE_JOB_SEARCH_PATTERNS)


def _base_hard_reject_reasons(post: Post) -> list[str]:
    post_text = post.text.lower()
    context = f"{post.author_headline}\n{post.text}".lower()
    reasons: list[str] = []

    if _looks_like_candidate_job_search(post_text):
        reasons.append("not_hiring_post")
    if any(term in post_text for term in EXPIRED_POST_TERMS):
        reasons.append("expired_post")
    if any(_matches_word(term, context) for term in NON_US_LOCATION_TERMS):
        reasons.append("wrong_location")
    if (
        any(_matches_word(term, post_text) for term in TOO_SENIOR_TERMS)
        or _requires_too_many_years(post_text)
    ):
        reasons.append("too_senior")
    if any(term in post_text for term in REJECT_TERMS):
        reasons.append("not_relevant_domain")
    return reasons


def _post_key(post: Post) -> str:
    return post.id or post.url


def _prefilter_posts(
    posts: list[Post],
    feedback_config: dict | None = None,
) -> list[Post]:
    kept: list[Post] = []
    feedback_config = feedback_config or {}
    seen_keys: set[str] = set()
    for post in posts:
        post_text = post.text.lower()
        context = f"{post.author_headline}\n{post.text}".lower()
        has_hiring_signal = any(term in post_text for term in HIRING_TERMS)
        has_target_signal = any(term in context for term in TARGET_TERMS)
        key = _post_key(post)
        reject_reasons = []
        if key in seen_keys:
            reject_reasons.append("duplicate")
        else:
            seen_keys.add(key)
        reject_reasons.extend(_base_hard_reject_reasons(post))
        if not has_hiring_signal:
            reject_reasons.append("not_hiring_post")
        if not has_target_signal:
            reject_reasons.append("not_relevant_domain")
        if not passes_feedback_hard_filters(post, feedback_config):
            reject_reasons.append("feedback_rule")

        if not reject_reasons:
            kept.append(post)

    log.info("prefilter: %d posts -> %d plausible posts", len(posts), len(kept))
    return kept


async def _score_one(
    client: anthropic.AsyncAnthropic, sem: asyncio.Semaphore, post: Post, system: str,
) -> Optional[ScoredPost]:
    user_msg = (
        f"Author: {post.author_name}\n"
        f"Headline: {post.author_headline}\n"
        f"Profile: {post.author_url}\n\n"
        f"{post.text}"
    )
    async with sem:
        for attempt in range(3):
            try:
                resp = await client.messages.parse(
                    model=CLAUDE_MODEL,
                    max_tokens=512,
                    system=system,
                    messages=[{"role": "user", "content": user_msg}],
                    output_format=_ScoreResult,
                )
                r: _ScoreResult = resp.parsed_output  # type: ignore[assignment]
                if r is None:
                    log.warning("parse returned None for post %s", post.id)
                    return None
                return ScoredPost(
                    post=post,
                    score=r.score,
                    role_match=r.role_match,
                    reason=r.reason,
                    poster_name=r.poster_name or post.author_name,
                    poster_url=r.poster_url or post.author_url,
                )
            except anthropic.RateLimitError:
                wait = 2 ** (attempt + 2)
                log.warning("Rate limited, waiting %ds (attempt %d)", wait, attempt + 1)
                await asyncio.sleep(wait)
            except Exception as exc:
                log.error("Scoring error for post %s: %s", post.id, exc)
                return None
    return None


async def _score_all(posts: list[Post]) -> list[ScoredPost]:
    system = _rubric()
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    async with anthropic.AsyncAnthropic() as client:
        tasks = [_score_one(client, sem, p, system) for p in posts]
        results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


def score_and_filter(posts: list[Post], feedback_config: dict | None = None) -> list[ScoredPost]:
    feedback_config = feedback_config or {}
    candidates = _prefilter_posts(posts, feedback_config=feedback_config)
    scored = asyncio.run(_score_all(candidates))
    scored = [apply_feedback_boost(s, feedback_config) for s in scored]
    kept = [s for s in scored if s.score >= SCORE_THRESHOLD]
    log.info(
        "scoring: %d posts → %d candidates → %d scored → %d above threshold %d",
        len(posts),
        len(candidates),
        len(scored),
        len(kept),
        SCORE_THRESHOLD,
    )
    return kept
