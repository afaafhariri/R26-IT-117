"""Random tokens for session cookies and email links.

The raw token only ever exists in the cookie or the emailed link; the
database stores its SHA-256. A 256-bit random value can't be brute-forced, so
a fast hash is enough here (unlike passwords).
"""

import hashlib
import secrets
import uuid
from datetime import timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import utcnow
from app.models import EmailToken

VERIFY_EMAIL = "verify_email"
RESET_PASSWORD = "reset_password"

TOKEN_LIFETIMES = {
    VERIFY_EMAIL: timedelta(hours=24),
    RESET_PASSWORD: timedelta(minutes=30),
}


def new_token() -> tuple[str, str]:
    """Returns (raw token, its hash)."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def issue_email_token(db: AsyncSession, user_id: uuid.UUID, purpose: str) -> str:
    """Creates a link token and returns the raw value to put in the email.

    Any earlier unused token for the same purpose stops working, so only the
    most recent email's link is valid.
    """
    now = utcnow()
    await db.execute(
        update(EmailToken)
        .where(
            EmailToken.user_id == user_id,
            EmailToken.purpose == purpose,
            EmailToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw, token_hash = new_token()
    db.add(
        EmailToken(
            token_hash=token_hash,
            user_id=user_id,
            purpose=purpose,
            created_at=now,
            expires_at=now + TOKEN_LIFETIMES[purpose],
        )
    )
    return raw


async def peek_email_token(db: AsyncSession, raw: str, purpose: str) -> EmailToken | None:
    """The token if it is still usable, without using it up."""
    token = await db.get(EmailToken, hash_token(raw))
    if (
        token is None
        or token.purpose != purpose
        or token.used_at is not None
        or token.expires_at <= utcnow()
    ):
        return None
    return token


async def consume_email_token(db: AsyncSession, raw: str, purpose: str) -> uuid.UUID | None:
    """Uses the token up and returns its user, or None if it isn't valid.

    One conditional UPDATE, so two simultaneous clicks can't both succeed.
    """
    now = utcnow()
    result = await db.execute(
        update(EmailToken)
        .where(
            EmailToken.token_hash == hash_token(raw),
            EmailToken.purpose == purpose,
            EmailToken.used_at.is_(None),
            EmailToken.expires_at > now,
        )
        .values(used_at=now)
        .returning(EmailToken.user_id)
    )
    return result.scalar_one_or_none()
