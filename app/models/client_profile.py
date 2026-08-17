"""
Client profile model — the unified "memory" of a client across
WhatsApp, website chat, and human call notes. Keyed by phone number.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base
from app.core.db_types import EncryptedText


class ClientProfile(Base):
    __tablename__ = "client_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Unique identifier across channels (WhatsApp number or website session-linked phone)
    phone_number: Mapped[str] = mapped_column(
        String(20), unique=True, index=True, nullable=False
    )

    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Encrypted free-text summary combining WhatsApp history + website chat summary + call notes.
    # Encryption/decryption handled at the service layer using FIELD_ENCRYPTION_KEY.
    profile_summary: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)

    # Which channels this client has interacted through, e.g. "whatsapp,website"
    channels_used: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<ClientProfile phone={self.phone_number}>"
