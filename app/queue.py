"""
app/queue.py — RQ connection and job-enqueueing helper.

Redis connection is created lazily so import-time failures (e.g. Redis not
yet up when running unit tests) do not crash the whole app.
"""
import logging

import redis
from rq import Queue
from rq.job import Retry

from app.config import get_settings

logger = logging.getLogger(__name__)

_redis_conn: redis.Redis | None = None
_queue: Queue | None = None


def _get_redis() -> redis.Redis:
    global _redis_conn
    if _redis_conn is None:
        settings = get_settings()
        _redis_conn = redis.from_url(settings.redis_url, decode_responses=False)
    return _redis_conn


def get_queue() -> Queue:
    """Return the shared RQ queue (lazy singleton)."""
    global _queue
    if _queue is None:
        _queue = Queue("default", connection=_get_redis())
    return _queue


def enqueue_analysis(image_id: str) -> str | None:
    """
    Enqueue an image analysis job.

    Returns the RQ job ID on success, or None if Redis is unreachable.
    The upload endpoint stays non-blocking regardless — the image row is already
    in the DB with status=pending, so callers can poll /status.

    Retry(max=1): retries once on transient failure; genuinely corrupt images
    are caught inside the job and marked `failed` without triggering a retry.
    """
    try:
        queue = get_queue()
        job = queue.enqueue(
            "app.worker.process_image",
            image_id,
            retry=Retry(max=1),
            job_timeout=300,          # 5-minute hard limit per job
        )
        logger.info("Enqueued analysis job %s for image %s", job.id, image_id)
        return job.id
    except Exception as exc:
        logger.error("Failed to enqueue job for image %s: %s", image_id, exc)
        return None
