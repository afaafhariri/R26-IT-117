"""Redis-based rate limiter for Veo video generation (1 video per hour globally)."""

import os

import redis

from utils.logger import get_logger

_logger = get_logger("video_rate_limiter")

_RATE_LIMIT_KEY = "video_rate_limit_global"
_TTL_SECONDS = int(os.getenv("VIDEO_RATE_LIMIT_HOURS", "1")) * 3600


def _get_redis() -> redis.Redis:
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return redis.from_url(url, decode_responses=True)


def check_and_set_rate_limit() -> tuple[bool, int]:
    """Check whether a video can be generated right now.

    Sets the rate-limit key on first use (TTL = 1 hour).

    Returns:
        (is_allowed, minutes_remaining)
        is_allowed=True means the caller may proceed.
        minutes_remaining is meaningful only when is_allowed=False.
    """
    try:
        r = _get_redis()
        ttl = r.ttl(_RATE_LIMIT_KEY)

        if ttl > 0:
            minutes_remaining = (ttl + 59) // 60
            _logger.info("Video rate limit active — %d minutes remaining", minutes_remaining)
            return False, minutes_remaining

        # Key absent (ttl == -2) or expired — allow and set lock
        r.set(_RATE_LIMIT_KEY, "1", ex=_TTL_SECONDS)
        _logger.info("Video rate limit key set (TTL=%ds)", _TTL_SECONDS)
        return True, 0

    except Exception as exc:
        # If Redis is unreachable, allow the call rather than blocking all video generation
        _logger.warning("Rate limiter Redis error — allowing video: %s", exc)
        return True, 0
