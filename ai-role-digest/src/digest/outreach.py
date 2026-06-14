"""
Draft LinkedIn reach-out messages for scored roles.

Each draft includes:
- a short title for the opportunity
- a LinkedIn connection request capped at 200 characters
- a longer first-degree DM draft capped well below LinkedIn's 8,000 character limit
"""

from __future__ import annotations

import asyncio
import logging
import os

import anthropic
from pydantic import BaseModel, Field

from .models import OutreachDraft, ScoredPost

log = logging.getLogger(__name__)

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5")
MAX_CONCURRENT = 5
CONNECTION_REQUEST_LIMIT = 200
DIRECT_MESSAGE_LIMIT = 8000

DEFAULT_CANDIDATE_BACKGROUND = (
    "I am currently a Data Scientist at Publicis Health with about two years of "
    "experience. Recently I built an internal multi-agent platform using Copilot "
    "Studio, Power Automate, and Salesforce to automate parts of the BD workflow "
    "for non-technical teams. I have also built n8n pipelines and side projects "
    "around AI daily digests, job search automation, and modernizing the digital "
    "experience for a Chinese art and humanities research organization."
)

SYSTEM_PROMPT = f"""\
You draft concise LinkedIn outreach for a candidate applying to internal applied-AI,
AI enablement, GTM engineering, and workflow automation roles.

Write in a warm, direct, lightly witty voice. Keep the message specific to the role
and the poster's hiring post. Do not overclaim. Preserve placeholders like [name]
when the recipient's first name is unclear.

Create both:
1. connection_request: a LinkedIn connection request, maximum {CONNECTION_REQUEST_LIMIT}
   characters including spaces.
2. direct_message: a first-degree LinkedIn DM, maximum {DIRECT_MESSAGE_LIMIT}
   characters, but aim for 900-1,400 characters.

The direct message should follow this shape:
- Hi [name],
- mention the role or post directly
- connect the candidate's background to relevant role needs
- explain what stood out about the company or role
- ask for a 15 minute chat
- optional light joke about LinkedIn/InMail credits when it feels natural

Return only structured output.
"""


class _DraftResult(BaseModel):
    title: str = Field(description="Short title, e.g. 'AI Engineer role at Decagon'")
    connection_request: str
    direct_message: str


def _candidate_background() -> str:
    return os.environ.get("CANDIDATE_BACKGROUND", DEFAULT_CANDIDATE_BACKGROUND)


def _truncate(text: str, limit: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    suffix = "..."
    if limit <= len(suffix):
        return normalized[:limit]
    return normalized[: limit - len(suffix)].rstrip() + suffix


def _fallback_draft(scored: ScoredPost) -> OutreachDraft:
    role_hint = scored.reason.split(".")[0].strip() or "your AI role"
    name = scored.poster_name.split()[0] if scored.poster_name else "[name]"
    title = f"AI role via {scored.poster_name or 'LinkedIn'}"
    connection = _truncate(
        f"Hi {name}, I saw your post on {role_hint}. My recent work spans internal "
        "AI agents, automation, and BD workflows, and the role looked unusually aligned.",
        CONNECTION_REQUEST_LIMIT,
    )
    direct = (
        f"Hi {name},\n\n"
        "I came across your post and wanted to reach out directly because the role "
        "lines up unusually well with the kind of work I have been building recently.\n\n"
        f"{_candidate_background()}\n\n"
        "What stood out to me is that the role seems focused on shipping useful AI "
        "systems end-to-end, especially around internal workflows and automation. "
        "That is exactly the direction I want to keep growing in.\n\n"
        "Would love to chat for 15 minutes if you are open to it. And if not, "
        "please at least let me know whether this LinkedIn message strategy works, "
        "because I am definitely spending my credits responsibly here."
    )
    return OutreachDraft(
        title=_truncate(title, 120),
        connection_request=connection,
        direct_message=direct[:DIRECT_MESSAGE_LIMIT],
    )


async def _draft_one(
    client: anthropic.AsyncAnthropic,
    sem: asyncio.Semaphore,
    scored: ScoredPost,
    candidate_background: str,
) -> ScoredPost:
    post = scored.post
    user_msg = (
        f"Candidate background:\n{candidate_background}\n\n"
        f"Fit reason:\n{scored.reason}\n\n"
        f"Poster name: {scored.poster_name or post.author_name}\n"
        f"Poster headline: {post.author_headline}\n"
        f"Poster profile: {scored.poster_url or post.author_url}\n"
        f"Post URL: {post.url}\n\n"
        f"Hiring post text:\n{post.text}"
    )
    async with sem:
        for attempt in range(3):
            try:
                resp = await client.messages.parse(
                    model=CLAUDE_MODEL,
                    max_tokens=1400,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_msg}],
                    output_format=_DraftResult,
                )
                draft: _DraftResult | None = resp.parsed_output  # type: ignore[assignment]
                if draft is None:
                    log.warning("outreach parse returned None for post %s", post.id)
                    return scored.model_copy(update={"outreach": _fallback_draft(scored)})

                outreach = OutreachDraft(
                    title=_truncate(draft.title, 120),
                    connection_request=_truncate(
                        draft.connection_request, CONNECTION_REQUEST_LIMIT
                    ),
                    direct_message=draft.direct_message[:DIRECT_MESSAGE_LIMIT],
                )
                return scored.model_copy(update={"outreach": outreach})
            except anthropic.RateLimitError:
                wait = 2 ** (attempt + 2)
                log.warning("Rate limited while drafting, waiting %ds", wait)
                await asyncio.sleep(wait)
            except Exception as exc:
                log.error("Outreach drafting error for post %s: %s", post.id, exc)
                return scored.model_copy(update={"outreach": _fallback_draft(scored)})

    return scored.model_copy(update={"outreach": _fallback_draft(scored)})


async def _draft_all(scored: list[ScoredPost]) -> list[ScoredPost]:
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    candidate_background = _candidate_background()
    async with anthropic.AsyncAnthropic() as client:
        tasks = [_draft_one(client, sem, item, candidate_background) for item in scored]
        return await asyncio.gather(*tasks)


def draft_reach_out(scored: list[ScoredPost]) -> list[ScoredPost]:
    if not scored:
        return []
    drafted = asyncio.run(_draft_all(scored))
    log.info("outreach: drafted messages for %d posts", len(drafted))
    return drafted
