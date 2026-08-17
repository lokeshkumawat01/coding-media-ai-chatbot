"""
MCP (Model Context Protocol) server exposing tools that the LangGraph
agent can call: get_past_solutions, create_order, check_available_slots,
book_meeting, add_call_notes, get_client_context, search_knowledge_base.
"""

import asyncio
import uuid
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from app.core.database import AsyncSessionLocal
from app.models.client_profile import ClientProfile
from app.models.call_log import CallLog
from app.models.order import Order, ServiceCategory, OrderStatus
from datetime import datetime, timedelta
from app.models.meeting import Meeting
from app.rag.chroma_client import get_knowledge_collection
from app.mcp_tools.calendar_client import (
    get_available_slots_sync,
    book_meeting_sync,
    cancel_event_sync,
)
from app.utils.logger import logger
from app.utils.email_client import send_team_notification

from sqlalchemy import select, desc

mcp = FastMCP("solutions-agency-tools")

# Valid service categories (mirrors ServiceCategory enum in app/models/order.py)
VALID_CATEGORIES = {
    "web-development",
    "web-design",
    "graphic-design",
    "ai-automation",
    "custom-software",
}


@mcp.tool()
async def get_past_solutions(category: str, limit: int = 3) -> str:
    """
    Retrieve past case studies/solutions for a given service category.
    Each result follows the Problem -> Solution -> Result format.

    Args:
        category: One of "web-development", "web-design", "graphic-design",
            "ai-automation", "custom-software".
        limit: Maximum number of case studies to return (default 3).

    Returns:
        A formatted string with matching case studies, or a message
        indicating no case studies were found for that category.
    """
    if category not in VALID_CATEGORIES:
        logger.warning(f"get_past_solutions called with invalid category: {category}")
        return (
            f"Invalid category '{category}'. Valid categories are: "
            f"{', '.join(sorted(VALID_CATEGORIES))}."
        )

    try:
        collection = get_knowledge_collection()
        results = await asyncio.to_thread(
            collection.query,
            query_texts=[f"case study {category} problem solution result"],
            n_results=limit,
            where={
                "$and": [
                    {"category": category},
                    {"type": "case_study"},
                ]
            },
        )

        documents = results.get("documents", [[]])[0]

        if not documents:
            return f"No past case studies found for category '{category}' yet."

        formatted = "\n\n---\n\n".join(documents)
        return formatted

    except Exception as e:
        logger.error(f"Error retrieving past solutions for category '{category}': {e}")
        return (
            "Sorry, I couldn't retrieve past case studies right now. Please try again."
        )


