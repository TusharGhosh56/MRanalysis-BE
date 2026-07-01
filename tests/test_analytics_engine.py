from datetime import UTC, datetime
from uuid import uuid4

from app.analytics.engine import AnalyticsEngine
from app.models.commit import Commit
from app.models.enums import RepositoryStatus
from app.models.file_change import FileChange
from app.models.repository import Repository
from app.models.user import User


def test_analytics_engine_computes_metrics(db_session):
    user = User(email="analytics@example.com", password_hash="hash")
    db_session.add(user)
    db_session.flush()

    repo = Repository(
        id=uuid4(),
        user_id=user.id,
        owner="demo",
        name="repo",
        url="https://github.com/demo/repo",
        clone_path="./data/repos/demo/repo",
        status=RepositoryStatus.COMPLETED,
    )
    db_session.add(repo)
    db_session.flush()

    t1 = datetime(2024, 1, 1, tzinfo=UTC)
    t2 = datetime(2024, 1, 8, tzinfo=UTC)
    t3 = datetime(2024, 2, 1, tzinfo=UTC)

    c1 = Commit(
        repository_id=repo.id,
        hash="a" * 40,
        author_name="Alice",
        author_email="alice@example.com",
        committed_at=t1,
        message="init",
        parent_hashes=[],
    )
    c2 = Commit(
        repository_id=repo.id,
        hash="b" * 40,
        author_name="Bob",
        author_email="bob@example.com",
        committed_at=t2,
        message="feature",
        parent_hashes=[c1.hash],
    )
    c3 = Commit(
        repository_id=repo.id,
        hash="c" * 40,
        author_name="Alice",
        author_email="alice@example.com",
        committed_at=t3,
        message="fix",
        parent_hashes=[c2.hash],
    )
    db_session.add_all([c1, c2, c3])
    db_session.flush()

    db_session.add_all(
        [
            FileChange(
                commit_id=c1.id,
                file_path="src/main.py",
                change_type="A",
                insertions=10,
                deletions=0,
            ),
            FileChange(
                commit_id=c2.id,
                file_path="src/main.py",
                change_type="M",
                insertions=5,
                deletions=2,
            ),
            FileChange(
                commit_id=c3.id,
                file_path="README.md",
                change_type="M",
                insertions=1,
                deletions=1,
            ),
        ]
    )
    db_session.commit()

    engine = AnalyticsEngine(db_session, repo.id)
    computed_at = engine.run()
    assert computed_at is not None

    from sqlalchemy import select

    from app.models.analytics_snapshot import AnalyticsSnapshot

    snapshots = db_session.scalars(
        select(AnalyticsSnapshot).where(AnalyticsSnapshot.repository_id == repo.id)
    ).all()
    keys = {s.metric_key for s in snapshots}
    assert "summary" in keys
    assert "commits_per_week" in keys
    assert "commits_by_weekday" in keys
    assert "commits_by_hour" in keys
    assert "top_contributors" in keys
    assert "bus_factor" in keys
    assert "commit_message_patterns" in keys
    assert "file_type_breakdown" in keys
    assert "contributor_timeline" in keys
    assert "code_ownership" in keys
    assert "activity_patterns" in keys

    summary = next(s for s in snapshots if s.metric_key == "summary").payload
    assert summary["total_commits"] == 3
    assert summary["total_contributors"] == 2
    assert summary["total_lines_changed"] == 19


def test_analytics_engine_merges_same_email_different_names(db_session):
    user = User(email="dup@example.com", password_hash="hash")
    db_session.add(user)
    db_session.flush()

    repo = Repository(
        id=uuid4(),
        user_id=user.id,
        owner="demo",
        name="dup-repo",
        url="https://github.com/demo/dup-repo",
        clone_path="./data/repos/demo/dup-repo",
        status=RepositoryStatus.COMPLETED,
    )
    db_session.add(repo)
    db_session.flush()

    t1 = datetime(2024, 1, 1, tzinfo=UTC)
    t2 = datetime(2024, 1, 2, tzinfo=UTC)
    t3 = datetime(2024, 1, 3, tzinfo=UTC)

    db_session.add_all(
        [
            Commit(
                repository_id=repo.id,
                hash="a" * 40,
                author_name="Alice",
                author_email="alice@example.com",
                committed_at=t1,
                message="one",
                parent_hashes=[],
            ),
            Commit(
                repository_id=repo.id,
                hash="b" * 40,
                author_name="alice.dev",
                author_email="alice@example.com",
                committed_at=t2,
                message="two",
                parent_hashes=[],
            ),
            Commit(
                repository_id=repo.id,
                hash="c" * 40,
                author_name="alice.dev",
                author_email="alice@example.com",
                committed_at=t3,
                message="three",
                parent_hashes=[],
            ),
        ]
    )
    db_session.commit()

    engine = AnalyticsEngine(db_session, repo.id)
    engine.run()

    from sqlalchemy import select

    from app.models.contributor_stat import ContributorStat

    stats = db_session.scalars(
        select(ContributorStat).where(ContributorStat.repository_id == repo.id)
    ).all()
    assert len(stats) == 1
    assert stats[0].author_email == "alice@example.com"
    assert stats[0].commit_count == 3
    assert stats[0].author_name == "alice.dev"
