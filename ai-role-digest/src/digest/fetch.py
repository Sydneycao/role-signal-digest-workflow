"""
Fetch LinkedIn posts via Apify harvestapi/linkedin-post-search (cookieless).

Actor input schema (verified 2026-06):
  searchQueries: list[str]   — array of search strings
  postedLimit:   str         — "any"|"1h"|"24h"|"week"|"month"|"3months"|"6months"|"year"
  sortBy:        str         — "date"|"relevance"
  maxPosts:      int         — 0 = unlimited; use to cap per-query cost
  profileScraperMode: str   — "short" (default) | "main"

Output fields used:
  item["id"], item["linkedinUrl"], item["content"],
  item["author"]["name"], item["author"]["info"], item["author"]["linkedinUrl"],
  item["postedAt"]["date"]  (ISO string, may be absent)
"""

from __future__ import annotations

import hashlib
import inspect
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

import yaml
from apify_client import ApifyClient

from .models import Post

log = logging.getLogger(__name__)

ACTOR_ID = "harvestapi/linkedin-post-search"
APIFY_POST_RESULT_COST_USD = 2.0 / 1000.0


@dataclass
class ApifyCostControls:
    max_results_per_query: int = 25
    max_queries_per_run: int = 2
    max_total_results_per_run: int = 50
    max_paid_dataset_items: int = 50
    days_lookback: int = 7
    dry_run: bool = False
    max_results_input_field: str = "maxPosts"

    @classmethod
    def from_env(cls) -> "ApifyCostControls":
        return cls(
            max_results_per_query=_env_int("APIFY_MAX_RESULTS_PER_QUERY", 25),
            max_queries_per_run=_env_int("APIFY_MAX_QUERIES_PER_RUN", 2),
            max_total_results_per_run=_env_int("APIFY_MAX_TOTAL_RESULTS_PER_RUN", 50),
            max_paid_dataset_items=_env_int("APIFY_MAX_PAID_DATASET_ITEMS", 50),
            days_lookback=_env_int("APIFY_DAYS_LOOKBACK", 7),
            dry_run=_env_bool("APIFY_DRY_RUN", False),
            max_results_input_field=os.environ.get("APIFY_MAX_RESULTS_INPUT_FIELD") or "maxPosts",
        )


@dataclass
class QueryPerformance:
    query: str
    posts_returned: int = 0
    unique_posts: int = 0
    valid_hiring_signals: int = 0
    high_fit_signals: int = 0
    duplicate_rate: float = 0.0
    last_run_at: str = ""

    @property
    def high_fit_rate(self) -> float:
        return self.high_fit_signals / self.posts_returned if self.posts_returned else 0.0

    @property
    def hiring_signal_rate(self) -> float:
        return self.valid_hiring_signals / self.posts_returned if self.posts_returned else 0.0


@dataclass
class QueryRunStats:
    query: str
    posts_returned: int = 0
    unique_posts: int = 0
    valid_hiring_signals: int = 0


@dataclass
class FetchResult:
    posts: list[Post] = field(default_factory=list)
    source_status: str = "ok"
    errors: list[str] = field(default_factory=list)
    query_stats: dict[str, QueryRunStats] = field(default_factory=dict)

    @property
    def skipped_quota(self) -> bool:
        return self.source_status == "skipped_quota"


def _load_config(path: str = "config/queries.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _stable_id(item: dict) -> str:
    raw_id = item.get("id") or item.get("linkedinUrl") or str(item)
    return hashlib.sha1(raw_id.encode()).hexdigest()[:16]


def _sanitize_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[redacted-email]", text)
    text = re.sub(
        r"(?<!\w)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}(?!\w)",
        "[redacted-phone]",
        text,
    )
    return text.strip()


def _normalize(item: dict, query: str = "") -> Post | None:
    text = _sanitize_text(item.get("content"))
    if not text:
        return None

    author = item.get("author") or {}
    posted_at_block = item.get("postedAt") or {}
    date_str = posted_at_block.get("date")
    try:
        posted_at = datetime.fromisoformat(date_str) if date_str else None
    except ValueError:
        posted_at = None

    return Post(
        id=_stable_id(item),
        url=item.get("linkedinUrl") or "",
        text=text[:4000],  # keep tokens manageable
        author_name=_sanitize_text(author.get("name")),
        author_headline=_sanitize_text(author.get("info")),
        author_url=author.get("linkedinUrl") or "",
        posted_at=posted_at,
        query=query,
    )


def _default_dataset_id(run: object) -> str:
    if isinstance(run, dict):
        dataset_id = run.get("defaultDatasetId")
    else:
        dataset_id = getattr(run, "default_dataset_id", None) or getattr(
            run, "defaultDatasetId", None
        )

    if not dataset_id:
        raise RuntimeError("Apify run did not include a default dataset ID")
    return dataset_id


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, str(default)).strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


