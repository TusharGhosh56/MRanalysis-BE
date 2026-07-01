from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.analytics_snapshot import AnalyticsSnapshot
from app.models.enums import RepositoryStatus
from app.models.repository import Repository
from app.models.user import User


@pytest.fixture
def auth_headers(client, db_session):
    client.post(
        "/api/v1/auth/register",
        json={"email": "repo@example.com", "password": "securepass1"},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "repo@example.com", "password": "securepass1"},
    )
    token = login.json()["access_token"]
    user = db_session.scalar(select(User).where(User.email == "repo@example.com"))
    return {"Authorization": f"Bearer {token}"}, user


@patch("app.api.v1.repositories.enqueue_analysis")
def test_create_repository(mock_enqueue, client, auth_headers):
    headers, _user = auth_headers
    response = client.post(
        "/api/v1/repositories",
        json={"url": "https://github.com/octocat/Hello-World"},
        headers=headers,
    )
    assert response.status_code == 202
    data = response.json()
    assert data["owner"] == "octocat"
    assert data["name"] == "Hello-World"
    assert data["status"] == "pending"
    assert "job_id" in data
    assert "repository_id" in data
    mock_enqueue.assert_called_once()


@patch("app.api.v1.repositories.enqueue_analysis")
def test_duplicate_repository_reanalyzes(mock_enqueue, client, auth_headers):
    headers, _user = auth_headers
    payload = {"url": "https://github.com/octocat/Spoon-Knife"}
    first = client.post("/api/v1/repositories", json=payload, headers=headers)
    second = client.post("/api/v1/repositories", json=payload, headers=headers)
    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["repository_id"] == first.json()["repository_id"]
    assert second.json()["job_id"] != first.json()["job_id"]
    assert second.json()["status"] == "pending"
    assert mock_enqueue.call_count == 2


def test_create_repository_requires_auth(client):
    response = client.post(
        "/api/v1/repositories",
        json={"url": "https://github.com/octocat/Hello-World"},
    )
    assert response.status_code == 401


def test_invalid_url_returns_422(client, auth_headers):
    headers, _ = auth_headers
    response = client.post(
        "/api/v1/repositories",
        json={"url": "not-a-valid-url"},
        headers=headers,
    )
    assert response.status_code == 422


@patch("app.api.v1.repositories.enqueue_analysis")
def test_list_and_get_repository(mock_enqueue, client, auth_headers, db_session):
    headers, user = auth_headers
    create = client.post(
        "/api/v1/repositories",
        json={"url": "https://github.com/octocat/Hello-World"},
        headers=headers,
    )
    repo_id = create.json()["repository_id"]

    listed = client.get("/api/v1/repositories", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["summary"] is None

    detail = client.get(f"/api/v1/repositories/{repo_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["summary"] is None


@patch("app.api.v1.repositories.enqueue_analysis")
def test_analytics_not_complete(mock_enqueue, client, auth_headers):
    headers, _ = auth_headers
    create = client.post(
        "/api/v1/repositories",
        json={"url": "https://github.com/octocat/Hello-World"},
        headers=headers,
    )
    repo_id = create.json()["repository_id"]

    status_resp = client.get(f"/api/v1/repositories/{repo_id}/status", headers=headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "pending"

    analytics = client.get(f"/api/v1/repositories/{repo_id}/analytics", headers=headers)
    assert analytics.status_code == 409


def test_completed_analytics_flow(client, auth_headers, db_session):
    headers, user = auth_headers
    repo = Repository(
        id=uuid4(),
        user_id=user.id,
        owner="demo",
        name="repo",
        url="https://github.com/demo/repo",
        clone_path="./data/repos/demo/repo",
        status=RepositoryStatus.COMPLETED,
        analyzed_at=datetime.now(UTC),
    )
    db_session.add(repo)
    db_session.add(
        AnalyticsSnapshot(
            repository_id=repo.id,
            metric_key="summary",
            payload={
                "total_commits": 2,
                "total_contributors": 1,
                "first_commit": "2024-01-01T00:00:00+00:00",
                "last_commit": "2024-02-01T00:00:00+00:00",
                "avg_commits_per_day": 0.5,
            },
            computed_at=datetime.now(UTC),
        )
    )
    db_session.add(
        AnalyticsSnapshot(
            repository_id=repo.id,
            metric_key="commits_per_week",
            payload=[{"week": "2024-W01", "count": 2}],
            computed_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    analytics = client.get(f"/api/v1/repositories/{repo.id}/analytics", headers=headers)
    assert analytics.status_code == 200
    body = analytics.json()
    assert body["metrics"]["summary"]["total_commits"] == 2
    assert "commits_per_week" in body["metrics"]

    metric = client.get(
        f"/api/v1/repositories/{repo.id}/analytics/commits_per_week",
        headers=headers,
    )
    assert metric.status_code == 200
    assert metric.json()["metric_key"] == "commits_per_week"

    listed = client.get("/api/v1/repositories", headers=headers)
    assert listed.status_code == 200
    item = next(i for i in listed.json()["items"] if i["id"] == str(repo.id))
    assert item["summary"]["total_commits"] == 2
