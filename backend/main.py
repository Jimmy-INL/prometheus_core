from fastapi import FastAPI

from routers import agents, chat, demo_workflow, demo, info, workflows


app = FastAPI(title="Workflow Orchestration API")
# app.include_router(agents.router)
# app.include_router(approvals.router)
app.include_router(chat.router)
# app.include_router(info.router)
app.include_router(demo.router)
app.include_router(demo_workflow.router)
# app.include_router(workflows.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