def _posted_limit_for_days(days: int, configured_default: str = "24h") -> str:
    if days <= 1:
        return "24h"
    if days <= 7:
        return "week"
    if days <= 30:
        return "month"
    if days <= 90:
        return "3months"
    if days <= 180:
        return "6months"
    if days <= 365:
        return "year"
    return configured_default or "any"


def _looks_like_hiring_signal(post: Post | None) -> bool:
    if post is None:
        return False
    text = post.text.lower()
    return any(
        term in text
        for term in (
            "hiring",
            "we're looking",
            "we are looking",
            "looking for",
            "join our",
            "open role",
            "opening",
            "apply",
        )
    )


def _performance_from_rows(rows: dict[str, dict] | None) -> dict[str, QueryPerformance]:
    performance: dict[str, QueryPerformance] = {}
    for query, row in (rows or {}).items():
        performance[query] = QueryPerformance(
            query=query,
            posts_returned=int(row.get("posts_returned") or 0),
            unique_posts=int(row.get("unique_posts") or 0),
            valid_hiring_signals=int(row.get("valid_hiring_signals") or 0),
            high_fit_signals=int(row.get("high_fit_signals") or 0),
            duplicate_rate=float(row.get("duplicate_rate") or 0.0),
            last_run_at=str(row.get("last_run_at") or ""),
        )
    return performance


def select_queries_for_run(
    queries: list[str],
    performance_rows: dict[str, dict] | None,
    max_queries: int,
) -> list[str]:
    if not queries:
        return []
    performance = _performance_from_rows(performance_rows)
    if not performance:
        offset = datetime.utcnow().toordinal() % len(queries)
        rotated = queries[offset:] + queries[:offset]
        return rotated[:max_queries]

    def score(query: str) -> tuple[float, int]:
        perf = performance.get(query)
        if perf is None or perf.posts_returned <= 0:
            return (0.2, -queries.index(query))
        value = (
            perf.high_fit_rate * 3.0
            + perf.hiring_signal_rate
            - perf.duplicate_rate * 1.5
        )
        return (value, -queries.index(query))

    return sorted(queries, key=score, reverse=True)[:max_queries]


def _build_run_input(query: str, defaults: dict, controls: ApifyCostControls, limit: int) -> dict:
    posted_limit = os.environ.get(
        "APIFY_POSTED_LIMIT",
        _posted_limit_for_days(controls.days_lookback, defaults.get("postedLimit", "24h")),
    )
    run_input = {
        "searchQueries": [query],
        "postedLimit": posted_limit,
        "sortBy": defaults.get("sortBy", "date"),
        "profileScraperMode": "short",
    }
    run_input[controls.max_results_input_field] = limit
    run_input.setdefault("maxPosts", limit)
    return run_input


def _supported_actor_call_kwargs(call_fn: Any, limit: int) -> dict:
    try:
        params = inspect.signature(call_fn).parameters
    except (TypeError, ValueError):
        return {}

    kwargs = {}
    if "max_items" in params:
        kwargs["max_items"] = limit
    if "max_paid_dataset_items" in params:
        kwargs["max_paid_dataset_items"] = limit
    if "maxPaidDatasetItems" in params:
        kwargs["maxPaidDatasetItems"] = limit
    if "max_total_charge_usd" in params:
        kwargs["max_total_charge_usd"] = Decimal(str(round(limit * APIFY_POST_RESULT_COST_USD, 4)))
    return kwargs


def _is_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "monthly usage hard limit",
            "quota",
            "billing",
            "forbidden",
            "payment required",
            "insufficient",
            "not enough credits",
            "usage limit",
            "402",
            "403",
        )
    )


