from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.digest.fetch import (
    build_query_performance_rows,
    fetch_posts,
    fetch_posts_result,
    select_queries_for_run,
)


def _mock_client(run: object) -> MagicMock:
    client = MagicMock()
    client.actor.return_value.call.return_value = run
    client.dataset.return_value.iterate_items.return_value = [
        {
            "id": "linkedin-post-1",
            "linkedinUrl": "https://www.linkedin.com/posts/example",
            "content": "We are hiring an applied AI engineer to build internal automations.",
            "author": {
                "name": "A. Founder",
                "info": "Founder",
                "linkedinUrl": "https://www.linkedin.com/in/example",
            },
            "postedAt": {"date": "2026-06-10T12:00:00+00:00"},
        }
    ]
    return client


def test_fetch_posts_reads_dataset_from_apify_v3_run_object(tmp_path):
    config = tmp_path / "queries.yaml"
    config.write_text("defaults: {}\nqueries:\n  - applied AI hiring\n")
    client = _mock_client(SimpleNamespace(default_dataset_id="dataset-v3"))

    with patch("src.digest.fetch.ApifyClient", return_value=client):
        posts = fetch_posts("token", config_path=str(config))

    assert client.dataset.call_args.args == ("dataset-v3",)
    assert len(posts) == 1
    assert posts[0].author_name == "A. Founder"


def test_fetch_posts_still_supports_apify_v2_run_dict(tmp_path):
    config = tmp_path / "queries.yaml"
    config.write_text("defaults: {}\nqueries:\n  - applied AI hiring\n")
    client = _mock_client({"defaultDatasetId": "dataset-v2"})

    with patch("src.digest.fetch.ApifyClient", return_value=client):
        fetch_posts("token", config_path=str(config))

    assert client.dataset.call_args.args == ("dataset-v2",)


def test_fetch_posts_caps_queries_and_total_results(tmp_path, monkeypatch):
    config = tmp_path / "queries.yaml"
    config.write_text(
        "defaults: {}\n"
        "queries:\n"
        "  - q1\n"
        "  - q2\n"
        "  - q3\n"
    )
    items = [
        {
            "id": f"post-{i}",
            "linkedinUrl": f"https://www.linkedin.com/posts/example-{i}",
            "content": "We are hiring an applied AI engineer to build automations.",
            "author": {"name": "A. Founder", "info": "Founder"},
        }
        for i in range(60)
    ]
    client = MagicMock()
    client.actor.return_value.call.return_value = {"defaultDatasetId": "dataset"}
    client.dataset.return_value.iterate_items.return_value = items
    monkeypatch.setenv("APIFY_MAX_RESULTS_PER_QUERY", "25")
    monkeypatch.setenv("APIFY_MAX_QUERIES_PER_RUN", "3")
    monkeypatch.setenv("APIFY_MAX_TOTAL_RESULTS_PER_RUN", "50")
    monkeypatch.setenv("APIFY_MAX_PAID_DATASET_ITEMS", "50")

    with patch("src.digest.fetch.ApifyClient", return_value=client):
        result = fetch_posts_result("token", config_path=str(config), performance_rows={})

    assert client.actor.return_value.call.call_count == 2
    run_inputs = [
        call.kwargs["run_input"]
        for call in client.actor.return_value.call.call_args_list
    ]
    assert [run_input["maxPosts"] for run_input in run_inputs] == [25, 25]
    assert len(result.posts) == 25


def test_dry_run_prints_plan_without_calling_apify(tmp_path, monkeypatch, capsys):
    config = tmp_path / "queries.yaml"
    config.write_text("defaults: {}\nqueries:\n  - q1\n  - q2\n")
    monkeypatch.setenv("APIFY_DRY_RUN", "true")
    monkeypatch.setenv("APIFY_MAX_RESULTS_PER_QUERY", "25")
    monkeypatch.setenv("APIFY_MAX_TOTAL_RESULTS_PER_RUN", "50")

    with patch("src.digest.fetch.ApifyClient") as apify_cls:
        result = fetch_posts_result("token", config_path=str(config), performance_rows={})

    assert result.source_status == "dry_run"
    assert not apify_cls.called
    out = capsys.readouterr().out
    assert "APIFY_DRY_RUN actor_id:" in out
    assert "estimated run max result cost USD: 0.1" in out


def test_quota_error_returns_skipped_quota(tmp_path):
    config = tmp_path / "queries.yaml"
    config.write_text("defaults: {}\nqueries:\n  - q1\n")
    client = MagicMock()
    client.actor.return_value.call.side_effect = RuntimeError("Monthly usage hard limit exceeded")

    with patch("src.digest.fetch.ApifyClient", return_value=client):
        result = fetch_posts_result("token", config_path=str(config), performance_rows={})

    assert result.source_status == "skipped_quota"
    assert result.errors


def test_query_selection_prefers_high_fit_low_duplicate_query():
    performance = {
        "good": {
            "posts_returned": 20,
            "unique_posts": 20,
            "valid_hiring_signals": 12,
            "high_fit_signals": 8,
            "duplicate_rate": 0.0,
        },
        "noisy": {
            "posts_returned": 20,
            "unique_posts": 4,
            "valid_hiring_signals": 2,
            "high_fit_signals": 0,
            "duplicate_rate": 0.8,
        },
    }

    selected = select_queries_for_run(["noisy", "good"], performance, 1)

    assert selected == ["good"]


def test_normalize_redacts_email_and_phone(tmp_path):
    config = tmp_path / "queries.yaml"
    config.write_text("defaults: {}\nqueries:\n  - q1\n")
    client = MagicMock()
    client.actor.return_value.call.return_value = {"defaultDatasetId": "dataset"}
    client.dataset.return_value.iterate_items.return_value = [
        {
            "id": "post-1",
            "linkedinUrl": "https://www.linkedin.com/posts/example",
            "content": "We are hiring. Email me at test@example.com or call 415-555-1212.",
            "author": {"name": "A. Founder", "info": "Founder"},
        }
    ]

    with patch("src.digest.fetch.ApifyClient", return_value=client):
        result = fetch_posts_result("token", config_path=str(config), performance_rows={})

    assert "test@example.com" not in result.posts[0].text
    assert "415-555-1212" not in result.posts[0].text


def test_build_query_performance_rows_accumulates_metrics():
    rows = build_query_performance_rows(
        {
            "q1": {
                "posts_returned": 10,
                "unique_posts": 8,
                "valid_hiring_signals": 4,
                "high_fit_signals": 1,
            }
        },
        {
            "q1": SimpleNamespace(
                query="q1",
                posts_returned=5,
                unique_posts=4,
                valid_hiring_signals=3,
            )
        },
        {"q1": 2},
    )

    assert rows[0]["posts_returned"] == 15
    assert rows[0]["unique_posts"] == 12
    assert rows[0]["valid_hiring_signals"] == 7
    assert rows[0]["high_fit_signals"] == 3
    assert rows[0]["duplicate_rate"] == 0.2
