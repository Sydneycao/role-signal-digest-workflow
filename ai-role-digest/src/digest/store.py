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
from urllib.parse import urlsplit, urlunsplit

from postgrest.exceptions import APIError

from supabase import Client, create_client

from .models import Post

log = logging.getLogger(__name__)

TABLE = "seen_posts"
MISSING_TABLE_MESSAGE = (
    "Supabase table public.seen_posts does not exist. "
    "Create it in Supabase SQL Editor with: "
    "create table if not exists public.seen_posts "
    "(post_id text primary key, url text, seen_at timestamptz default now());"
)
RLS_DENIED_MESSAGE = (
    "Supabase denied access to public.seen_posts. "
    "Set the GitHub Actions secret SUPABASE_SERVICE_ROLE_KEY to your Supabase service_role "
    "key, or add Row Level Security policies that allow this workflow to read and upsert "
    "seen_posts."
)


def _project_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    path = parsed.path.rstrip("/")
    rest_index = path.find("/rest/v1")
    if rest_index != -1:
        path = path[:rest_index]
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")


def _client() -> Client:
    url = _project_url(os.environ["SUPABASE_URL"])
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_KEY"]
    return create_client(url, key)


def _raise_clear_store_error(exc: APIError) -> None:
    if exc.code == "PGRST205":
        raise RuntimeError(MISSING_TABLE_MESSAGE) from exc
    if exc.code == "42501":
        raise RuntimeError(RLS_DENIED_MESSAGE) from exc
    raise exc


def filter_unseen(posts: list[Post]) -> list[Post]:
    if not posts:
        return []
    ids = [p.id for p in posts]
    try:
        result = _client().table(TABLE).select("post_id").in_("post_id", ids).execute()
    except APIError as exc:
        _raise_clear_store_error(exc)
    seen = {row["post_id"] for row in result.data}
    fresh = [p for p in posts if p.id not in seen]
    log.info("store: %d/%d posts are new", len(fresh), len(posts))
    return fresh


def mark_seen(posts: list[Post]) -> None:
    if not posts:
        return
    rows = [{"post_id": p.id, "url": p.url} for p in posts]
    try:
        _client().table(TABLE).upsert(rows).execute()
    except APIError as exc:
        _raise_clear_store_error(exc)
    log.info("store: marked %d posts as seen", len(posts))
