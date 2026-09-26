"""Request guards shared by the auth endpoints and the proxy: the CSRF check
and rate limiting."""

import hashlib
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import utcnow
from app.models import RateLimit

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


async def check_origin(request: Request) -> None:
    """Dependency: rejects state-changing requests sent from another site.

    The session cookie is SameSite=Lax, which already stops most cross-site
    POSTs from carrying it. This is the second layer: browsers label every
    request with where it came from (Sec-Fetch-Site, or Origin in older
    ones), and anything not from our own origin is refused. A request with
    neither header isn't from a browser, so it can't be a CSRF attack.
    """
    if request.method in _SAFE_METHODS:
        return

    site = request.headers.get("sec-fetch-site")
    if site is not None:
        if site == "same-origin":
            return
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-site request blocked.")

    origin = request.headers.get("origin")
    if origin is not None and origin not in request.app.state.settings.allowed_origins:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-site request blocked.")


def client_ip(request: Request) -> str:
    # In production, run uvicorn with --proxy-headers and
    # --forwarded-allow-ips set to the load balancer, or every request will
    # appear to come from the load balancer's address.
    return request.client.host if request.client else "unknown"


async def hit(db: AsyncSession, key: str, limit: int, window: timedelta) -> int | None:
    """Counts one attempt against `key`.

    Returns how many seconds to wait if the limit for the current window is
    exceeded, otherwise None. The caller commits, so the count survives even
    when the request itself then fails.
    """
    now = utcnow()
    seconds = window.total_seconds()
    window_start = datetime.fromtimestamp(now.timestamp() // seconds * seconds, UTC)
    key_hash = hashlib.sha256(key.encode()).hexdigest()

    count = (
        await db.execute(
            insert(RateLimit)
            .values(key=key_hash, window_start=window_start, count=1)
            .on_conflict_do_update(
                index_elements=[RateLimit.key, RateLimit.window_start],
                set_={"count": RateLimit.count + 1},
            )
            .returning(RateLimit.count)
        )
    ).scalar_one()

    if count <= limit:
        return None
    return int((window_start + window - now).total_seconds()) + 1


def too_many_attempts(retry_after: int) -> HTTPException:
    minutes = max(1, round(retry_after / 60))
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        f"Too many attempts. Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
        headers={"Retry-After": str(retry_after)},
    )
