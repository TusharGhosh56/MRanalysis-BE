from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from git import Repo
from sqlalchemy.orm import Session

from app.config import get_settings
from app.git.fast_log_parser import _infer_change_type
from app.models.commit import Commit
from app.models.file_change import FileChange

settings = get_settings()


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
            total_commits = max(int(repo.git.rev_list("--count", "HEAD")), 1)
            commit_buffer: list[Commit] = []
            total = 0

            for git_commit in repo.iter_commits(max_count=settings.ANALYSIS_MAX_COMMITS or None):
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

                for path, stat in git_commit.stats.files.items():
                    commit_row.file_changes.append(
                        FileChange(
                            file_path=path,
                            change_type=_infer_change_type(stat.insertions, stat.deletions),
                            insertions=stat.insertions,
                            deletions=stat.deletions,
                        )
                    )

                if len(commit_buffer) >= self.batch_size:
                    self._flush(commit_buffer, on_progress, total, total_commits)

            if commit_buffer:
                self._flush(commit_buffer, on_progress, total, total_commits)

            return total
        finally:
            repo.close()

    def _flush(
        self,
        commit_buffer: list[Commit],
        on_progress: Callable[[int], None] | None,
        processed: int,
        total_commits: int,
    ) -> None:
        self.db.add_all(commit_buffer)
        self.db.commit()
        commit_buffer.clear()
        if on_progress and total_commits:
            on_progress(min(100, int(processed * 100 / total_commits)))
