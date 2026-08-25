import json
from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Any

from redis.asyncio import Redis, from_url

from app.core.config import get_settings


@lru_cache
def get_redis_pool() -> Redis:
    settings = get_settings()
    return from_url(settings.redis_url, decode_responses=True)


async def get_redis() -> AsyncGenerator[Redis, None]:
    yield get_redis_pool()


async def check_redis_connection() -> bool:
    try:
        redis = get_redis_pool()
        return bool(await redis.ping())
    except Exception:
        return False


def research_channel(research_job_id: str) -> str:
    return f"research:{research_job_id}:events"


async def publish_research_event(redis: Redis, research_job_id: str, event: dict[str, Any]) -> None:
    await redis.publish(research_channel(research_job_id), json.dumps(event, default=str))
