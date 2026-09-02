import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (
    admin_users,
    artifacts,
    auth,
    chat,
    config,
    conversations,
    events,
    health,
    sessions,
    setup,
    uploads,
)
from app.services.events import EventBus
from app.sessions import SessionStore

_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def _run_admin_db_migrations() -> None:
    """Apply pending Alembic migrations against admin-db. Synchronous (Alembic's
    command API blocks); called via asyncio.to_thread from the lifespan below so
    it doesn't block the event loop during startup."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_ALEMBIC_INI))
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Fail fast on a misconfigured deploy: without a signing secret, issue_token
    # would raise a 500 on the first login rather than here. Crash on boot with an
    # actionable message instead. (Bare TestClient(app) does not run the lifespan,
    # so this never trips in the test suite.)
    if not settings.jwt_secret:
        raise RuntimeError(
            "jwt_secret is not configured: set BACKEND_JWT_SECRET or "
            "CHAINLIT_AUTH_SECRET (both are forwarded to the container in "
            "docker-compose.yml). Refusing to start with an empty signing key."
        )
    # Bring admin-db (local users, OIDC provider config, signing keys) up to the
    # latest schema before serving any request. A single-replica backend, so
    # there's no concurrent-migration race to worry about; if this fails the
    # app refuses to start rather than serving against a stale/missing schema.
    await asyncio.to_thread(_run_admin_db_migrations)
    # In-memory session store — one per process, lost on restart (documented in
    # app/sessions.py).
    app.state.session_store = SessionStore()
    # In-process SSE fan-out bus. routers/chat.py publishes StatusEvents onto it;
    # routers/events.py drains it per connection. Each SSE connection owns its own
    # Redis subscriber, so no shared Redis connection is held here.
    app.state.event_bus = EventBus()
    yield


app = FastAPI(title="Prometheus Backend", lifespan=lifespan)

# CORS for local dev only; in prod the frontend is served same-origin behind nginx.
# Explicit origins, not "*", because credentialed requests can't use a wildcard
# Access-Control-Allow-Origin (AU-9). Configure via BACKEND_DEV_ORIGINS.
if settings.debug:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.dev_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(health.router)
app.include_router(setup.router)
app.include_router(auth.router)
app.include_router(config.router)
app.include_router(sessions.router)
app.include_router(chat.router)
app.include_router(events.router)
app.include_router(uploads.router)
app.include_router(artifacts.router)
app.include_router(conversations.router)
app.include_router(admin_users.router)
