from src.digest.models import Post, ScoredPost
from src.digest.outreach import (
    CONNECTION_REQUEST_LIMIT,
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


def test_default_outreach_uses_template_without_llm():
    result = draft_reach_out([_scored_post()])

    assert result[0].outreach is not None
    assert "15 minutes" in result[0].outreach.direct_message


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
    monkeypatch.setenv("FEEDBACK_BASE_URL", "https://feedback.example/api")
    monkeypatch.setenv("FEEDBACK_FORM_URL", "https://pages.example/feedback.html")
    scored = _scored_post()
    scored.outreach = _fallback_draft(scored)

    html = render([scored])

    assert "Good" in html
    assert "Add feedback" in html
    assert "action=good" in html
    assert "pages.example/feedback.html" in html
    assert "api_url=https%3A%2F%2Ffeedback.example%2Fapi" in html
    assert "post_id=post_123" in html
