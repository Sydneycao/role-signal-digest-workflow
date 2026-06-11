from unittest.mock import patch

import pytest
from postgrest.exceptions import APIError

from src.digest.models import Post
from src.digest.store import (
    MISSING_TABLE_MESSAGE,
    RLS_DENIED_MESSAGE,
    _client,
    _project_url,
    filter_unseen,
    mark_seen,
)


def test_project_url_strips_rest_endpoint():
    assert (
        _project_url("https://example.supabase.co/rest/v1")
        == "https://example.supabase.co"
    )


def test_project_url_strips_copied_table_endpoint():
    assert (
        _project_url("https://example.supabase.co/rest/v1/seen_posts")
        == "https://example.supabase.co"
    )


def test_client_uses_project_root_url(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co/rest/v1")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")

    with patch("src.digest.store.create_client") as create_client:
        _client()

    assert create_client.call_args.args == ("https://example.supabase.co", "test-key")


def test_client_prefers_service_role_key(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")

    with patch("src.digest.store.create_client") as create_client:
        _client()

    assert create_client.call_args.args == ("https://example.supabase.co", "service-role-key")


def test_filter_unseen_reports_missing_table(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    post = Post(
        id="post-1",
        url="https://www.linkedin.com/posts/example",
        text="Hiring for applied AI.",
        author_name="A. Founder",
        author_headline="Founder",
        author_url="https://www.linkedin.com/in/example",
    )
    api_error = APIError(
        {
            "message": "Could not find the table 'public.seen_posts' in the schema cache",
            "code": "PGRST205",
            "hint": None,
            "details": None,
        }
    )

    with patch("src.digest.store.create_client") as create_client:
        query = create_client.return_value.table.return_value.select.return_value
        query.in_.return_value.execute.side_effect = api_error
        with pytest.raises(RuntimeError, match="public.seen_posts") as exc:
            filter_unseen([post])

    assert str(exc.value) == MISSING_TABLE_MESSAGE


def test_mark_seen_reports_rls_denied(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "anon-key")
    post = Post(
        id="post-1",
        url="https://www.linkedin.com/posts/example",
        text="Hiring for applied AI.",
        author_name="A. Founder",
        author_headline="Founder",
        author_url="https://www.linkedin.com/in/example",
    )
    api_error = APIError(
        {
            "message": 'new row violates row-level security policy for table "seen_posts"',
            "code": "42501",
            "hint": None,
            "details": None,
        }
    )

    with patch("src.digest.store.create_client") as create_client:
        create_client.return_value.table.return_value.upsert.return_value.execute.side_effect = (
            api_error
        )
        with pytest.raises(RuntimeError, match="SUPABASE_SERVICE_ROLE_KEY") as exc:
            mark_seen([post])

    assert str(exc.value) == RLS_DENIED_MESSAGE