@mcp.tool()
async def create_order(
    phone_number: str,
    service_category: str,
    requirement_description: str,
) -> str:
    """
    Create a new lead/order when a client shows interest in a service.
    Creates a client profile automatically if one doesn't exist yet.
    Skips creating a duplicate order if the same client already has an
    open order for the same category within the last 24 hours.

    Args:
        phone_number: Client's phone number (used as the unique client key).
        service_category: One of "web-development", "web-design",
            "graphic-design", "ai-automation", "custom-software".
        requirement_description: What the client said they need, in their
            own words or a brief summary of the conversation.

    Returns:
        A confirmation message with the order ID, or an error message
        if the input was invalid.
    """
    source_channel = "website"  # Hardcoded: only channel currently live is the website widget

    if service_category not in VALID_CATEGORIES:
        logger.warning(f"create_order called with invalid category: {service_category}")
        return (
            f"Invalid service category '{service_category}'. Valid categories are: "
            f"{', '.join(sorted(VALID_CATEGORIES))}."
        )

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ClientProfile).where(ClientProfile.phone_number == phone_number)
            )
            client_profile = result.scalar_one_or_none()

            if client_profile is None:
                client_profile = ClientProfile(
                    phone_number=phone_number,
                    channels_used=source_channel,
                )
                session.add(client_profile)
                await session.flush()
                logger.info(f"Created new client profile for phone: {phone_number}")
            else:
                existing_channels = set(
                    (client_profile.channels_used or "").split(",")
                ) - {""}
                existing_channels.add(source_channel)
                client_profile.channels_used = ",".join(sorted(existing_channels))

            # --- Duplicate lead check: skip creating a new order if an
            # open order for the same category already exists within the
            # last 24 hours for this client ---
            recent_cutoff = datetime.utcnow() - timedelta(hours=24)
            duplicate_result = await session.execute(
                select(Order).where(
                    Order.client_profile_id == client_profile.id,
                    Order.service_category == ServiceCategory(service_category),
                    Order.status == OrderStatus.NEW,
                    Order.created_at >= recent_cutoff,
                )
            )
            existing_order = duplicate_result.scalar_one_or_none()

            if existing_order is not None:
                logger.info(
                    f"Duplicate order skipped for {phone_number} "
                    f"(category: {service_category}, existing order: {existing_order.id})"
                )
                return (
                    f"We already have your {service_category} request on file "
                    f"(submitted recently) — our team will reach out to you shortly. "
                    f"No need to submit again!"
                )

            order = Order(
                id=uuid.uuid4(),
                client_profile_id=client_profile.id,
                service_category=ServiceCategory(service_category),
                requirement_description=requirement_description,
                source_channel=source_channel,
            )
            session.add(order)

            await session.commit()

            logger.info(f"Order created: {order.id} for client {phone_number}")

            await send_team_notification(
                subject=f"🆕 New Lead — {service_category}",
                body=(
                    f"A new lead has been captured.\n\n"
                    f"Phone: {phone_number}\n"
                    f"Category: {service_category}\n"
                    f"Requirement: {requirement_description}\n"
                    f"Channel: {source_channel}\n"
                    f"Order ID: {order.id}"
                ),
            )

            return (
                f"Order created successfully. Order ID: {order.id}. "
                f"Our team will reach out to you shortly regarding your {service_category} requirement."
            )

    except Exception as e:
        logger.error(f"Error creating order for {phone_number}: {e}")
        return "Sorry, I couldn't create the order right now. Please try again or contact us directly."

@mcp.tool()
async def check_available_slots(date: str) -> str:
    """
    Check available 30-minute meeting slots for a given date.

    Args:
        date: Date in YYYY-MM-DD format (e.g. "2026-08-10").

    Returns:
        A formatted string listing available time slots, or a message
        if none are available or the date format is invalid.
    """
    try:
        parsed_date = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return "Invalid date format. Please provide the date as YYYY-MM-DD."

    if parsed_date.date() < datetime.now().date():
        return "That date has already passed. Please choose a future date."

    try:
        slots = await asyncio.to_thread(get_available_slots_sync, parsed_date)

        if not slots:
            return f"No available slots on {date}. Please try another date."

        formatted = ", ".join(slots)
        return f"Available slots on {date}: {formatted}"

    except Exception as e:
        logger.error(f"Error checking available slots for {date}: {e}")
        return "Sorry, I couldn't check available slots right now. Please try again."


