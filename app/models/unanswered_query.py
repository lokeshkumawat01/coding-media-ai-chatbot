"""
Unanswered query model — logs questions where RAG confidence was too low
to answer reliably. Used for weekly review and team notification.
"""

import uuid
import enum
from datetime import datetime

from sqlalchemy import String, DateTime, Text, Float, Boolean, Enum, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class QueryChannel(str, enum.Enum):
    WHATSAPP = "whatsapp"
    WEBSITE = "website"


class UnansweredQuery(Base):
    __tablename__ = "unanswered_queries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Phone number if available (may be null for anonymous website visitors)
    phone_number: Mapped[str | None] = mapped_column(
        String(20), nullable=True, index=True
    )

    user_query: Mapped[str] = mapped_column(Text, nullable=False)

    # RAG similarity/confidence score that triggered the fallback
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    channel: Mapped[QueryChannel] = mapped_column(
        Enum(QueryChannel, name="query_channel_enum"), nullable=False
    )

    # Whether the team has been notified about this unanswered query
    team_notified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Whether this has been reviewed/resolved in the weekly improvement cycle
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<UnansweredQuery id={self.id} resolved={self.resolved}>"
