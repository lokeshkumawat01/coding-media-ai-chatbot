"""
Pydantic schemas for the admin panel API.
"""

from datetime import datetime
from pydantic import BaseModel
from uuid import UUID


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class OrderOut(BaseModel):
    id: UUID
    client_profile_id: UUID
    service_category: str
    requirement_description: str | None
    source_channel: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class UnansweredQueryOut(BaseModel):
    id: UUID
    phone_number: str | None
    user_query: str
    confidence_score: float | None
    channel: str
    team_notified: bool
    resolved: bool
    created_at: datetime

    class Config:
        from_attributes = True


class CallNoteCreate(BaseModel):
    phone_number: str
    notes: str
    added_by: str


class MeetingOut(BaseModel):
    id: UUID
    phone_number: str
    client_name: str | None
    topic: str | None
    scheduled_date: str
    scheduled_time: str
    event_link: str | None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
