from src.digest.feedback_learning import (
    apply_feedback_boost,
    hard_filter_reasons,
    passes_feedback_hard_filters,
    positive_boost,
)
from src.digest.models import Post, ScoredPost


def _post(text: str, headline: str = "Founder") -> Post:
    return Post(
        id="p1",
        url="https://linkedin.com/posts/p1",
        text=text,
        author_name="A Founder",
        author_headline=headline,
        author_url="https://linkedin.com/in/founder",
    )


def test_hard_filter_blocks_feedback_locations():
    post = _post("We are hiring an AI Agent Engineer in India.")
    config = {"blocked_locations": ["India"]}

    assert not passes_feedback_hard_filters(post, config)
    assert "Blocked location: India" in hard_filter_reasons(post, config)


def test_hard_filter_blocks_principal_even_with_positive_agent_keyword():
    post = _post("We are hiring a Principal AI Agent Engineer for workflow automation.")
    config = {"blocked_seniority_keywords": ["Principal"]}

    assert not passes_feedback_hard_filters(post, config)


def test_positive_boost_for_agentic_workflow_terms():
    post = _post("We are hiring an AI Builder for agentic AI workflow automation.")
    config = {
        "positive_title_boost_keywords": ["AI Builder"],
        "positive_domain_boost_keywords": ["agentic AI"],
        "positive_workflow_boost_keywords": ["workflow automation"],
    }

    assert positive_boost(post, config) == 2


def test_positive_boost_does_not_override_hard_filter():
    post = _post("We are hiring a Principal AI Agent Engineer in India.")
    scored = ScoredPost(
        post=post,
        score=8,
        role_match=True,
        reason="Strong AI Agent fit.",
        poster_name="A Founder",
        poster_url="https://linkedin.com/in/founder",
    )
    config = {
        "blocked_locations": ["India"],
        "blocked_seniority_keywords": ["Principal"],
        "positive_agent_boost_keywords": ["AI Agent"],
    }

    result = apply_feedback_boost(scored, config)

    assert result.score == 8
    assert result.reason == "Strong AI Agent fit."
