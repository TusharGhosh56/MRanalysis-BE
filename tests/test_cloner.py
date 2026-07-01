import os
import stat
from unittest.mock import MagicMock, patch

from app.git.cloner import GitRepositoryCloner, _remove_tree


def test_remove_tree_clears_read_only_files(tmp_path):
    nested = tmp_path / "repo" / ".git" / "objects" / "pack"
    nested.mkdir(parents=True)
    locked = nested / "pack-deadbeef.idx"
    locked.write_text("x", encoding="utf-8")
    os.chmod(locked, stat.S_IREAD)

    _remove_tree(tmp_path / "repo")

    assert not (tmp_path / "repo").exists()


@patch("app.git.cloner.Repo")
def test_clone_syncs_existing_repo_instead_of_deleting(mock_repo_cls, tmp_path):
    target = tmp_path / "owner" / "repo"
    (target / ".git").mkdir(parents=True)

    repo = MagicMock()
    mock_repo_cls.return_value = repo

    cloner = GitRepositoryCloner(base_path=tmp_path)
    result = cloner.clone(
        url="https://github.com/owner/repo",
        owner="owner",
        name="repo",
    )

    assert result == target
    repo.remote.assert_called_once_with("origin")
    repo.remote.return_value.fetch.assert_called_once_with(prune=True)
    repo.remote.return_value.pull.assert_called_once()
    repo.close.assert_called_once()
    mock_repo_cls.clone_from.assert_not_called()
