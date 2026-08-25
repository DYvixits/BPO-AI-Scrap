"""arq worker entrypoint: `arq app.workers.worker.WorkerSettings`."""

from typing import ClassVar

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.workers.tasks.research import run_research_job

configure_logging()

settings = get_settings()


class WorkerSettings:
    functions: ClassVar = [run_research_job]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = settings.crawler_max_concurrency
