from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.analytics_snapshot import AnalyticsSnapshot
from app.models.commit import Commit
from app.models.contributor_stat import ContributorStat
from app.models.file_change import FileChange

settings = get_settings()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class AnalyticsEngine:
    def __init__(self, db: Session, repository_id: UUID) -> None:
        self.db = db
        self.repository_id = repository_id

    def run(self) -> datetime:
        self.db.execute(
            delete(AnalyticsSnapshot).where(AnalyticsSnapshot.repository_id == self.repository_id)
        )
        self.db.execute(
            delete(ContributorStat).where(ContributorStat.repository_id == self.repository_id)
        )
        self.db.commit()

        computed_at = datetime.now(UTC)
        metrics = {
            "summary": self._compute_summary(),
            "commits_per_week": self._compute_commits_per_week(),
            "top_contributors": self._compute_top_contributors(),
            "top_modified_files": self._compute_top_modified_files(),
            "inactive_contributors": self._compute_inactive_contributors(),
            "folder_growth": self._compute_folder_growth(),
            "bus_factor": self._compute_bus_factor(),
            "largest_commits": self._compute_largest_commits(),
        }

        for key, payload in metrics.items():
            self.db.add(
                AnalyticsSnapshot(
                    repository_id=self.repository_id,
                    metric_key=key,
                    payload=payload,
                    computed_at=computed_at,
                )
            )

        self._persist_contributor_stats(metrics["top_contributors"], computed_at)
        self.db.commit()
        return computed_at

    def _compute_summary(self) -> dict[str, Any]:
        row = self.db.execute(
            select(
                func.count(Commit.id),
                func.count(func.distinct(Commit.author_email)),
                func.min(Commit.committed_at),
                func.max(Commit.committed_at),
            ).where(Commit.repository_id == self.repository_id)
        ).one()

        total_commits, total_contributors, first_commit, last_commit = row
        avg_per_day = 0.0
        if first_commit and last_commit and total_commits:
            days = max((last_commit - first_commit).total_seconds() / 86400, 1)
            avg_per_day = round(total_commits / days, 2)

        return {
            "total_commits": total_commits or 0,
            "total_contributors": total_contributors or 0,
            "first_commit": first_commit.isoformat() if first_commit else None,
            "last_commit": last_commit.isoformat() if last_commit else None,
            "avg_commits_per_day": avg_per_day,
        }

    def _compute_commits_per_week(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            select(Commit.committed_at)
            .where(Commit.repository_id == self.repository_id)
            .order_by(Commit.committed_at)
        ).all()

        buckets: dict[str, int] = defaultdict(int)
        for (committed_at,) in rows:
            iso = committed_at.isocalendar()
            week = f"{iso.year}-W{iso.week:02d}"
            buckets[week] += 1

        return [{"week": week, "count": count} for week, count in sorted(buckets.items())]

    def _line_stats_by_email(self) -> dict[str, tuple[int, int]]:
        rows = self.db.execute(
            select(
                Commit.author_email,
                func.coalesce(func.sum(FileChange.insertions), 0),
                func.coalesce(func.sum(FileChange.deletions), 0),
            )
            .join(FileChange, FileChange.commit_id == Commit.id)
            .where(Commit.repository_id == self.repository_id)
            .group_by(Commit.author_email)
        ).all()
        return {email: (int(ins), int(dels)) for email, ins, dels in rows}

    def _aggregate_contributors_by_email(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            select(
                Commit.author_email,
                Commit.author_name,
                func.count(Commit.id),
                func.max(Commit.committed_at),
            )
            .where(Commit.repository_id == self.repository_id)
            .group_by(Commit.author_email, Commit.author_name)
        ).all()

        merged: dict[str, dict[str, Any]] = {}
        for email, name, commit_count, last_at in rows:
            entry = merged.get(email)
            if entry is None:
                merged[email] = {
                    "email": email,
                    "name": name,
                    "commits": commit_count,
                    "last_at": last_at,
                }
                continue
            entry["commits"] += commit_count
            if last_at > entry["last_at"]:
                entry["last_at"] = last_at
                entry["name"] = name

        line_stats = self._line_stats_by_email()
        result = []
        for email, entry in merged.items():
            ins, dels = line_stats.get(email, (0, 0))
            result.append(
                {
                    "name": entry["name"],
                    "email": email,
                    "commits": entry["commits"],
                    "lines_changed": int(ins) + int(dels),
                    "lines_added": int(ins),
                    "lines_deleted": int(dels),
                    "last_at": entry["last_at"],
                }
            )
        result.sort(key=lambda row: row["commits"], reverse=True)
        return result

    def _compute_top_contributors(self) -> list[dict[str, Any]]:
        return [
            {
                "name": row["name"],
                "email": row["email"],
                "commits": row["commits"],
                "lines_changed": row["lines_changed"],
            }
            for row in self._aggregate_contributors_by_email()[:10]
        ]

    def _compute_top_modified_files(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            select(
                FileChange.file_path,
                func.count(FileChange.id),
                func.coalesce(func.sum(FileChange.insertions + FileChange.deletions), 0),
            )
            .join(Commit, Commit.id == FileChange.commit_id)
            .where(Commit.repository_id == self.repository_id)
            .group_by(FileChange.file_path)
            .order_by(func.count(FileChange.id).desc())
            .limit(20)
        ).all()

        return [
            {
                "path": path,
                "change_count": count,
                "churn_score": round((count + churn) / 2, 2),
            }
            for path, count, churn in rows
        ]

    def _compute_inactive_contributors(self) -> list[dict[str, Any]]:
        now = datetime.now(UTC)
        threshold = now - timedelta(days=settings.INACTIVE_CONTRIBUTOR_DAYS)
        result = []
        for row in self._aggregate_contributors_by_email():
            last_at_utc = _as_utc(row["last_at"])
            if last_at_utc >= threshold:
                continue
            days_inactive = (now - last_at_utc).days
            result.append(
                {
                    "name": row["name"],
                    "last_commit_at": last_at_utc.isoformat(),
                    "days_inactive": days_inactive,
                }
            )
        result.sort(key=lambda item: item["days_inactive"], reverse=True)
        return result

    def _compute_folder_growth(self) -> list[dict[str, Any]]:
        bounds = self.db.execute(
            select(func.min(Commit.committed_at), func.max(Commit.committed_at)).where(
                Commit.repository_id == self.repository_id
            )
        ).one()
        first, last = bounds
        if not first or not last or first == last:
            return []

        midpoint = first + (last - first) / 2
        folder_first: dict[str, int] = defaultdict(int)
        folder_second: dict[str, int] = defaultdict(int)

        rows = self.db.execute(
            select(FileChange.file_path, Commit.committed_at)
            .join(Commit, Commit.id == FileChange.commit_id)
            .where(Commit.repository_id == self.repository_id)
        ).all()

        for path, committed_at in rows:
            folder = _top_level_folder(path)
            if committed_at <= midpoint:
                folder_first[folder] += 1
            else:
                folder_second[folder] += 1

        all_folders = set(folder_first) | set(folder_second)
        result = []
        for folder in all_folders:
            fh = folder_first.get(folder, 0)
            sh = folder_second.get(folder, 0)
            growth = round(sh / max(fh, 1), 2)
            result.append(
                {
                    "path": folder,
                    "commits_first_half": fh,
                    "commits_second_half": sh,
                    "growth_rate": growth,
                }
            )
        result.sort(key=lambda x: x["growth_rate"], reverse=True)
        return result[:20]

    def _compute_bus_factor(self) -> dict[str, Any]:
        rows = self.db.execute(
            select(Commit.author_email, func.count(Commit.id))
            .where(Commit.repository_id == self.repository_id)
            .group_by(Commit.author_email)
            .order_by(func.count(Commit.id).desc())
        ).all()

        if not rows:
            return {"score": 0, "top_contributor_pct": 0.0}

        total = sum(count for _, count in rows)
        cumulative = 0
        score = 0
        for _email, count in rows:
            cumulative += count
            score += 1
            if cumulative / total >= 0.5:
                break

        top_pct = round(rows[0][1] / total, 2) if total else 0.0
        return {"score": score, "top_contributor_pct": top_pct}

    def _compute_largest_commits(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            select(
                Commit.hash,
                Commit.message,
                Commit.committed_at,
                func.coalesce(func.sum(FileChange.insertions), 0),
                func.coalesce(func.sum(FileChange.deletions), 0),
            )
            .outerjoin(FileChange, FileChange.commit_id == Commit.id)
            .where(Commit.repository_id == self.repository_id)
            .group_by(Commit.id, Commit.hash, Commit.message, Commit.committed_at)
            .order_by(
                func.coalesce(func.sum(FileChange.insertions + FileChange.deletions), 0).desc()
            )
            .limit(10)
        ).all()

        return [
            {
                "hash": h[:12],
                "message": (msg or "")[:200],
                "insertions": int(ins),
                "deletions": int(dels),
                "committed_at": at.isoformat(),
            }
            for h, msg, at, ins, dels in rows
        ]

    def _persist_contributor_stats(
        self, _top_contributors: list[dict[str, Any]], _computed_at: datetime
    ) -> None:
        for row in self._aggregate_contributors_by_email():
            self.db.add(
                ContributorStat(
                    repository_id=self.repository_id,
                    author_email=row["email"],
                    author_name=row["name"],
                    commit_count=row["commits"],
                    lines_added=row["lines_added"],
                    lines_deleted=row["lines_deleted"],
                    last_commit_at=row["last_at"],
                )
            )


def _top_level_folder(path: str) -> str:
    parts = path.replace("\\", "/").split("/")
    if len(parts) > 1:
        return parts[0] + "/"
    return "(root)"
