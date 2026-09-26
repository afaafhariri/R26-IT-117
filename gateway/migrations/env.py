"""Alembic environment. The database URL comes from the gateway's settings
(DATABASE_URL), never from alembic.ini, so credentials live in one place."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import load_settings
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Tests migrate a throwaway schema. Its version table must live there
        # too: left unqualified, Alembic would find public.alembic_version via
        # the search_path, decide nothing needs creating, and the tests would
        # then run against the real tables.
        version_table_schema=config.attributes.get("version_table_schema"),
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(load_settings().database_url, poolclass=pool.NullPool)

    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await engine.dispose()


# Tests pass in an open connection whose search_path points at a throwaway
# schema; everything else connects with DATABASE_URL.
connection = config.attributes.get("connection")
if connection is not None:
    do_run_migrations(connection)
else:
    asyncio.run(run_async_migrations())
