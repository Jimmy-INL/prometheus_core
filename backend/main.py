from contextlib import asynccontextmanager

from fastapi import FastAPI

from routers import agents, approvals, chat, info, sessions, workflows, demo, demo_workflow
from state import SQLiteStateRepository


@asynccontextmanager
async def lifespan(app: FastAPI):
    repo = SQLiteStateRepository(db_path="data/prometheus.db")
    await repo.initialize()
    app.state.repo = repo
    yield
    await repo.close()


app = FastAPI(title="Workflow Orchestration API", lifespan=lifespan)
# app.include_router(agents.router)
# app.include_router(approvals.router)
app.include_router(chat.router)
# app.include_router(info.router)
app.include_router(sessions.router)
app.include_router(demo.router)
app.include_router(demo_workflow.router)
# app.include_router(workflows.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
