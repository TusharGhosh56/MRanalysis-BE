from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.git.github_api import parse_repository_from_github_api
from app.models.commit import Commit
from app.models.enums import RepositoryStatus
from app.models.file_change import FileChange
from app.models.repository import Repository
from app.models.user import User


def test_parse_repository_from_github_api(db_session):
    user = User(email="ghapi@example.com", password_hash="hash")
    db_session.add(user)
    db_session.flush()

    repo = Repository(
        id=uuid4(),
        user_id=user.id,
        owner="testowner",
        name="testrepo",
        url="https://github.com/testowner/testrepo",
        clone_path="./data/repos/testowner/testrepo",
        status=RepositoryStatus.PARSING,
    )
    db_session.add(repo)
    db_session.commit()

    mock_commits_list = [
        {
            "sha": "1234567890abcdef1234567890abcdef12345678",
            "commit": {
                "author": {"name": "Dev", "email": "dev@example.com", "date": "2026-09-01T12:00:00Z"},
                "message": "feat: initial commit",
            },
            "parents": [],
        }
    ]

    mock_commit_detail = {
        "sha": "1234567890abcdef1234567890abcdef12345678",
        "commit": {
            "author": {"name": "Dev", "email": "dev@example.com", "date": "2026-09-01T12:00:00Z"},
            "message": "feat: initial commit",
        },
        "parents": [],
        "files": [
            {"filename": "main.py", "status": "added", "additions": 10, "deletions": 0}
        ],
    }

    def mock_get(url, *args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        if "commits?" in url:
            mock_resp.json.return_value = mock_commits_list
        else:
            mock_resp.json.return_value = mock_commit_detail
        return mock_resp

    with patch("httpx.Client.get", side_effect=mock_get):
        count = parse_repository_from_github_api(db_session, repo.id, "testowner", "testrepo")
        assert count == 1

        commits = db_session.query(Commit).filter(Commit.repository_id == repo.id).all()
        assert len(commits) == 1
        assert commits[0].hash == "1234567890abcdef1234567890abcdef12345678"
        assert commits[0].author_name == "Dev"

        files = db_session.query(FileChange).filter(FileChange.commit_id == commits[0].id).all()
        assert len(files) == 1
        assert files[0].file_path == "main.py"
        assert files[0].change_type == "A"
        assert files[0].insertions == 10