@mcp.tool()
async def book_meeting(
    date: str,
    time: str,
    client_name: str,
    client_phone: str,
    topic: str,
) -> str:
    """
    Book a 30-minute meeting slot on the calendar. If the client already
    has an active upcoming meeting booked, it will be automatically
    cancelled and replaced with this new one (reschedule behavior) —
    a client should only ever have one active meeting at a time.

    Args:
        date: Date in YYYY-MM-DD format (e.g. "2026-08-10").
        time: Time in "HH:MM AM/PM" format (e.g. "10:00 AM"), must match
            one of the slots returned by check_available_slots.
        client_name: Name of the client booking the meeting.
        client_phone: Client's phone number.
        topic: Brief topic/reason for the meeting (e.g. service category or need).

    Returns:
        A confirmation message with the calendar event link, or an error
        message if the slot is unavailable or input is invalid.
    """
    try:
        parsed_date = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return "Invalid date format. Please provide the date as YYYY-MM-DD."

    try:
        datetime.strptime(time, "%I:%M %p")
    except ValueError:
        return "Invalid time format. Please provide the time as 'HH:MM AM/PM', e.g. '10:00 AM'."

    try:
        available_slots = await asyncio.to_thread(get_available_slots_sync, parsed_date)
        if time not in available_slots:
            return (
                f"Sorry, {time} on {date} is no longer available. "
                f"Available slots: {', '.join(available_slots) if available_slots else 'none'}."
            )

        async with AsyncSessionLocal() as session:
            # Find or create client profile
            result = await session.execute(
                select(ClientProfile).where(ClientProfile.phone_number == client_phone)
            )
            client_profile = result.scalar_one_or_none()
            if client_profile is None:
                client_profile = ClientProfile(phone_number=client_phone)
                session.add(client_profile)
                await session.flush()

            # Cancel any existing active meeting for this client (reschedule behavior)
            existing_result = await session.execute(
                select(Meeting).where(
                    Meeting.client_profile_id == client_profile.id,
                    Meeting.is_active == True,  # noqa: E712
                )
            )
            existing_meetings = existing_result.scalars().all()

            was_rescheduled = False
            for existing in existing_meetings:
                await asyncio.to_thread(cancel_event_sync, existing.google_event_id)
                existing.is_active = False
                was_rescheduled = True
                logger.info(
                    f"Cancelled previous meeting for {client_phone}: {existing.google_event_id}"
                )

            # Book the new meeting
            booking = await asyncio.to_thread(
                book_meeting_sync, parsed_date, time, client_name, client_phone, topic
            )

            new_meeting = Meeting(
                id=uuid.uuid4(),
                client_profile_id=client_profile.id,
                google_event_id=booking["event_id"],
                event_link=booking["link"],
                scheduled_date=date,
                scheduled_time=time,
                topic=topic,
                client_name=client_name,
                is_active=True,
            )
            session.add(new_meeting)
            await session.commit()

        await send_team_notification(
            subject=f"📅 New Meeting Booked — {client_name}",
            body=(
                f"A client has booked a consultation call.\n\n"
                f"Name: {client_name}\n"
                f"Phone: {client_phone}\n"
                f"Date: {date}\n"
                f"Time: {time}\n"
                f"Topic: {topic}"
            ),
        )

        prefix = (
            "Your previous meeting has been rescheduled. " if was_rescheduled else ""
        )
        return (
            f"{prefix}Meeting confirmed for {date} at {time}. "
            f"Calendar link: {booking['link']}"
        )

    except Exception as e:
        logger.error(
            f"Error booking meeting for {client_phone} on {date} at {time}: {e}"
        )
        return "Sorry, I couldn't book the meeting right now. Please try again or contact us directly."


@mcp.tool()
async def add_call_notes(phone_number: str, notes: str, added_by: str) -> str:
    """
    Add notes from a human phone call with a client. These notes will
    be available to the bot in future conversations with this client
    via get_client_context.

    Args:
        phone_number: Client's phone number (must match an existing
            client profile; a new profile is created if none exists).
        notes: Free-text notes summarizing what was discussed on the call.
        added_by: Name/identifier of the team member adding this note.

    Returns:
        A confirmation message, or an error message if something went wrong.
    """
    if not notes or not notes.strip():
        return "Call notes cannot be empty."

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ClientProfile).where(ClientProfile.phone_number == phone_number)
            )
            client_profile = result.scalar_one_or_none()

            if client_profile is None:
                client_profile = ClientProfile(phone_number=phone_number)
                session.add(client_profile)
                await session.flush()
                logger.info(
                    f"Created new client profile for phone: {phone_number} (via call notes)"
                )

            call_log = CallLog(
                id=uuid.uuid4(),
                client_profile_id=client_profile.id,
                notes=notes.strip(),
                added_by=added_by,
            )
            session.add(call_log)

            await session.commit()

            logger.info(f"Call notes added for client {phone_number} by {added_by}")
            return f"Call notes saved successfully for {phone_number}."

    except Exception as e:
        logger.error(f"Error adding call notes for {phone_number}: {e}")
        return "Sorry, I couldn't save the call notes right now. Please try again."


