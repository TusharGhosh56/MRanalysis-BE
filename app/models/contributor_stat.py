from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ContributorStat(Base):
    __tablename__ = "contributor_stats"
    __table_args__ = (
        UniqueConstraint("repository_id", "author_email", name="uq_repo_author_email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    author_email: Mapped[str] = mapped_column(String(320), nullable=False)
    author_name: Mapped[str] = mapped_column(String(255), nullable=False)
    commit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lines_added: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lines_deleted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_commit_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    repository: Mapped[Repository] = relationship(back_populates="contributor_stats")
