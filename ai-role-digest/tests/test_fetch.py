from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.digest.fetch import fetch_posts


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
