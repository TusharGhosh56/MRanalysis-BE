from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from git import Repo
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.commit import Commit
from app.models.file_change import FileChange

settings = get_settings()

CHANGE_TYPE_MAP = {
    "A": "A",
    "D": "D",
    "M": "M",
    "R": "R",
    "T": "M",
}


class GitHistoryParser:
    def __init__(self, db: Session, repository_id, batch_size: int | None = None) -> None:
        self.db = db
        self.repository_id = repository_id
        self.batch_size = batch_size or settings.PARSE_BATCH_SIZE

    def parse(
        self,
        clone_path: str | Path,
        on_progress: Callable[[int], None] | None = None,
    ) -> int:
        repo = Repo(str(clone_path))
        try:
            commit_buffer: list[Commit] = []
            file_change_buffer: list[FileChange] = []
            total = 0

            for git_commit in repo.iter_commits():
                committed_at = datetime.fromtimestamp(git_commit.committed_date, tz=UTC)
                parents = [p.hexsha for p in git_commit.parents]
                commit_row = Commit(
                    repository_id=self.repository_id,
                    hash=git_commit.hexsha,
                    author_name=git_commit.author.name or "Unknown",
                    author_email=git_commit.author.email or "unknown@local",
                    committed_at=committed_at,
                    message=git_commit.message or "",
                    parent_hashes=parents,
                )
                commit_buffer.append(commit_row)
                total += 1

                if git_commit.parents:
                    try:
                        diffs = git_commit.diff(git_commit.parents[0], create_patch=False)
                    except Exception:
                        diffs = []
                else:
                    try:
                        diffs = git_commit.diff(None, create_patch=False)
                    except Exception:
                        diffs = []

                for diff_item in diffs:
                    change_type = CHANGE_TYPE_MAP.get(diff_item.change_type or "M", "M")
                    path = diff_item.b_path or diff_item.a_path or ""
                    if not path:
                        continue
                    file_change_buffer.append(
                        FileChange(
                            commit=commit_row,
                            file_path=path,
                            change_type=change_type,
                            insertions=0,
                            deletions=0,
                        )
                    )

                if len(commit_buffer) >= self.batch_size:
                    self._flush(commit_buffer, file_change_buffer, on_progress, total)

            if commit_buffer:
                self._flush(commit_buffer, file_change_buffer, on_progress, total)

            return total
        finally:
            repo.close()

    def _flush(
        self,
        commit_buffer: list[Commit],
        file_change_buffer: list[FileChange],
        on_progress: Callable[[int], None] | None,
        total: int,
    ) -> None:
        self.db.add_all(commit_buffer)
        self.db.commit()
        commit_buffer.clear()
        file_change_buffer.clear()
        if on_progress:
            on_progress(min(99, total % 100))