def _dry_run_result(actor_id: str, plan: list[tuple[str, int, dict]]) -> FetchResult:
    estimated_posts = sum(limit for _, limit, _ in plan)
    estimated_cost = round(estimated_posts * APIFY_POST_RESULT_COST_USD, 4)
    for query, limit, run_input in plan:
        print("APIFY_DRY_RUN actor_id:", actor_id)
        print("APIFY_DRY_RUN query:", query)
        print("APIFY_DRY_RUN run_input:", run_input)
        print("APIFY_DRY_RUN estimated max posts:", limit)
        print(
            "APIFY_DRY_RUN estimated max result cost USD:",
            round(limit * APIFY_POST_RESULT_COST_USD, 4),
        )
    print("APIFY_DRY_RUN estimated run max posts:", estimated_posts)
    print("APIFY_DRY_RUN estimated run max result cost USD:", estimated_cost)
    return FetchResult(source_status="dry_run")


def fetch_posts_result(
    apify_token: str,
    config_path: str = "config/queries.yaml",
    performance_rows: dict[str, dict] | None = None,
) -> FetchResult:
    cfg = _load_config(config_path)
    defaults = cfg.get("defaults", {})
    queries = cfg.get("queries", [])
    controls = ApifyCostControls.from_env()
    actor_id = os.environ.get("APIFY_ACTOR_ID") or ACTOR_ID
    selected_queries = select_queries_for_run(
        queries,
        performance_rows,
        controls.max_queries_per_run,
    )

    remaining = min(controls.max_total_results_per_run, controls.max_paid_dataset_items)
    run_plan: list[tuple[str, int, dict]] = []
    for query in selected_queries:
        if remaining <= 0:
            break
        limit = min(controls.max_results_per_query, remaining)
        run_input = _build_run_input(query, defaults, controls, limit)
        run_plan.append((query, limit, run_input))
        remaining -= limit

    if controls.dry_run:
        return _dry_run_result(actor_id, run_plan)

    client = ApifyClient(apify_token)
    seen_ids: set[str] = set()
    posts: list[Post] = []
    stats: dict[str, QueryRunStats] = {}

    for query, limit, run_input in run_plan:
        query_stats = QueryRunStats(query=query)
        stats[query] = query_stats
        log.info("Apify query: %r", query)
        try:
            actor = client.actor(actor_id)
            call_kwargs = _supported_actor_call_kwargs(actor.call, limit)
            run = actor.call(run_input=run_input, **call_kwargs)
            items = list(client.dataset(_default_dataset_id(run)).iterate_items())[:limit]
        except Exception as exc:
            if _is_quota_error(exc):
                log.warning("Apify quota/billing limit hit; source_status=skipped_quota: %s", exc)
                return FetchResult(
                    posts=posts,
                    source_status="skipped_quota",
                    errors=[str(exc)],
                    query_stats=stats,
                )
            raise

        log.info("  → %d raw items", len(items))

        for item in items:
            query_stats.posts_returned += 1
            post = _normalize(item, query=query)
            if post is None:
                continue
            if post.id in seen_ids:
                continue
            seen_ids.add(post.id)
            query_stats.unique_posts += 1
            if _looks_like_hiring_signal(post):
                query_stats.valid_hiring_signals += 1
            posts.append(post)

    log.info("fetch total: %d unique posts across %d queries", len(posts), len(run_plan))
    return FetchResult(posts=posts, query_stats=stats)


def fetch_posts(apify_token: str, config_path: str = "config/queries.yaml") -> list[Post]:
    result = fetch_posts_result(apify_token, config_path=config_path)
    return result.posts


def build_query_performance_rows(
    existing_rows: dict[str, dict] | None,
    query_stats: dict[str, QueryRunStats],
    high_fit_counts: dict[str, int],
) -> list[dict]:
    rows: list[dict] = []
    existing_rows = existing_rows or {}
    now = datetime.utcnow().isoformat()
    for query, stats in query_stats.items():
        previous = existing_rows.get(query, {})
        posts_returned = int(previous.get("posts_returned") or 0) + stats.posts_returned
        unique_posts = int(previous.get("unique_posts") or 0) + stats.unique_posts
        valid_hiring_signals = (
            int(previous.get("valid_hiring_signals") or 0) + stats.valid_hiring_signals
        )
        high_fit_signals = (
            int(previous.get("high_fit_signals") or 0) + high_fit_counts.get(query, 0)
        )
        duplicate_rate = 0.0
        if posts_returned:
            duplicate_rate = round(max(0, posts_returned - unique_posts) / posts_returned, 4)
        rows.append(
            {
                "query": query,
                "posts_returned": posts_returned,
                "unique_posts": unique_posts,
                "valid_hiring_signals": valid_hiring_signals,
                "high_fit_signals": high_fit_signals,
                "duplicate_rate": duplicate_rate,
                "last_run_at": now,
            }
        )
    return rows
    return posts
