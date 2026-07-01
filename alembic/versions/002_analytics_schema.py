"""analytics schema

Revision ID: 002_analytics_schema
Revises: 001_create_users
Create Date: 2026-06-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_analytics_schema"
down_revision: str | None = "001_create_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "repositories",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=512), nullable=False),
        sa.Column("clone_path", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "owner", "name", name="uq_user_owner_name"),
    )
    op.create_index(op.f("ix_repositories_user_id"), "repositories", ["user_id"])

    op.create_table(
        "analysis_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("repository_id", sa.UUID(), nullable=False),
        sa.Column("celery_task_id", sa.String(length=255), nullable=True),
        sa.Column("stage", sa.String(length=64), nullable=True),
        sa.Column("progress_pct", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_analysis_jobs_repository_id"), "analysis_jobs", ["repository_id"])

    op.create_table(
        "commits",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("repository_id", sa.UUID(), nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.Column("author_name", sa.String(length=255), nullable=False),
        sa.Column("author_email", sa.String(length=320), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("parent_hashes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("repository_id", "hash", name="uq_repo_commit_hash"),
    )
    op.create_index(op.f("ix_commits_repository_id"), "commits", ["repository_id"])

    op.create_table(
        "file_changes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("commit_id", sa.UUID(), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("change_type", sa.String(length=8), nullable=False),
        sa.Column("insertions", sa.Integer(), nullable=False),
        sa.Column("deletions", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["commit_id"], ["commits.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_file_changes_commit_id"), "file_changes", ["commit_id"])

    op.create_table(
        "contributor_stats",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("repository_id", sa.UUID(), nullable=False),
        sa.Column("author_email", sa.String(length=320), nullable=False),
        sa.Column("author_name", sa.String(length=255), nullable=False),
        sa.Column("commit_count", sa.Integer(), nullable=False),
        sa.Column("lines_added", sa.Integer(), nullable=False),
        sa.Column("lines_deleted", sa.Integer(), nullable=False),
        sa.Column("last_commit_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("repository_id", "author_email", name="uq_repo_author_email"),
    )
    op.create_index(
        op.f("ix_contributor_stats_repository_id"), "contributor_stats", ["repository_id"]
    )

    op.create_table(
        "analytics_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("repository_id", sa.UUID(), nullable=False),
        sa.Column("metric_key", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("repository_id", "metric_key", name="uq_repo_metric_key"),
    )
    op.create_index(
        op.f("ix_analytics_snapshots_repository_id"),
        "analytics_snapshots",
        ["repository_id"],
    )


def downgrade() -> None:
    op.drop_table("analytics_snapshots")
    op.drop_table("contributor_stats")
    op.drop_table("file_changes")
    op.drop_table("commits")
    op.drop_table("analysis_jobs")
    op.drop_table("repositories")
