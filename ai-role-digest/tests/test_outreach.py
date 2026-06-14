from unittest.mock import AsyncMock, MagicMock, patch

from src.digest.models import Post, ScoredPost
from src.digest.outreach import (
    CONNECTION_REQUEST_LIMIT,
    _DraftResult,
    _fallback_draft,
    draft_reach_out,
)
from src.digest.render import render


def _scored_post() -> ScoredPost:
    return ScoredPost(
        post=Post(
            id="post_123",
            url="https://www.linkedin.com/posts/example",
            text=(
                "We're hiring an Applied AI Engineer to build internal agents, "
                "workflow automation, and GTM tooling."
            ),
            author_name="Alice Founder",
            author_headline="Founder at Decagon",
            author_url="https://www.linkedin.com/in/alice-founder",
        ),
        score=9,
        role_match=True,
        reason="Strong fit for internal applied AI automation.",
        poster_name="Alice Founder",
        poster_url="https://www.linkedin.com/in/alice-founder",
    )


def _mock_response() -> MagicMock:
    resp = MagicMock()
    resp.parsed_output = _DraftResult(
        title="AI Engineer role at Decagon",
        connection_request="Hi Alice, " + ("this role feels aligned " * 20),
        direct_message=(
            "Hi Alice,\n\n"
            "I came across your post on the Applied AI Engineer role and wanted "
            "to reach out directly."
        ),
    )
    return resp


def test_draft_reach_out_maps_structured_output():
    mock_client = AsyncMock()
    mock_client.messages.parse = AsyncMock(return_value=_mock_response())

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("src.digest.outreach.anthropic.AsyncAnthropic", return_value=mock_ctx):
        result = draft_reach_out([_scored_post()])

    assert len(result) == 1
    assert result[0].outreach is not None
    assert result[0].outreach.title == "AI Engineer role at Decagon"
    assert len(result[0].outreach.connection_request) <= CONNECTION_REQUEST_LIMIT
    assert "Applied AI Engineer" in result[0].outreach.direct_message
    assert mock_client.messages.parse.await_count == 1


def test_fallback_connection_request_stays_within_linkedin_limit():
    draft = _fallback_draft(_scored_post())

    assert len(draft.connection_request) <= CONNECTION_REQUEST_LIMIT
    assert "Alice" in draft.connection_request
    assert "15 minutes" in draft.direct_message


def test_render_includes_outreach_blocks():
    scored = _scored_post()
    scored.outreach = _fallback_draft(scored)

    html = render([scored])

    assert "Connection request" in html
    assert "Direct message" in html
    assert "/200 characters" in html
    assert scored.outreach.connection_request in html


def test_render_includes_simple_feedback_links(monkeypatch):
    monkeypatch.setenv("FEEDBACK_BASE_URL", "https://feedback.example/role")
    scored = _scored_post()
    scored.outreach = _fallback_draft(scored)

    html = render([scored])

    assert "Good" in html
    assert "Add feedback" in html
    assert "action=good" in html
    assert "action=add_feedback" in html
    assert "post_id=post_123" in html
