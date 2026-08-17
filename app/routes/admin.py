"""
Admin panel API routes (Phase 1): login, orders list, unanswered
queries list, call notes entry. Single admin account via .env —
no full user table yet.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select, desc

from app.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import verify_password, create_access_token, decode_access_token
from app.models.order import Order
from app.models.unanswered_query import UnansweredQuery
from app.models.client_profile import ClientProfile
from app.models.call_log import CallLog
from app.models.meeting import Meeting
from app.schemas.admin import (
    LoginRequest,
    TokenResponse,
    OrderOut,
    UnansweredQueryOut,
    CallNoteCreate,
    MeetingOut,
)
from app.utils.logger import logger

import uuid

router = APIRouter()
security_scheme = HTTPBearer()


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> str:
    """FastAPI dependency that validates the JWT and returns the admin username."""
    username = decode_access_token(credentials.credentials)
    if username is None or username != settings.admin_username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return username


@router.post("/admin/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    """Authenticate the admin and return a JWT access token."""
    if payload.username != settings.admin_username or not verify_password(
        payload.password, settings.admin_password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_access_token(subject=payload.username)
    return TokenResponse(access_token=token)


@router.get("/admin/orders", response_model=list[OrderOut])
async def list_orders(admin: str = Depends(get_current_admin)) -> list[OrderOut]:
    """List all orders/leads, most recent first."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Order).order_by(desc(Order.created_at)))
        orders = result.scalars().all()
        return [
            OrderOut(
                id=o.id,
                client_profile_id=o.client_profile_id,
                service_category=o.service_category.value,
                requirement_description=o.requirement_description,
                source_channel=o.source_channel,
                status=o.status.value,
                created_at=o.created_at,
            )
            for o in orders
        ]


@router.get("/admin/unanswered-queries", response_model=list[UnansweredQueryOut])
async def list_unanswered_queries(
    admin: str = Depends(get_current_admin),
) -> list[UnansweredQueryOut]:
    """List all unanswered queries, most recent first."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UnansweredQuery).order_by(desc(UnansweredQuery.created_at))
        )
        queries = result.scalars().all()
        return [
            UnansweredQueryOut(
                id=q.id,
                phone_number=q.phone_number,
                user_query=q.user_query,
                confidence_score=q.confidence_score,
                channel=q.channel.value,
                team_notified=q.team_notified,
                resolved=q.resolved,
                created_at=q.created_at,
            )
            for q in queries
        ]


@router.post("/admin/call-notes", status_code=status.HTTP_201_CREATED)
async def add_call_note_admin(
    payload: CallNoteCreate, admin: str = Depends(get_current_admin)
) -> dict:
    """
    Add a call note via the admin panel form. Creates a client profile
    if one doesn't exist yet for the given phone number.
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ClientProfile).where(
                    ClientProfile.phone_number == payload.phone_number
                )
            )
            client_profile = result.scalar_one_or_none()

            if client_profile is None:
                client_profile = ClientProfile(phone_number=payload.phone_number)
                session.add(client_profile)
                await session.flush()

            call_log = CallLog(
                id=uuid.uuid4(),
                client_profile_id=client_profile.id,
                notes=payload.notes,
                added_by=payload.added_by,
            )
            session.add(call_log)
            await session.commit()

            logger.info(
                f"Call note added via admin panel for {payload.phone_number} by {admin}"
            )
            return {"message": "Call note saved successfully."}

    except Exception as e:
        logger.error(f"Error saving call note via admin panel: {e}")
        raise HTTPException(status_code=500, detail="Failed to save call note.")


@router.get("/admin/meetings", response_model=list[MeetingOut])
async def list_meetings(admin: str = Depends(get_current_admin)) -> list[MeetingOut]:
    """List all meetings with client phone numbers and topics, most recent first."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Meeting, ClientProfile.phone_number)
            .join(ClientProfile, Meeting.client_profile_id == ClientProfile.id)
            .order_by(desc(Meeting.created_at))
        )
        rows = result.all()
        return [
            MeetingOut(
                id=meeting.id,
                phone_number=phone_number,
                client_name=meeting.client_name,
                topic=meeting.topic,
                scheduled_date=meeting.scheduled_date,
                scheduled_time=meeting.scheduled_time,
                event_link=meeting.event_link,
                is_active=meeting.is_active,
                created_at=meeting.created_at,
            )
            for meeting, phone_number in rows
        ]
