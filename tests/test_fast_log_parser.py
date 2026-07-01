from app.git.fast_log_parser import _infer_change_type, _parse_numstat_line


def test_infer_change_type():
    assert _infer_change_type(10, 0) == "A"
    assert _infer_change_type(0, 5) == "D"
    assert _infer_change_type(3, 2) == "M"


def test_parse_numstat_line():
    assert _parse_numstat_line("10\t5\tsrc/main.py") == (10, 5, "src/main.py")
    assert _parse_numstat_line("-\t-\tbinary.png") == (0, 0, "binary.png")
    assert _parse_numstat_line("bad line") is None


SAMPLE_LOG = """@@@\nabc123def4567890123456789012345678901234\nAlice\nalice@example.com\n1704067200\nfeat: init\n\n10\t0\tREADME.md\n5\t2\tsrc/main.py\n@@@\ndef4567890123456789012345678901234567890\nBob\nbob@example.com\n1704153600\nfix: bug\nparent1 parent2\n1\t1\tREADME.md\n"""


def test_fast_log_parser_parses_git_output(db_session):
    from unittest.mock import patch
    from uuid import uuid4

    from app.git.fast_log_parser import FastGitLogParser
    from app.models.enums import RepositoryStatus
    from app.models.repository import Repository
    from app.models.user import User

    user = User(email="fast@example.com", password_hash="hash")
    db_session.add(user)
    db_session.flush()

    repo = Repository(
        id=uuid4(),
        user_id=user.id,
        owner="demo",
        name="repo",
        url="https://github.com/demo/repo",
        clone_path="./data/repos/demo/repo",
        status=RepositoryStatus.PARSING,
    )
    db_session.add(repo)
    db_session.commit()

    parser = FastGitLogParser(db_session, repo.id, batch_size=10)

    with patch.object(parser, "_count_commits", return_value=2), patch(
        "app.git.fast_log_parser.subprocess.run"
    ) as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = SAMPLE_LOG
        total = parser.parse("./data/repos/demo/repo")

    assert total == 2

    from sqlalchemy import select

    from app.models.commit import Commit
    from app.models.file_change import FileChange

    commits = db_session.scalars(select(Commit).where(Commit.repository_id == repo.id)).all()
    assert len(commits) == 2
    assert commits[0].author_name == "Alice"
    assert commits[1].parent_hashes == ["parent1", "parent2"]

    files = db_session.scalars(
        select(FileChange).join(Commit).where(Commit.repository_id == repo.id)
    ).all()
    assert len(files) == 3
    assert any(file.file_path == "src/main.py" and file.insertions == 5 for file in files)
