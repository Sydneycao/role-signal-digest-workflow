from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import Post, ScoredPost
from .quality import has_affirmative_hiring_intent

CONFIG_PATH = Path("config/feedback_learning.json")

DEFAULT_CONFIG: dict[str, Any] = {
    "allowed_locations": ["US", "Remote US", "New York", "San Francisco"],
    "blocked_locations": [],
    "blocked_seniority_keywords": [],
    "max_years_experience": 6,
    "require_hiring_signal": True,
    "positive_title_boost_keywords": [],
    "positive_domain_boost_keywords": [],
    "positive_workflow_boost_keywords": [],
    "positive_agent_boost_keywords": [],
    "positive_location_boost_terms": [],
    "acceptable_seniority_keywords": [],
}


def load_feedback_config(runtime_config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        config.update(json.loads(CONFIG_PATH.read_text()))
    if runtime_config:
        config.update({k: v for k, v in runtime_config.items() if v is not None})
    return config


def _text(post: Post) -> str:
    return f"{post.author_headline}\n{post.text}".lower()


def _matches_word(term: str, text: str) -> bool:
    return re.search(r"\b" + re.escape(term.lower()) + r"\b", text) is not None


def hard_filter_reasons(post: Post, config: dict[str, Any]) -> list[str]:
    cfg = load_feedback_config(config)
    text = _text(post)
    reasons: list[str] = []

    if cfg.get("require_hiring_signal", True) and not has_affirmative_hiring_intent(post.text):
        reasons.append("Missing hiring signal")

    for term in cfg.get("blocked_locations", []):
        if term and term.lower() in text:
            reasons.append(f"Blocked location: {term}")
            break

    for term in cfg.get("blocked_seniority_keywords", []):
        term_l = str(term).lower()
        if not term_l:
            continue
        if "years" in term_l:
            pattern = re.escape(term_l).replace(r"\+", r"\+?").replace(r"\ ", r"\s*")
            matched = re.search(pattern, text) is not None
        else:
            matched = _matches_word(term_l, text)
        if matched:
            reasons.append(f"Blocked seniority keyword: {term}")
            break

    max_years = cfg.get("max_years_experience")
    if max_years is not None:
        for match in re.finditer(r"(\d+)\s*\+?\s*years?", text):
            if int(match.group(1)) > int(max_years):
                reasons.append(f"Requires more than {max_years} years")
                break

    return reasons


def passes_feedback_hard_filters(post: Post, config: dict[str, Any]) -> bool:
    return not hard_filter_reasons(post, config)


def positive_boost(post: Post, config: dict[str, Any]) -> int:
    cfg = load_feedback_config(config)
    text = _text(post)

    def hits(key: str) -> int:
        return sum(1 for term in cfg.get(key, []) if term and term.lower() in text)

    boost = 0
    boost += min(1, hits("positive_title_boost_keywords"))
    boost += min(1, hits("positive_domain_boost_keywords"))
    boost += min(1, hits("positive_workflow_boost_keywords"))
    boost += min(1, hits("positive_agent_boost_keywords"))
    boost += min(1, hits("positive_location_boost_terms"))
    boost += min(1, hits("acceptable_seniority_keywords"))
    return min(2, boost)


def apply_feedback_boost(scored: ScoredPost, config: dict[str, Any]) -> ScoredPost:
    if hard_filter_reasons(scored.post, config):
        return scored
    boost = positive_boost(scored.post, config)
    if not boost:
        return scored
    return scored.model_copy(
        update={
            "score": min(10, scored.score + boost),
            "reason": f"{scored.reason} Feedback boost: +{boost}.",
        }
    )
