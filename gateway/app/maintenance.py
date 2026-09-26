"""Hourly clean-up of auth rows that can never be used again."""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import delete, or_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import utcnow
from app.models import EmailToken, RateLimit, UserSession

logger = logging.getLogger("gateway.maintenance")

CLEANUP_INTERVAL = timedelta(hours=1)


async def cleanup_expired(db: AsyncSession) -> None:
    now = utcnow()
    await db.execute(
        delete(UserSession).where(
            or_(UserSession.idle_expires_at <= now, UserSession.absolute_expires_at <= now)
        )
    )
    await db.execute(
        delete(EmailToken).where(or_(EmailToken.expires_at <= now, EmailToken.used_at.is_not(None)))
    )
    await db.execute(delete(RateLimit).where(RateLimit.window_start <= now - timedelta(days=1)))


async def run_cleanup_forever(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL.total_seconds())
        try:
            async with sessionmaker() as db:
                await cleanup_expired(db)
                await db.commit()
        except Exception:
            logger.exception("Clean-up of expired auth rows failed")
