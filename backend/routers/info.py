from fastapi import APIRouter

router = APIRouter(
    prefix="/info",
    tags=["info"]
)


@router.get("/health")
async def health_check():
    """
    Health check endpoint
    """
    return {"status": "healthy"}


@router.get("/api/workflow-types")
async def list_workflow_types():
    """
    List all available workflow types
    """
    pass

@router.get("/")
def read_root():
    return {"Hello": "World"}