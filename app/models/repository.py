from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import RepositoryStatus


class Repository(Base, TimestampMixin):
    __tablename__ = "repositories"
    __table_args__ = (UniqueConstraint("user_id", "owner", "name", name="uq_user_owner_name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    clone_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[RepositoryStatus] = mapped_column(
        String(32), default=RepositoryStatus.PENDING, nullable=False
    )
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    analysis_jobs: Mapped[list[AnalysisJob]] = relationship(back_populates="repository")
    commits: Mapped[list[Commit]] = relationship(back_populates="repository")
    contributor_stats: Mapped[list[ContributorStat]] = relationship(back_populates="repository")
    analytics_snapshots: Mapped[list[AnalyticsSnapshot]] = relationship(
        back_populates="repository"
    )
