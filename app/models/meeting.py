"""
Meeting model — tracks booked consultation calls so we can detect and
cancel/replace a client's previous booking when they reschedule, instead
of creating duplicate calendar events.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Boolean, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client_profiles.id"), nullable=False, index=True
    )
    google_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(300), nullable=True)
    client_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    scheduled_date: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # YYYY-MM-DD
    scheduled_time: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # e.g. "10:00 AM"
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True
    )  # False once cancelled/replaced
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Meeting {self.scheduled_date} {self.scheduled_time} active={self.is_active}>"
