"""
Draft LinkedIn reach-out messages for scored roles.

Each draft includes:
- a short title for the opportunity
- a LinkedIn connection request capped at 200 characters
- a longer first-degree DM draft capped well below LinkedIn's 8,000 character limit
"""

from __future__ import annotations

import logging
import os

from .models import OutreachDraft, ScoredPost

log = logging.getLogger(__name__)

OUTREACH_MODE = os.environ.get("OUTREACH_MODE", "template").lower()
CONNECTION_REQUEST_LIMIT = 200
DIRECT_MESSAGE_LIMIT = 8000

DEFAULT_CANDIDATE_BACKGROUND = (
    "I am a candidate with relevant experience for this role. Recently, I have "
    "worked on projects that connect technical execution with practical business "
    "needs, including automation, internal tooling, data workflows, and user-facing "
    "improvements. I am especially interested in roles where I can ship useful "
    "systems end to end and learn quickly from real users."
)


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


def draft_reach_out(
    scored: list[ScoredPost],
    mode: str | None = None,
) -> list[ScoredPost]:
    if not scored:
        return []
    selected_mode = (mode or OUTREACH_MODE).lower()
    if selected_mode == "template":
        drafted = [item.model_copy(update={"outreach": _fallback_draft(item)}) for item in scored]
    else:
        raise ValueError(f"Unknown OUTREACH_MODE: {selected_mode}")
    log.info("outreach mode: %s", selected_mode)
    log.info("outreach: drafted messages for %d posts", len(drafted))
    return drafted
