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

import hashlib
import logging
from datetime import datetime

import yaml
from apify_client import ApifyClient

from .models import Post

log = logging.getLogger(__name__)

ACTOR_ID = "harvestapi/linkedin-post-search"
MAX_POSTS_PER_QUERY = 50  # ~$0.075 per query at $1.50/1k


def _load_config(path: str = "config/queries.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _stable_id(item: dict) -> str:
    raw_id = item.get("id") or item.get("linkedinUrl") or str(item)
    return hashlib.sha1(raw_id.encode()).hexdigest()[:16]


def _normalize(item: dict) -> Post | None:
    text = (item.get("content") or "").strip()
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
        author_name=author.get("name") or "",
        author_headline=author.get("info") or "",
        author_url=author.get("linkedinUrl") or "",
        posted_at=posted_at,
    )


def fetch_posts(apify_token: str, config_path: str = "config/queries.yaml") -> list[Post]:
    cfg = _load_config(config_path)
    defaults = cfg.get("defaults", {})
    queries = cfg.get("queries", [])

    client = ApifyClient(apify_token)
    seen_ids: set[str] = set()
    posts: list[Post] = []

    for query in queries:
        run_input = {
            "searchQueries": [query],
            "postedLimit": defaults.get("postedLimit", "24h"),
            "sortBy": defaults.get("sortBy", "date"),
            "maxPosts": MAX_POSTS_PER_QUERY,
            "profileScraperMode": "short",
        }
        log.info("Apify query: %r", query)
        run = client.actor(ACTOR_ID).call(run_input=run_input)
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        log.info("  → %d raw items", len(items))

        for item in items:
            post = _normalize(item)
            if post is None or post.id in seen_ids:
                continue
            seen_ids.add(post.id)
            posts.append(post)

    log.info("fetch total: %d unique posts across %d queries", len(posts), len(queries))
    return posts
