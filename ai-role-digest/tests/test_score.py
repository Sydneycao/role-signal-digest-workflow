"""
Tests for score.py.
Mocks the Gemini client so no real API calls are made.
Asserts threshold filtering and that structured output maps correctly to ScoredPost.
"""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.digest import main as digest_main
from src.digest.main import require_env
from src.digest.models import Post
from src.digest.score import (
    GEMINI_MODEL,
    _prefilter_posts,
    _ScoreResult,
    score_and_filter,
)

FIXTURES = Path(__file__).parent / "fixtures" / "sample_posts.json"


def _load_posts() -> list[Post]:
    data = json.loads(FIXTURES.read_text())
    return [Post(**p) for p in data]


def _mock_response(score: int, role_match: bool | None = None) -> MagicMock:
    resp = MagicMock()
    resp.output_text = _ScoreResult(
        score=score,
        role_match=score >= 7 if role_match is None else role_match,
        reason=f"Score {score} reason",
    ).model_dump_json()
    return resp


def _mock_client(response_or_side_effect):
    async_client = AsyncMock()
    async_client.interactions.create = AsyncMock(side_effect=response_or_side_effect)
    async_context = MagicMock()
    async_context.__aenter__ = AsyncMock(return_value=async_client)
    async_context.__aexit__ = AsyncMock(return_value=False)
    client = MagicMock()
    client.aio = async_context
    return client, async_client


def test_score_and_filter_keeps_high_scores():
    posts = _load_posts()

    responses = [
        _mock_response(9),
        _mock_response(8),
    ]
    client, async_client = _mock_client(responses)

    with (
        patch("src.digest.score.genai.Client", return_value=client),
        patch("src.digest.score._rubric", return_value="You are a job scorer."),
        patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}),
    ):
        result = score_and_filter(posts, mode="gemini")

    assert len(result) == 2
    assert all(s.score >= 7 for s in result)
    scores = {s.post.id for s in result}
    assert "post_abc123" in scores
    assert "post_ghi789" in scores
    assert "post_def456" not in scores
    assert async_client.interactions.create.await_count == 2


def test_score_and_filter_empty_input():
    result = score_and_filter([])
    assert result == []


def test_default_rule_scoring_needs_no_gemini_call():
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

    with patch("src.digest.score.genai.Client") as client:
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
            text=(
                "We are hiring an applied AI engineer to build internal automations "
                "in San Francisco."
            ),
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
            text="We are hiring an Applied AI Engineer to build internal agents. Remote US.",
            author_name="Founder",
            author_headline="Founder",
            author_url="https://www.linkedin.com/in/founder",
        ),
        Post(
            id="dupe",
            url="https://www.linkedin.com/posts/dupe",
            text="We are hiring an Applied AI Engineer to build internal agents. Remote US.",
            author_name="Founder",
            author_headline="Founder",
            author_url="https://www.linkedin.com/in/founder",
        ),
    ]

    assert [post.id for post in _prefilter_posts(posts)] == ["dupe"]


def test_prefilter_rejects_hiring_keyword_without_employer_intent():
    post = Post(
        id="trends",
        url="https://www.linkedin.com/posts/trends",
        text="AI hiring trends and advice for applied AI teams in New York.",
        author_name="Analyst",
        author_headline="Researcher",
        author_url="https://www.linkedin.com/in/analyst",
    )

    assert _prefilter_posts([post]) == []


def test_prefilter_rejects_plain_remote_without_us_evidence():
    post = Post(
        id="remote-unknown",
        url="https://www.linkedin.com/posts/remote-unknown",
        text="We are hiring an Applied AI Engineer to build agents. Fully remote.",
        author_name="Founder",
        author_headline="Founder",
        author_url="https://www.linkedin.com/in/founder",
    )

    assert _prefilter_posts([post]) == []


