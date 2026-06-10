"""
Supabase-backed deduplication store.

Table DDL (run once):
  create table seen_posts (
    post_id  text primary key,
    url      text,
    seen_at  timestamptz default now()
  );
"""

import logging
import os

from supabase import Client, create_client

from .models import Post

log = logging.getLogger(__name__)

TABLE = "seen_posts"


def _client() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    return create_client(url, key)


def filter_unseen(posts: list[Post]) -> list[Post]:
    if not posts:
        return []
    ids = [p.id for p in posts]
    result = _client().table(TABLE).select("post_id").in_("post_id", ids).execute()
    seen = {row["post_id"] for row in result.data}
    fresh = [p for p in posts if p.id not in seen]
    log.info("store: %d/%d posts are new", len(fresh), len(posts))
    return fresh


def mark_seen(posts: list[Post]) -> None:
    if not posts:
        return
    rows = [{"post_id": p.id, "url": p.url} for p in posts]
    _client().table(TABLE).upsert(rows).execute()
    log.info("store: marked %d posts as seen", len(posts))
