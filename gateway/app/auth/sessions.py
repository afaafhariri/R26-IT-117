"""Server-side sessions held in an HttpOnly cookie.

The cookie carries only a random ID. Everything else (who, until when) lives
in the `sessions` table, so a session can be ended instantly by deleting its
row: on logout, on password reset, or when it expires.
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from fastapi import HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import hash_token, new_token
from app.config import Settings
from app.db import utcnow
from app.models import User, UserSession


@dataclass(frozen=True)
class Lifetime:
    idle: timedelta
    absolute: timedelta


DEFAULT = Lifetime(idle=timedelta(hours=2), absolute=timedelta(hours=12))
REMEMBER_ME = Lifetime(idle=timedelta(days=7), absolute=timedelta(days=30))

# Extending the idle timeout on every request would mean a database write per
# API call; once a minute is precise enough.
TOUCH_INTERVAL = timedelta(minutes=1)


def cookie_name(settings: Settings) -> str:
    # The __Host- prefix makes the browser refuse the cookie unless it is
    # Secure, has Path=/ and no Domain, so no subdomain can set or read it.
    # It requires Secure, so local HTTP development uses a plain name.
    return "__Host-session" if settings.cookie_secure else "session"


def set_session_cookie(response: Response, settings: Settings, raw: str, remember_me: bool) -> None:
    response.set_cookie(
        cookie_name(settings),
        raw,
        # Without "remember me" it is a browser-session cookie: gone when the
        # browser closes, as well as after the server-side timeouts.
        max_age=int(REMEMBER_ME.absolute.total_seconds()) if remember_me else None,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        cookie_name(settings),
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


async def create_session(
    db: AsyncSession, user_id: uuid.UUID, remember_me: bool, request: Request
) -> str:
    """Stores a new session and returns the raw ID for the cookie."""
    lifetime = REMEMBER_ME if remember_me else DEFAULT
    now = utcnow()
    raw, id_hash = new_token()
    db.add(
        UserSession(
            id_hash=id_hash,
            user_id=user_id,
            remember_me=remember_me,
            created_at=now,
            last_seen_at=now,
            idle_expires_at=now + lifetime.idle,
            absolute_expires_at=now + lifetime.absolute,
            ip=request.client.host if request.client else None,
            user_agent=(request.headers.get("user-agent") or "")[:512] or None,
        )
    )
    return raw


async def load_session(db: AsyncSession, raw: str) -> tuple[UserSession, User] | None:
    """The live session and its user, or None. Expired sessions are deleted."""
    row = (
        await db.execute(
            select(UserSession, User)
            .join(User, User.id == UserSession.user_id)
            .where(UserSession.id_hash == hash_token(raw))
        )
    ).first()
    if row is None:
        return None
    session, user = row

    now = utcnow()
    if now >= session.idle_expires_at or now >= session.absolute_expires_at:
        await db.delete(session)
        return None

    if now - session.last_seen_at >= TOUCH_INTERVAL:
        lifetime = REMEMBER_ME if session.remember_me else DEFAULT
        session.last_seen_at = now
        session.idle_expires_at = min(now + lifetime.idle, session.absolute_expires_at)
    return session, user


async def revoke_session(db: AsyncSession, raw: str) -> None:
    await db.execute(delete(UserSession).where(UserSession.id_hash == hash_token(raw)))


async def revoke_all_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(delete(UserSession).where(UserSession.user_id == user_id))


async def require_user(request: Request) -> User:
    """Dependency: the signed-in user, or 401.

    Opens its own short-lived database session instead of using get_db, so a
    proxied request doesn't hold a pooled connection while the service works.
    """
    settings: Settings = request.app.state.settings
    raw = request.cookies.get(cookie_name(settings))
    loaded = None
    if raw:
        async with request.app.state.db() as db:
            loaded = await load_session(db, raw)
            await db.commit()
    if loaded is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in.")
    return loaded[1]
