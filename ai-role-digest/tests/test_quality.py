from src.digest.quality import (
    evaluate_post_quality,
    has_affirmative_hiring_intent,
    target_location_from_text,
)


def test_affirmative_hiring_intent_rejects_non_hiring_context():
    assert not has_affirmative_hiring_intent("AI hiring trends in 2026")
    assert not has_affirmative_hiring_intent("We are no longer hiring for this role")
    assert not has_affirmative_hiring_intent("I got hired after a long search")
    assert not has_affirmative_hiring_intent("I'm looking for my next Applied AI role in New York")


def test_target_location_requires_explicit_target_us_evidence():
    assert target_location_from_text("This role is fully remote") == ""
    assert target_location_from_text("Remote - Europe") == ""
    assert target_location_from_text("Based in Austin, Texas") == ""
    assert target_location_from_text("Remote within the United States") == "Remote US"
    assert target_location_from_text("Join our New York team") == "New York City"
    assert target_location_from_text("Based in the SF Bay Area") == "San Francisco"


def test_quality_gate_requires_hiring_and_location_together():
    assert evaluate_post_quality("We are hiring an Applied AI Engineer. Remote US.").accepted
    assert not evaluate_post_quality("We are hiring an Applied AI Engineer. Fully remote.").accepted
    assert not evaluate_post_quality("Applied AI hiring trends in San Francisco.").accepted
