"""
Tests for score.py.
Mocks the Anthropic client so no real API calls are made.
Asserts threshold filtering and that parsed_output maps correctly to ScoredPost.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.digest.main import require_env
from src.digest.models import Post
from src.digest.score import (
    CLAUDE_MODEL,
    _prefilter_posts,
    _ScoreResult,
    score_and_filter,
)

FIXTURES = Path(__file__).parent / "fixtures" / "sample_posts.json"


def _load_posts() -> list[Post]:
    data = json.loads(FIXTURES.read_text())
    return [Post(**p) for p in data]


def _mock_response(score: int, name: str, url: str) -> MagicMock:
    resp = MagicMock()
    resp.parsed_output = _ScoreResult(
        score=score,
        role_match=score >= 7,
        reason=f"Score {score} reason",
        poster_name=name,
        poster_url=url,
    )
    return resp


def test_score_and_filter_keeps_high_scores():
    posts = _load_posts()

    responses = [
        _mock_response(9, "Alice Founder", "https://www.linkedin.com/in/alice-founder"),
        _mock_response(8, "Carol Ops", "https://www.linkedin.com/in/carol-ops"),
    ]

    mock_client = AsyncMock()
    mock_client.messages.parse = AsyncMock(side_effect=responses)

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("src.digest.score.anthropic.AsyncAnthropic", return_value=mock_ctx),
        patch("src.digest.score._rubric", return_value="You are a job scorer."),
    ):
        result = score_and_filter(posts, mode="anthropic")

    assert len(result) == 2
    assert all(s.score >= 7 for s in result)
    scores = {s.post.id for s in result}
    assert "post_abc123" in scores
    assert "post_ghi789" in scores
    assert "post_def456" not in scores
    assert mock_client.messages.parse.await_count == 2


def test_score_and_filter_empty_input():
    result = score_and_filter([])
    assert result == []


def test_default_rule_scoring_needs_no_anthropic_call():
    posts = [
        Post(
            id="rules",
            url="https://www.linkedin.com/posts/rules",
            text=(
                "We are hiring an Applied AI Engineer to build internal agents "
                "and workflow automation for our New York team."
            ),
            author_name="Founder",
            author_headline="Founder",
            author_url="https://www.linkedin.com/in/founder",
        )
    ]

    with patch("src.digest.score.anthropic.AsyncAnthropic") as client:
        result = score_and_filter(posts)

    assert len(result) == 1
    assert result[0].score >= 7
    assert "Rule-based match" in result[0].reason
    client.assert_not_called()


def test_prefilter_rejects_obvious_sales_role():
    posts = [
        Post(
            id="sales",
            url="https://www.linkedin.com/posts/sales",
            text="We are hiring an account executive to sell our AI automation platform.",
            author_name="Sales Recruiter",
            author_headline="Recruiter",
            author_url="https://www.linkedin.com/in/sales",
        ),
        Post(
            id="applied-ai",
            url="https://www.linkedin.com/posts/applied-ai",
            text="We are hiring an applied AI engineer to build internal automations.",
            author_name="Founder",
            author_headline="Founder",
            author_url="https://www.linkedin.com/in/founder",
        ),
    ]

    kept = _prefilter_posts(posts)

    assert [post.id for post in kept] == ["applied-ai"]


def test_prefilter_rejects_candidate_job_search_post():
    posts = [
        Post(
            id="candidate",
            url="https://www.linkedin.com/posts/candidate",
            text="I'm currently seeking a Senior AI/ML Engineer opportunity with LLM agents.",
            author_name="Candidate",
            author_headline="AI Engineer | Open to work",
            author_url="https://www.linkedin.com/in/candidate",
        )
    ]

    assert _prefilter_posts(posts) == []


def test_prefilter_rejects_wrong_location_post():
    posts = [
        Post(
            id="texas",
            url="https://www.linkedin.com/posts/texas",
            text="We are hiring an Applied AI Engineer in Texas to build internal agents.",
            author_name="Founder",
            author_headline="Founder",
            author_url="https://www.linkedin.com/in/founder",
        )
    ]

    assert _prefilter_posts(posts) == []


def test_prefilter_rejects_too_senior_post():
    posts = [
        Post(
            id="principal",
            url="https://www.linkedin.com/posts/principal",
            text="We are hiring a Principal AI Agent Engineer with 8+ years of experience.",
            author_name="Recruiter",
            author_headline="Recruiter",
            author_url="https://www.linkedin.com/in/recruiter",
        )
    ]

    assert _prefilter_posts(posts) == []


def test_prefilter_rejects_expired_post():
    posts = [
        Post(
            id="expired",
            url="https://www.linkedin.com/posts/expired",
            text="We were hiring an Applied AI Engineer, but applications are closed.",
            author_name="Founder",
            author_headline="Founder",
            author_url="https://www.linkedin.com/in/founder",
        )
    ]

    assert _prefilter_posts(posts) == []


def test_prefilter_rejects_duplicate_posts_in_batch():
    posts = [
        Post(
            id="dupe",
            url="https://www.linkedin.com/posts/dupe",
            text="We are hiring an Applied AI Engineer to build internal agents.",
            author_name="Founder",
            author_headline="Founder",
            author_url="https://www.linkedin.com/in/founder",
        ),
        Post(
            id="dupe",
            url="https://www.linkedin.com/posts/dupe",
            text="We are hiring an Applied AI Engineer to build internal agents.",
            author_name="Founder",
            author_headline="Founder",
            author_url="https://www.linkedin.com/in/founder",
        ),
    ]

    assert [post.id for post in _prefilter_posts(posts)] == ["dupe"]


def test_default_model_is_haiku():
    assert CLAUDE_MODEL == "claude-haiku-4-5"


def test_score_and_filter_all_below_threshold():
    posts = _load_posts()[:1]
    mock_client = AsyncMock()
    mock_client.messages.parse = AsyncMock(
        return_value=_mock_response(2, "Alice", "https://linkedin.com/in/alice-founder")
    )
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("src.digest.score.anthropic.AsyncAnthropic", return_value=mock_ctx),
        patch("src.digest.score._rubric", return_value="scorer"),
    ):
        result = score_and_filter(posts, mode="anthropic")

    assert result == []


def test_require_env_reports_empty_github_secret(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")

    with pytest.raises(SystemExit) as exc:
        require_env(("APIFY_TOKEN", "ANTHROPIC_API_KEY"))

    message = str(exc.value)
    assert "APIFY_TOKEN" in message
    assert "ANTHROPIC_API_KEY" not in message
    assert "GitHub Actions repository secrets" in message