def test_gemini_mode_without_key_falls_back_to_rules(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    post = Post(
        id="fallback",
        url="https://www.linkedin.com/posts/fallback",
        text=(
            "We are hiring an Applied AI Engineer to build internal agents and "
            "workflow automation. Remote US."
        ),
        author_name="Founder",
        author_headline="Founder",
        author_url="https://www.linkedin.com/in/founder",
    )

    with patch("src.digest.score.genai.Client") as client:
        result = score_and_filter([post], mode="gemini")

    assert len(result) == 1
    assert "Rule-based match" in result[0].reason
    client.assert_not_called()


def test_gemini_api_failure_falls_back_per_post(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    post = Post(
        id="api-fallback",
        url="https://www.linkedin.com/posts/api-fallback",
        text=(
            "We are hiring an Applied AI Engineer to build internal agents and "
            "workflow automation. Remote US."
        ),
        author_name="Founder",
        author_headline="Founder",
        author_url="https://www.linkedin.com/in/founder",
    )
    client, _ = _mock_client(RuntimeError("temporary API error"))

    with patch("src.digest.score.genai.Client", return_value=client):
        result = score_and_filter([post], mode="gemini")

    assert len(result) == 1
    assert "Rule-based match" in result[0].reason


def test_gemini_budget_gate_caps_posts_per_run(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MAX_POSTS_PER_RUN", "3")
    monkeypatch.setenv("GEMINI_MAX_OUTPUT_TOKENS", "128")
    posts = [
        Post(
            id=f"budget-{index}",
            url=f"https://www.linkedin.com/posts/budget-{index}",
            text=(
                "We are hiring an Applied AI Engineer to build internal agents and "
                f"workflow automation. Remote US. Opening {index}."
            ),
            author_name="Founder",
            author_headline="Founder",
            author_url="https://www.linkedin.com/in/founder",
        )
        for index in range(7)
    ]
    client, async_client = _mock_client([_mock_response(8)] * 3)

    with (
        patch("src.digest.score.genai.Client", return_value=client),
        patch("src.digest.score._rubric", return_value="scorer"),
    ):
        result = score_and_filter(posts, mode="gemini")

    assert [item.post.id for item in result] == ["budget-0", "budget-1", "budget-2"]
    assert async_client.interactions.create.await_count == 3
    generation_config = async_client.interactions.create.call_args.kwargs["generation_config"]
    assert generation_config["max_output_tokens"] == 128
    assert generation_config["thinking_level"] == "minimal"
    for call in async_client.interactions.create.call_args_list:
        prompt = call.kwargs["input"]
        assert "https://www.linkedin.com/in/founder" not in prompt
        assert "Author: Founder" not in prompt


def test_default_model_is_gemini_flash_lite():
    assert GEMINI_MODEL == "gemini-3.5-flash-lite"


def test_score_and_filter_all_below_threshold():
    posts = _load_posts()[:1]
    client, _ = _mock_client([_mock_response(2)])

    with (
        patch("src.digest.score.genai.Client", return_value=client),
        patch("src.digest.score._rubric", return_value="scorer"),
        patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}),
    ):
        result = score_and_filter(posts, mode="gemini")

    assert result == []


def test_gemini_role_mismatch_is_rejected_even_with_high_score():
    posts = _load_posts()[:1]
    client, _ = _mock_client([_mock_response(9, role_match=False)])

    with (
        patch("src.digest.score.genai.Client", return_value=client),
        patch("src.digest.score._rubric", return_value="scorer"),
        patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}),
    ):
        result = score_and_filter(posts, mode="gemini")

    assert result == []


def test_require_env_reports_empty_github_secret(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")

    with pytest.raises(SystemExit) as exc:
        require_env(("APIFY_TOKEN", "GEMINI_API_KEY"))

    message = str(exc.value)
    assert "APIFY_TOKEN" in message
    assert "GEMINI_API_KEY" not in message
    assert "GitHub Actions repository secrets" in message


def test_require_env_requires_gemini_key_in_gemini_mode(monkeypatch):
    monkeypatch.setenv("SCORING_MODE", "gemini")
    monkeypatch.setenv("SUPABASE_KEY", "supabase-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(SystemExit) as exc:
        require_env(())

    assert "GEMINI_API_KEY" in str(exc.value)


def test_require_env_allows_rules_mode_without_gemini_key(monkeypatch):
    monkeypatch.setenv("SCORING_MODE", "rules")
    monkeypatch.setenv("SUPABASE_KEY", "supabase-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    require_env(())


def test_email_dry_run_does_not_send(monkeypatch):
    monkeypatch.setattr(digest_main, "EMAIL_DRY_RUN", True)
    with patch("src.digest.main.send") as send:
        digest_main._send_or_log("Test digest", "<p>test</p>")
    send.assert_not_called()
