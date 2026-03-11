"""Tests for webhook payload models."""

from webhook.models import PullRequestEvent


def _pr_payload(action: str = "opened") -> dict:
    return {
        "action": action,
        "pull_request": {
            "number": 42,
            "title": "Add feature X",
            "body": "Description here",
            "state": "open",
            "user": {"login": "alice", "id": 1},
            "head": {"sha": "abc123def456", "ref": "feature/x", "label": "alice:feature/x"},
            "base": {"ref": "main", "label": "owner:main"},
            "html_url": "https://github.com/owner/repo/pull/42",
            "additions": 10,
            "deletions": 2,
            "changed_files": 3,
        },
        "repository": {
            "id": 100,
            "name": "repo",
            "full_name": "owner/repo",
            "private": False,
            "owner": {"login": "owner"},
        },
        "installation": {"id": 999},
    }


class TestPullRequestEvent:
    def test_parses_opened_event(self) -> None:
        event = PullRequestEvent.from_dict(_pr_payload("opened"))
        assert event.action == "opened"
        assert event.pr_number == 42
        assert event.owner == "owner"
        assert event.repo == "repo"
        assert event.head_sha == "abc123def456"

    def test_parses_installation_id(self) -> None:
        event = PullRequestEvent.from_dict(_pr_payload("opened"))
        assert event.installation_id == 999

    def test_should_review_opened(self) -> None:
        assert PullRequestEvent.from_dict(_pr_payload("opened")).should_review

    def test_should_review_synchronize(self) -> None:
        assert PullRequestEvent.from_dict(_pr_payload("synchronize")).should_review

    def test_should_review_reopened(self) -> None:
        assert PullRequestEvent.from_dict(_pr_payload("reopened")).should_review

    def test_should_not_review_closed(self) -> None:
        assert not PullRequestEvent.from_dict(_pr_payload("closed")).should_review

    def test_should_not_review_edited(self) -> None:
        assert not PullRequestEvent.from_dict(_pr_payload("edited")).should_review

    def test_pr_url(self) -> None:
        event = PullRequestEvent.from_dict(_pr_payload())
        assert event.pr_url == "https://github.com/owner/repo/pull/42"

    def test_private_repo(self) -> None:
        payload = _pr_payload()
        payload["repository"]["private"] = True
        event = PullRequestEvent.from_dict(payload)
        assert event.repository.private

    def test_no_installation_id(self) -> None:
        payload = _pr_payload()
        del payload["installation"]
        event = PullRequestEvent.from_dict(payload)
        assert event.installation_id is None
