from fastapi import APIRouter

from app.core.database import check_database_connection
from app.core.redis import check_redis_connection

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    db_ok = await check_database_connection()
    redis_ok = await check_redis_connection()
    status_ = "ok" if (db_ok and redis_ok) else "degraded"
    return {
        "status": status_,
        "checks": {"database": db_ok, "redis": redis_ok},
    }
