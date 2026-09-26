"""R26-IT-117 API gateway.

The single public entry point. The planner UI talks only to this service:
/api/auth/* handles sign-up, login and sessions, and everything else under
/api/<service>/ is proxied to C01–C04, which sit on the internal network.
Every proxied request needs a signed-in session.
"""

import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI

from app.auth.guards import check_origin
from app.auth.router import router as auth_router
from app.auth.sessions import require_user
from app.config import Settings, load_settings
from app.db import create_engine, make_sessionmaker
from app.email import EmailSender, make_sender
from app.maintenance import run_cleanup_forever
from app.proxy import router as proxy_router


def create_app(
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    email_sender: EmailSender | None = None,
) -> FastAPI:
    """Builds the app. Tests pass a fake `transport` in place of the real
    services and a fake `email_sender` that records what would be sent."""
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_engine(settings.database_url)
        app.state.db = make_sessionmaker(engine)
        # One pooled client for every proxied request. Redirects are passed
        # back to the browser rather than followed here.
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.upstream_timeout_seconds, connect=5.0),
            follow_redirects=False,
            transport=transport,
        ) as client:
            app.state.http = client
            app.state.email = email_sender or make_sender(settings, client)
            cleanup = asyncio.create_task(run_cleanup_forever(app.state.db))
            try:
                yield
            finally:
                cleanup.cancel()
                await engine.dispose()

    app = FastAPI(title="R26-IT-117 Gateway", version="0.2.0", lifespan=lifespan)
    app.state.settings = settings

    @app.get("/health", tags=["System"])
    async def health():
        return {"status": "healthy", "component": "gateway"}

    # Registered before the proxy so /api/auth/* is never mistaken for a service.
    app.include_router(auth_router)
    app.include_router(
        proxy_router, dependencies=[Depends(check_origin), Depends(require_user)]
    )
    return app


app = create_app()
