from fastapi import APIRouter, Request, HTTPException
from models.chat import ChatMessageRequest, ChatResponse, ResponseType

from openai import OpenAI
openai_api_key = "sk-api-key"
OPENAI_BASE_URL="https://api.i2-core.american-science-cloud.org/v1"
model = "gpt-oss-120b"

options = [
    "Design a Rankine cycle based power generation system for a Sodium Fast Reactor. Core power rating is 390 MW, turbine output is 170.9 MW",
    "Run FTL Safety Analysis",
]

router = APIRouter(
    prefix="/api",
    tags=["chat"]
)


# ============================================================================
# Chat Endpoints
# ============================================================================
@router.post("/chat", response_model=ChatResponse)
async def chat(request_body: ChatMessageRequest, request: Request):
    """
    Main chat endpoint - routes to direct response or workflow trigger
    """

    if request_body.message in options:
        # Workflow Triggered response
        response = ChatResponse(
            type="workflow",
            session_id="tmp",
            workflow_id="wf_a7b3c9d2-4e5f-6a1b-8c9d-0e1f2a3b4c5d",
            workflow_type="research_and_report",
            status="queued",
            response=f"You trigger a workflow! Workflow: {request_body.message}",
            estimated_duration="8-12 minutes",
            polling_url="/api/workflows/wf_a7b3c9d2-4e5f-6a1b-8c9d-0e1f2a3b4c5d/status"
        )
    elif request_body.message in ['fmea']:
        # Workflow Triggered response
        response = ChatResponse(
            type=ResponseType.FMEA_WORKFLOW,
            session_id="tmp",
            workflow_id="wf_fmea",
            workflow_type="research_and_report",
            status="queued",
            response=f"You trigger a workflow! Workflow: {request_body.message}",
            estimated_duration="8-12 minutes",
            polling_url="/api/workflows/wf_fmea"
        )
    else:
        try:
            client = OpenAI(
                api_key=openai_api_key,
                base_url=OPENAI_BASE_URL
            )
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": f"You are prometheus, a nuclear reactor system assistant. Your job is the help the user with their requests. You are friendly and professional. You can make small talk but keep it on the topic of designing nuclear reactor systems. Be short and concise with your responses. REQUEST: {request_body.message}"
                    }
                ]
            )
            llm_response = completion.choices[0].message.content
        except Exception:
            llm_response = "I'm sorry, I'm unable to process your request right now. Please try again later."
        
        response = ChatResponse(
            type=ResponseType.CHAT,
            session_id="tmp",
            response=llm_response,
            stream=False
        )

    return response
