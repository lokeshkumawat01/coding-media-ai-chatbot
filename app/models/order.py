"""
Order model — represents a captured lead/order when a client shows interest
in a service (website development, design, AI automation, custom software).
"""

import uuid
import enum
from datetime import datetime

from sqlalchemy import String, DateTime, Text, ForeignKey, Enum, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base
from app.core.db_types import EncryptedText


class OrderStatus(str, enum.Enum):
    NEW = "new"
    CONTACTED = "contacted"
    IN_PROGRESS = "in_progress"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


class ServiceCategory(str, enum.Enum):
    WEB_DEVELOPMENT = "web-development"
    WEB_DESIGN = "web-design"
    GRAPHIC_DESIGN = "graphic-design"
    AI_AUTOMATION = "ai-automation"
    CUSTOM_SOFTWARE = "custom-software"
    OTHER = "other"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    client_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client_profiles.id"), nullable=False, index=True
    )

    service_category: Mapped[ServiceCategory] = mapped_column(
        Enum(ServiceCategory, name="service_category_enum"), nullable=False
    )

    # Client's own description of what they need, captured from conversation
    requirement_description: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)

    # Which channel the lead came from: "whatsapp" or "website"
    source_channel: Mapped[str] = mapped_column(String(20), nullable=False)

    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status_enum"),
        default=OrderStatus.NEW,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Order id={self.id} category={self.service_category} status={self.status}>"
