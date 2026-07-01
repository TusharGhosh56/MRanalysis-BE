from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.analysis_job import AnalysisJob
from app.models.analytics_snapshot import AnalyticsSnapshot
from app.models.enums import RepositoryStatus
from app.models.repository import Repository


@pytest.fixture
def auth_headers(client, db_session):
    from app.models.user import User

    client.post(
        "/api/v1/auth/register",
        json={"email": "jobs@example.com", "password": "securepass1"},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "jobs@example.com", "password": "securepass1"},
    )
    token = login.json()["access_token"]
    user = db_session.scalar(select(User).where(User.email == "jobs@example.com"))
    return {"Authorization": f"Bearer {token}"}, user


@patch("app.api.v1.repositories.enqueue_analysis")
def test_job_poll_pending(mock_enqueue, client, auth_headers):
    headers, _ = auth_headers
    create = client.post(
        "/api/v1/repositories",
        json={"url": "https://github.com/octocat/Hello-World"},
        headers=headers,
    )
    job_id = create.json()["job_id"]

    poll = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    assert poll.status_code == 200
    body = poll.json()
    assert body["status"] == "pending"
    assert body["result"] is None
    assert body["job_id"] == job_id


@patch("app.api.v1.repositories.enqueue_analysis")
def test_job_poll_completed_with_metrics(mock_enqueue, client, auth_headers, db_session):
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
    db_session.flush()
    job = AnalysisJob(
        id=uuid4(),
        repository_id=repo.id,
        stage="completed",
        progress_pct=100,
    )
    db_session.add(job)
    db_session.add(
        AnalyticsSnapshot(
            repository_id=repo.id,
            metric_key="summary",
            payload={
                "total_commits": 10,
                "total_contributors": 2,
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
            payload=[{"week": "2024-W01", "count": 10}],
            computed_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    poll = client.get(f"/api/v1/jobs/{job.id}", headers=headers)
    assert poll.status_code == 200
    body = poll.json()
    assert body["status"] == "completed"
    assert body["progress_pct"] == 100
    assert body["result"] is not None
    assert body["result"]["metrics"]["summary"]["total_commits"] == 10
    assert "commits_per_week" in body["result"]["metrics"]


def test_job_poll_not_found(client, auth_headers):
    headers, _ = auth_headers
    response = client.get(f"/api/v1/jobs/{uuid4()}", headers=headers)
    assert response.status_code == 404


def test_job_poll_requires_auth(client):
    response = client.get(f"/api/v1/jobs/{uuid4()}")
    assert response.status_code == 401
