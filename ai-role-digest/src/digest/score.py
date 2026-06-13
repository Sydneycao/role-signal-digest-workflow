"""
Score posts via Claude structured output (messages.parse + Pydantic).
Uses AsyncAnthropic with an asyncio semaphore for concurrency control.
SDK auto-retries rate limits (default 2 retries); we add one more layer.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

import anthropic
from pydantic import BaseModel

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
    "director",
    "machine learning research",
    "ml research",
    "phd",
    "postdoc",
    "principal scientist",
    "research scientist",
    "sales executive",
    "solutions engineer",
    "vice president",
)


class _ScoreResult(BaseModel):
    score: int
    role_match: bool
    reason: str
    poster_name: str
    poster_url: str


def _rubric() -> str:
    return RUBRIC_PATH.read_text()


def _prefilter_posts(posts: list[Post]) -> list[Post]:
    kept: list[Post] = []
    for post in posts:
        post_text = post.text.lower()
        context = f"{post.author_headline}\n{post.text}".lower()
        has_hiring_signal = any(term in post_text for term in HIRING_TERMS)
        has_target_signal = any(term in context for term in TARGET_TERMS)
        has_reject_signal = any(term in post_text for term in REJECT_TERMS)
        if has_hiring_signal and has_target_signal and not has_reject_signal:
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


def score_and_filter(posts: list[Post]) -> list[ScoredPost]:
    candidates = _prefilter_posts(posts)
    scored = asyncio.run(_score_all(candidates))
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
