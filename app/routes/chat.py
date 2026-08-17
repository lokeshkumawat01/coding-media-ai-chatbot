"""
Website chat endpoint. Shares the same core agent logic that the
WhatsApp webhook will also use later — no duplicated business logic.

Includes:
  - Global daily message cap (protects shared Groq free-tier quota
    across all visitors combined, not just per-IP)
  - Redis-based response caching for repeated FAQ-style queries
  - Redis-based short-term conversation history per session
  - Unanswered query logging + email notification when the agent's
    response indicates it could not help
"""
import json
import hashlib
from datetime import date

from fastapi import APIRouter, Request
from langchain_core.messages import HumanMessage, AIMessage

from app.schemas.chat import ChatRequest, ChatResponse
from app.core.redis_client import redis_client
from app.core.rate_limit import limiter
from app.core.database import AsyncSessionLocal
from app.models.unanswered_query import UnansweredQuery, QueryChannel
from app.agent.graph import run_agent
from app.utils.email_client import send_team_notification
from app.utils.logger import logger
from app.config import settings

router = APIRouter()

SESSION_HISTORY_TTL_SECONDS = 60 * 60 * 2  # 2 hours
CACHE_TTL_SECONDS = 60 * 60 * 6  # 6 hours
MAX_HISTORY_MESSAGES = 10  # keep last N messages for context

FALLBACK_INDICATORS = [
    "i couldn't", "i can't help", "sorry, i'm having trouble",
    "our team has been notified", "i don't have that information",
]


def _cache_key(message: str) -> str:
    """Generate a cache key based on the normalized message text."""
    normalized = message.strip().lower()
    digest = hashlib.sha256(normalized.encode()).hexdigest()
    return f"chat_cache:{digest}"


def _history_key(session_id: str) -> str:
    return f"chat_history:{session_id}"


def _daily_cap_key() -> str:
    return f"global_chat_count:{date.today().isoformat()}"


async def _get_history(session_id: str) -> list:
    raw = await redis_client.get(_history_key(session_id))
    if not raw:
        return []
    data = json.loads(raw)
    messages = []
    for item in data:
        if item["role"] == "user":
            messages.append(HumanMessage(content=item["content"]))
        else:
            messages.append(AIMessage(content=item["content"]))
    return messages


async def _save_history(session_id: str, history: list, new_user_msg: str, new_ai_msg: str):
    serializable = [
        {"role": "user" if isinstance(m, HumanMessage) else "assistant", "content": m.content}
        for m in history
    ]
    serializable.append({"role": "user", "content": new_user_msg})
    serializable.append({"role": "assistant", "content": new_ai_msg})
    serializable = serializable[-MAX_HISTORY_MESSAGES:]

    await redis_client.set(
        _history_key(session_id),
        json.dumps(serializable),
        ex=SESSION_HISTORY_TTL_SECONDS,
    )


async def _log_unanswered_query(user_query: str, phone_number: str | None):
    try:
        async with AsyncSessionLocal() as session:
            entry = UnansweredQuery(
                phone_number=phone_number,
                user_query=user_query,
                channel=QueryChannel.WEBSITE,
            )
            session.add(entry)
            await session.commit()
            logger.info(f"Logged unanswered query: {user_query[:80]}")

            await send_team_notification(
                subject="⚠️ Unanswered Query Logged",
                body=(
                    f"The bot could not confidently answer a client's question.\n\n"
                    f"Query: {user_query}\n"
                    f"Phone: {phone_number or 'unknown (website visitor)'}\n"
                    f"Channel: website"
                ),
            )
    except Exception as e:
        logger.error(f"Failed to log unanswered query: {e}")


def _looks_unanswered(reply: str) -> bool:
    reply_lower = reply.lower()
    return any(indicator in reply_lower for indicator in FALLBACK_INDICATORS)


async def _is_daily_cap_reached() -> bool:
    """
    Increments the global daily chat counter and returns True if the
    configured cap has been exceeded. This protects the shared Groq
    free-tier quota across ALL visitors combined, not just per-IP
    (per-IP is already handled separately by the @limiter.limit decorator).
    """
    key = _daily_cap_key()
    current_count = await redis_client.incr(key)
    if current_count == 1:
        # First message of the day for this key — set expiry (~26h, safe buffer past midnight)
        await redis_client.expire(key, 60 * 60 * 26)

    if current_count > settings.max_daily_chat_messages:
        logger.warning(
            f"Global daily chat cap reached ({current_count}/{settings.max_daily_chat_messages})"
        )
        return True
    return False


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("15/minute")
async def chat_endpoint(request: Request, payload: ChatRequest) -> ChatResponse:
    """
    Main website chat endpoint.
    Order of checks: daily cap -> cache -> run agent -> cache/save/notify.
    """
    # --- Global daily cap check (runs first, before any Groq usage) ---
    if await _is_daily_cap_reached():
        return ChatResponse(
            reply=(
                "We're experiencing high demand right now and have reached today's chat limit. "
                "Please try again tomorrow, or contact us directly at +91 83064 71487."
            ),
            session_id=payload.session_id,
        )

    # --- Check cache for repeated/FAQ-style queries ---
    cache_key = _cache_key(payload.message)
    cached_reply = await redis_client.get(cache_key)

    if cached_reply:
        logger.info(f"Cache hit for session {payload.session_id}")
        history = await _get_history(payload.session_id)
        await _save_history(payload.session_id, history, payload.message, cached_reply)
        return ChatResponse(reply=cached_reply, session_id=payload.session_id)

    # --- Run the agent ---
    history = await _get_history(payload.session_id)
    reply, used_tools = await run_agent(user_message=payload.message, conversation_history=history)

    # --- Cache only short, generic, non-tool-driven replies ---
    if len(payload.message) < 100 and not used_tools:
        await redis_client.set(cache_key, reply, ex=CACHE_TTL_SECONDS)

    # --- Save conversation history ---
    await _save_history(payload.session_id, history, payload.message, reply)

    # --- Log unanswered queries for weekly review ---
    if _looks_unanswered(reply):
        await _log_unanswered_query(payload.message, payload.phone_number)

    return ChatResponse(reply=reply, session_id=payload.session_id)