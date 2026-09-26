import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import Settings, load_settings
from app.email import Email
from app.main import create_app
from app.models import Base

GATEWAY_DIR = Path(__file__).resolve().parents[1]

SERVICES = {
    "c01": "http://c01.test",
    "c02": "http://c02.test",
    "c03": "http://c03.test/base",
    "c04": "http://c04.test",
}

APP_URL = "https://planner.test"


class FakeServices:
    """Stands in for C01–C04: records what the gateway forwards, replies as told."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.bodies: list[bytes] = []
        self.reply = lambda request: httpx.Response(200, json={"ok": True})

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.bodies.append(await request.aread())
        self.requests.append(request)
        reply = self.reply(request)
        # httpx.Response(json=...) reads its body up front; a real service's
        # response arrives unread, which is what the gateway streams from. The
        # raw (still encoded) bytes come from .stream, not the decoded .content.
        raw = b"".join(reply.stream)
        return httpx.Response(
            reply.status_code, headers=reply.headers, stream=httpx.ByteStream(raw)
        )


class FakeEmail:
    """Records outgoing email instead of sending it."""

    def __init__(self):
        self.sent: list[Email] = []

    async def send(self, email: Email) -> None:
        self.sent.append(email)

    def link_token(self, index: int = -1) -> str:
        """The token from the link in a sent email (the last one by default)."""
        match = re.search(r"#token=([A-Za-z0-9_-]+)", self.sent[index].text)
        assert match, f"no link in: {self.sent[index].text}"
        return match.group(1)


@pytest.fixture(scope="session")
def test_schema():
    """A throwaway schema in authdb, built by the real migrations.

    Everything the tests create lives here, and the schema is dropped at the
    end, so the development data in authdb's public schema is never touched.
    public stays on the search_path only because the citext type lives there.
    """
    base = load_settings().database_url
    if not base:
        pytest.skip("DATABASE_URL is not set (see gateway/.env.example)")

    schema = f"pytest_{uuid.uuid4().hex[:8]}"
    engine = create_engine(base)
    with engine.begin() as conn:
        # Left behind by an interrupted run.
        leftovers = conn.execute(
            text("SELECT nspname FROM pg_namespace WHERE nspname LIKE 'pytest\\_%'")
        ).scalars()
        for old in list(leftovers):
            conn.execute(text(f'DROP SCHEMA "{old}" CASCADE'))
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        conn.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
        config = Config(str(GATEWAY_DIR / "alembic.ini"))
        config.attributes["connection"] = conn
        config.attributes["version_table_schema"] = schema
        command.upgrade(config, "head")

        # Any table missing here would silently resolve to public's copy via
        # the search_path, so refuse to run rather than risk the real data.
        created = set(
            conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema = :s"),
                {"s": schema},
            ).scalars()
        )
        missing = set(Base.metadata.tables) - created
        assert not missing, f"migrations did not create {sorted(missing)} in {schema}"

    yield schema

    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    engine.dispose()


@pytest.fixture(scope="session")
def database_url(test_schema):
    """DATABASE_URL with its search_path pointed at the test schema."""
    return (
        make_url(load_settings().database_url)
        .update_query_dict({"options": f"-csearch_path={test_schema},public"})
        .render_as_string(hide_password=False)
    )


@dataclass
class Harness:
    client: TestClient
    services: FakeServices
    email: FakeEmail
    database_url: str

    def sql(self, statement: str, **params):
        """Runs SQL against the test schema (to fast-forward clocks and the like)."""
        engine = create_engine(self.database_url)
        try:
            with engine.begin() as conn:
                result = conn.execute(text(statement), params)
                return result.all() if result.returns_rows else None
        finally:
            engine.dispose()


@pytest.fixture
def harness(test_schema, database_url):
    """A gateway with a clean database, fake services and a fake mailbox.

    Runs over https with Secure cookies, exactly as in production.
    """
    services = FakeServices()
    email = FakeEmail()
    settings = Settings(
        services=SERVICES,
        upstream_timeout_seconds=5,
        database_url=database_url,
        app_base_url=APP_URL,
        allowed_origins=frozenset({APP_URL}),
        cookie_secure=True,
    )
    app = create_app(settings, transport=httpx.MockTransport(services.handle), email_sender=email)
    with TestClient(app, base_url="https://testserver") as client:
        h = Harness(client, services, email, database_url)
        # Schema-qualified, so this can only ever empty the test schema.
        tables = ", ".join(f'"{test_schema}".{t}' for t in Base.metadata.tables)
        h.sql(f"TRUNCATE {tables} CASCADE")
        yield h
