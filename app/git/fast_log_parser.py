import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.commit import Commit
from app.models.file_change import FileChange

settings = get_settings()

COMMIT_MARKER = "@@@"


def _infer_change_type(insertions: int, deletions: int) -> str:
    if insertions > 0 and deletions == 0:
        return "A"
    if insertions == 0 and deletions > 0:
        return "D"
    return "M"


def _parse_numstat_line(line: str) -> tuple[int, int, str] | None:
    parts = line.split("\t")
    if len(parts) != 3:
        return None
    ins_raw, dels_raw, path = parts
    if not path:
        return None
    if ins_raw == "-" or dels_raw == "-":
        return 0, 0, path
    return int(ins_raw), int(dels_raw), path


class FastGitLogParser:
    def __init__(self, db: Session, repository_id, batch_size: int | None = None) -> None:
        self.db = db
        self.repository_id = repository_id
        self.batch_size = batch_size or settings.PARSE_BATCH_SIZE

    def parse(
        self,
        clone_path: str | Path,
        on_progress: Callable[[int], None] | None = None,
    ) -> int:
        clone_path = Path(clone_path)
        total_commits = self._count_commits(clone_path)
        if total_commits == 0:
            return 0

        command = [
            "git",
            "-C",
            str(clone_path),
            "log",
            "--numstat",
            "--no-renames",
            "--pretty=format:@@@%n%H%n%an%n%ae%n%at%n%s%n%P",
        ]
        max_commits = settings.ANALYSIS_MAX_COMMITS
        if max_commits > 0:
            command.append(f"--max-count={max_commits}")
            total_commits = min(total_commits, max_commits)

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "git log failed")

        commit_buffer: list[Commit] = []
        total = 0

        for block in result.stdout.split(f"{COMMIT_MARKER}\n"):
            block = block.strip()
            if not block:
                continue

            lines = block.split("\n")
            if len(lines) < 6:
                continue

            commit_hash, author_name, author_email, committed_raw, message, parents_raw = lines[:6]
            parent_hashes = parents_raw.split() if parents_raw else []
            committed_at = datetime.fromtimestamp(int(committed_raw), tz=UTC)

            commit_row = Commit(
                repository_id=self.repository_id,
                hash=commit_hash,
                author_name=author_name or "Unknown",
                author_email=author_email or "unknown@local",
                committed_at=committed_at,
                message=message or "",
                parent_hashes=parent_hashes,
            )
            commit_buffer.append(commit_row)

            for line in lines[6:]:
                parsed = _parse_numstat_line(line)
                if parsed is None:
                    continue
                insertions, deletions, path = parsed
                commit_row.file_changes.append(
                    FileChange(
                        file_path=path,
                        change_type=_infer_change_type(insertions, deletions),
                        insertions=insertions,
                        deletions=deletions,
                    )
                )

            total += 1
            if len(commit_buffer) >= self.batch_size:
                self._flush(commit_buffer, on_progress, total, total_commits)

        if commit_buffer:
            self._flush(commit_buffer, on_progress, total, total_commits)

        return total

    def _count_commits(self, clone_path: Path) -> int:
        command = ["git", "-C", str(clone_path), "rev-list", "--count", "HEAD"]
        max_commits = settings.ANALYSIS_MAX_COMMITS
        if max_commits > 0:
            command.append(f"--max-count={max_commits}")
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            return 0
        return int(result.stdout.strip() or 0)

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
