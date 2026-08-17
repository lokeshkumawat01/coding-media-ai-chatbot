"""
Async Redis client setup, used for caching repeated FAQ responses
and storing lightweight session conversation history.
"""

import redis.asyncio as redis

from app.config import settings

redis_client = redis.from_url(settings.redis_url, decode_responses=True)
