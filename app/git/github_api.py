import concurrent.futures
from datetime import UTC, datetime
import logging
from typing import Callable
from uuid import UUID

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.git.fast_log_parser import _infer_change_type
from app.models.commit import Commit
from app.models.file_change import FileChange

logger = logging.getLogger(__name__)
settings = get_settings()

STATUS_MAP = {
    "added": "A",
    "removed": "D",
    "modified": "M",
    "renamed": "M",
}


def _get_headers() -> dict[str, str]:
    headers = {
        "User-Agent": "MRanalytics-App",
        "Accept": "application/vnd.github+json",
    }
    token = getattr(settings, "GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def parse_repository_from_github_api(
    db: Session,
    repository_id: UUID,
    owner: str,
    name: str,
    on_progress: Callable[[int], None] | None = None,
) -> int:
    headers = _get_headers()
    client = httpx.Client(headers=headers, timeout=30.0)

    # 1. Fetch commits list
    commits_summary: list[dict] = []
    page = 1
    max_commits = settings.ANALYSIS_MAX_COMMITS or 300

    try:
        while len(commits_summary) < max_commits:
            per_page = min(100, max_commits - len(commits_summary))
            url = f"https://api.github.com/repos/{owner}/{name}/commits?page={page}&per_page={per_page}"
            resp = client.get(url)

            if resp.status_code == 404:
                raise ValueError(f"GitHub repository {owner}/{name} not found or is private")
            if resp.status_code == 403 and "rate limit" in resp.text.lower():
                raise ValueError(
                    "GitHub API rate limit exceeded. Please set GITHUB_TOKEN in your environment variables."
                )
            resp.raise_for_status()

            batch = resp.json()
            if not isinstance(batch, list) or not batch:
                break

            commits_summary.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"Failed to fetch commits from GitHub API: {exc.response.text}") from exc

    total_commits = len(commits_summary)
    if total_commits == 0:
        return 0

    # 2. Clean existing commits and file changes
    db.execute(
        delete(FileChange).where(
            FileChange.commit_id.in_(
                select(Commit.id).where(Commit.repository_id == repository_id)
            )
        )
    )
    db.execute(delete(Commit).where(Commit.repository_id == repository_id))
    db.commit()

    if on_progress:
        on_progress(35)

    # 3. Fetch detailed commit stats with files in parallel
    def _fetch_commit_detail(item: dict) -> dict:
        sha = item.get("sha", "")
        detail_url = f"https://api.github.com/repos/{owner}/{name}/commits/{sha}"
        try:
            r = client.get(detail_url)
            if r.status_code == 200:
                return r.json()
        except Exception:
            logger.warning("Failed to fetch detail for commit %s", sha)
        return item

    workers = min(8, total_commits)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        detailed_commits = list(pool.map(_fetch_commit_detail, commits_summary))

    if on_progress:
        on_progress(65)

    # 4. Save Commit and FileChange rows to database
    commit_rows: list[Commit] = []
    for data in detailed_commits:
        commit_info = data.get("commit") or {}
        author_info = commit_info.get("author") or {}
        committer_info = commit_info.get("committer") or {}

        author_name = author_info.get("name") or committer_info.get("name") or "Unknown"
        author_email = author_info.get("email") or committer_info.get("email") or "unknown@github"
        date_str = author_info.get("date") or committer_info.get("date")

        if date_str:
            try:
                committed_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except Exception:
                committed_at = datetime.now(UTC)
        else:
            committed_at = datetime.now(UTC)

        message = commit_info.get("message") or ""
        parents = [p.get("sha") for p in data.get("parents", []) if p.get("sha")]

        commit_row = Commit(
            repository_id=repository_id,
            hash=data.get("sha", ""),
            author_name=author_name,
            author_email=author_email,
            committed_at=committed_at,
            message=message,
            parent_hashes=parents,
        )

        files = data.get("files") or []
        for f in files:
            file_path = f.get("filename") or ""
            status = f.get("status") or "modified"
            change_type = STATUS_MAP.get(status, _infer_change_type(f.get("additions", 0), f.get("deletions", 0)))
            commit_row.file_changes.append(
                FileChange(
                    file_path=file_path,
                    change_type=change_type,
                    insertions=int(f.get("additions") or 0),
                    deletions=int(f.get("deletions") or 0),
                )
            )

        commit_rows.append(commit_row)

    db.add_all(commit_rows)
    db.commit()

    if on_progress:
        on_progress(85)

    return len(commit_rows)