@mcp.tool()
async def get_client_context(phone_number: str) -> str:
    """
    Retrieve a unified context summary for a client, combining their
    profile info, past orders, and human call notes — regardless of
    which channel (WhatsApp/website) the data came from.

    Use this at the start of a conversation with a returning client
    to personalize the response and avoid asking for info already known.

    Args:
        phone_number: Client's phone number.

    Returns:
        A formatted summary of the client's context, or a message
        indicating this is a new client with no prior history.
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ClientProfile).where(ClientProfile.phone_number == phone_number)
            )
            client_profile = result.scalar_one_or_none()

            if client_profile is None:
                return (
                    f"No prior history found for {phone_number}. This is a new client."
                )

            # Fetch past orders (most recent first)
            orders_result = await session.execute(
                select(Order)
                .where(Order.client_profile_id == client_profile.id)
                .order_by(desc(Order.created_at))
                .limit(5)
            )
            orders = orders_result.scalars().all()

            # Fetch call notes (most recent first)
            from app.models.call_log import CallLog

            call_logs_result = await session.execute(
                select(CallLog)
                .where(CallLog.client_profile_id == client_profile.id)
                .order_by(desc(CallLog.created_at))
                .limit(5)
            )
            call_logs = call_logs_result.scalars().all()

            # Build the summary
            parts = [
                f"Client: {client_profile.name or 'Unknown name'} ({phone_number})"
            ]
            parts.append(f"Channels used: {client_profile.channels_used or 'none yet'}")

            if orders:
                parts.append("\nPast orders/leads:")
                for order in orders:
                    parts.append(
                        f"  - [{order.status.value}] {order.service_category.value}: "
                        f"{order.requirement_description or 'no description'} "
                        f"(via {order.source_channel}, {order.created_at.strftime('%Y-%m-%d')})"
                    )
            else:
                parts.append("\nNo past orders/leads.")

            if call_logs:
                parts.append("\nHuman call notes:")
                for log in call_logs:
                    parts.append(
                        f"  - [{log.created_at.strftime('%Y-%m-%d')} by {log.added_by or 'unknown'}]: {log.notes}"
                    )
            else:
                parts.append("\nNo call notes on record.")

            return "\n".join(parts)

    except Exception as e:
        logger.error(f"Error retrieving client context for {phone_number}: {e}")
        return "Sorry, I couldn't retrieve the client's context right now."


@mcp.tool()
async def search_knowledge_base(query: str, limit: int = 3) -> str:
    """
    Search the company's general knowledge base (services, FAQs, company
    info, policies) for information relevant to the client's question.
    Use this whenever a client asks something about the company, its
    services, processes, or general information that isn't a request
    for past case studies specifically.

    Args:
        query: The client's question or topic to search for.
        limit: Maximum number of relevant knowledge chunks to return (default 3).

    Returns:
        A formatted string with relevant knowledge base excerpts, or a
        message indicating nothing relevant was found.
    """
    try:
        collection = get_knowledge_collection()
        results = await asyncio.to_thread(
            collection.query,
            query_texts=[query],
            n_results=limit,
            where={"type": "knowledge"},
        )

        documents = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]

        if not documents:
            return "No relevant information found in the knowledge base for this query."

        # Filter out weak matches (high distance = low relevance)
        # Threshold is heuristic based on the current embedding model's typical range
        relevant = [doc for doc, dist in zip(documents, distances) if dist < 25]

        if not relevant:
            return "No sufficiently relevant information found in the knowledge base for this query."

        return "\n\n---\n\n".join(relevant)

    except Exception as e:
        logger.error(f"Error searching knowledge base for query '{query}': {e}")
        return "Sorry, I couldn't search the knowledge base right now."
