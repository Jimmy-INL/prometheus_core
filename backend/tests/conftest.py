import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from routers import chat, demo_workflow


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(chat.router)
    app.include_router(demo_workflow.router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
