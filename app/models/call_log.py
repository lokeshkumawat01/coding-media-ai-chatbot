"""
Call log model — notes added by a human team member after a phone call
with a client. Used to bridge human context into future bot conversations.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base
from app.core.db_types import EncryptedText

class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    client_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client_profiles.id"), nullable=False, index=True
    )

    # Free-text notes entered by the team member via the admin panel
    notes: Mapped[str] = mapped_column(EncryptedText, nullable=False)

    # Name/identifier of the team member who added this note
    added_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<CallLog id={self.id} client_profile_id={self.client_profile_id}>"
