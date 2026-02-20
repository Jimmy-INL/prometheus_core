import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from routers import chat, sessions
from state import SQLiteStateRepository


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(chat.router)
    app.include_router(sessions.router)

    repo = SQLiteStateRepository(db_path=":memory:")
    await repo.initialize()
    app.state.repo = repo

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await repo.close()
