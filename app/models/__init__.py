"""
Import all models here so Alembic and SQLAlchemy's metadata
can discover them for migrations and table creation.
"""

from app.models.client_profile import ClientProfile
from app.models.order import Order, OrderStatus, ServiceCategory
from app.models.call_log import CallLog
from app.models.unanswered_query import UnansweredQuery, QueryChannel
from app.models.meeting import Meeting

__all__ = [
    "ClientProfile",
    "Order",
    "OrderStatus",
    "ServiceCategory",
    "CallLog",
    "UnansweredQuery",
    "QueryChannel",
    "Meeting",
]
