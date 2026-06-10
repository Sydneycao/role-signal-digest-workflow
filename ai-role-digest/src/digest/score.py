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

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
SCORE_THRESHOLD = int(os.environ.get("SCORE_THRESHOLD", "7"))
MAX_CONCURRENT = 5
RUBRIC_PATH = Path("config/rubric.md")


class _ScoreResult(BaseModel):
    score: int
    role_match: bool
    reason: str
    poster_name: str
    poster_url: str


def _rubric() -> str:
    return RUBRIC_PATH.read_text()


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
    scored = asyncio.run(_score_all(posts))
    kept = [s for s in scored if s.score >= SCORE_THRESHOLD]
    log.info(
        "scoring: %d posts → %d scored → %d above threshold %d",
        len(posts),
        len(scored),
        len(kept),
        SCORE_THRESHOLD,
    )
    return kept
