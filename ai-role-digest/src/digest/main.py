"""
Entrypoint: fetch → dedupe → score → filter → mark_seen → render → send
Run locally: python -m src.digest.main
"""

import logging
import os
import sys
from collections.abc import Iterable
from datetime import date

from dotenv import load_dotenv

from .emailer import send
from .fetch import build_query_performance_rows, fetch_posts_result
from .outreach import draft_reach_out
from .render import render
from .score import score_and_filter
from .store import filter_unseen, load_query_performance, mark_seen, upsert_query_performance

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stderr,
)
log = logging.getLogger(__name__)

SEND_ON_EMPTY = os.environ.get("SEND_ON_EMPTY", "false").lower() == "true"
REQUIRED_ENV_VARS = (
    "APIFY_TOKEN",
    "ANTHROPIC_API_KEY",
    "SUPABASE_URL",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASS",
    "EMAIL_TO",
)
SUPABASE_KEY_ENV_VARS = ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_KEY")


def _load_query_performance_or_empty() -> dict[str, dict]:
    try:
        return load_query_performance()
    except Exception as exc:
        log.warning("Could not load Apify query performance; using rotation fallback: %s", exc)
        return {}


def _upsert_query_performance_best_effort(rows: list[dict]) -> None:
    try:
        upsert_query_performance(rows)
    except Exception as exc:
        log.warning("Could not update Apify query performance: %s", exc)


def require_env(names: Iterable[str] = REQUIRED_ENV_VARS) -> None:
    missing = [name for name in names if not os.environ.get(name)]
    if not any(os.environ.get(name) for name in SUPABASE_KEY_ENV_VARS):
        missing.append("SUPABASE_SERVICE_ROLE_KEY (recommended) or SUPABASE_KEY")
    if not missing:
        return

    joined = ", ".join(missing)
    raise SystemExit(
        "Missing required environment variable(s): "
        f"{joined}. Add them as GitHub Actions repository secrets, then re-run the workflow."
    )


def main() -> None:
    load_dotenv()
    require_env()
    apify_token = os.environ["APIFY_TOKEN"]

    log.info("=== AI Role Digest starting ===")

    query_performance = _load_query_performance_or_empty()
    fetch_result = fetch_posts_result(apify_token, performance_rows=query_performance)
    if fetch_result.skipped_quota:
        log.warning("Apify source skipped due to quota/billing; not treating this as no results")
        if SEND_ON_EMPTY:
            send(
                f"AI Role Digest {date.today()} — Apify quota skipped",
                (
                    "<p>Apify quota/billing limit hit. "
                    "No LinkedIn fetch was attempted after the error.</p>"
                ),
            )
        return
    if fetch_result.source_status == "dry_run":
        log.info("APIFY_DRY_RUN=true; exiting before scoring or sending")
        return

    raw = fetch_result.posts
    log.info("stage fetch: %d posts", len(raw))

    fresh = filter_unseen(raw)
    log.info("stage dedupe: %d new posts", len(fresh))

    if not fresh:
        performance_rows = build_query_performance_rows(
            query_performance,
            fetch_result.query_stats,
            {},
        )
        _upsert_query_performance_best_effort(performance_rows)
        log.info("No new posts; skipping scoring")
        if SEND_ON_EMPTY:
            send(f"AI Role Digest {date.today()} — no new posts", "<p>No new posts today.</p>")
        return

    scored = score_and_filter(fresh)
    log.info("stage score: %d posts above threshold", len(scored))
    high_fit_counts: dict[str, int] = {}
    for scored_post in scored:
        query = scored_post.post.query
        if query:
            high_fit_counts[query] = high_fit_counts.get(query, 0) + 1
    performance_rows = build_query_performance_rows(
        query_performance,
        fetch_result.query_stats,
        high_fit_counts,
    )
    _upsert_query_performance_best_effort(performance_rows)

    scored = draft_reach_out(scored)
    log.info("stage outreach: %d posts drafted", len(scored))

    mark_seen(fresh)

    if not scored:
        log.info("No posts above threshold")
        if SEND_ON_EMPTY:
            subj = f"AI Role Digest {date.today()} — nothing matched"
            send(subj, "<p>Nothing matched today.</p>")
        return

    html = render(scored)
    count = len(scored)
    subject = f"AI Role Digest {date.today()} — {count} new role{'s' if count != 1 else ''}"
    send(subject, html)
    log.info("=== Done ===")


if __name__ == "__main__":
    main()
