import json
import os
import socket
import uuid
from typing import Any, Awaitable, Callable, cast

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


def _setup_tracing(agent_name: str) -> TracerProvider:
    mlflow_tracking_uri = os.getenv("MLFLOW_URL", "https://mlflow.american-science-cloud.org")
    mlflow_experiment_id = os.getenv("MLFLOW_EXPERIMENT_ID", "20")

    resource = Resource.create(
        {
            "service.name": f"Prometheus-A2A-{agent_name}",
            "service.version": "1.0",
            "deployment.environment": os.getenv("ENV", "dev"),
            "host.name": socket.gethostname(),
            "mlflow.experiment_id": mlflow_experiment_id,
        }
    )

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=f"{mlflow_tracking_uri}/v1/traces",
        headers={"x-mlflow-experiment-id": mlflow_experiment_id},
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return provider


class MLFlowTracingMiddleware(OpenTelemetryMiddleware):
    """ASGI/OpenTelemetry root-span middleware — sets up the tracer provider and
    enriches the root HTTP span with A2A metadata."""

    def __init__(self, app, agent_name: str):
        self._agent_name = agent_name
        provider = _setup_tracing(agent_name)

        def server_request_hook(span, scope):
            if not span or not span.is_recording():
                return
            path = scope.get("path", "")
            method = scope.get("method", "")
            span.update_name(f"A2A {method} {path}")
            span.set_attribute("a2a.receiver_agent", agent_name)
            span.set_attribute("a2a.correlation_id", str(uuid.uuid4()))

        super().__init__(app, tracer_provider=provider, server_request_hook=server_request_hook)


class A2APayloadTracingMiddleware(BaseHTTPMiddleware):
    """Reads request/response bodies for A2A endpoints and attaches them as
    span attributes on the active span created by MLFlowTracingMiddleware.

    Stack order matters — this must be added AFTER MLFlowTracingMiddleware so
    it executes INSIDE the OTel span:

        app.add_middleware(A2APayloadTracingMiddleware, max_body_bytes=8192)
        app.add_middleware(MLFlowTracingMiddleware, agent_name=self.agent_name)
    """

    # A2A endpoints that carry meaningful JSON-RPC payloads
    A2A_PATHS = {"/", "/a2a", "/tasks/send", "/tasks/sendSubscribe"}

    def __init__(self, app, max_body_bytes: int = 8192):
        super().__init__(app)
        self._max_bytes = max_body_bytes

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        span = trace.get_current_span()

        # Only instrument A2A JSON-RPC paths
        if request.url.path not in self.A2A_PATHS:
            return await call_next(request)

        # --- Capture request body ---
        raw_req = await request.body()
        req_text = raw_req[: self._max_bytes].decode("utf-8", errors="replace")
        if span.is_recording():
            span.set_attribute("a2a.request.body", req_text)
            try:
                parsed = json.loads(raw_req)
                # Pull out the most useful A2A/JSON-RPC fields
                span.set_attribute("a2a.jsonrpc.method", parsed.get("method", ""))
                task = parsed.get("params", {})
                if isinstance(task, dict):
                    span.set_attribute("a2a.task.id", task.get("id", ""))
                    # Capture the first user message text if present
                    messages = task.get("message", {}).get("parts", [])
                    if messages:
                        first_text = next(
                            (p.get("text", "") for p in messages if p.get("type") == "text"), ""
                        )
                        span.set_attribute("a2a.input.text", first_text[: self._max_bytes])
            except (json.JSONDecodeError, AttributeError):
                pass

        # Starlette requires re-injecting the body since it's a stream
        async def receive():
            return {"type": "http.request", "body": raw_req, "more_body": False}

        request = Request(request.scope, receive)

        # --- Capture response body ---
        response = await call_next(request)
        streaming_response = cast(Any, response)
        resp_chunks = []
        async for chunk in streaming_response.body_iterator:
            resp_chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode())

        raw_resp = b"".join(resp_chunks)
        resp_text = raw_resp[: self._max_bytes].decode("utf-8", errors="replace")

        if span.is_recording():
            span.set_attribute("a2a.response.body", resp_text)
            try:
                parsed_resp = json.loads(raw_resp)
                result = parsed_resp.get("result", {})
                if isinstance(result, dict):
                    # Capture agent output artifacts/messages
                    artifacts = result.get("artifacts", [])
                    if artifacts:
                        output_parts = artifacts[0].get("parts", [])
                        first_out = next(
                            (p.get("text", "") for p in output_parts if p.get("type") == "text"), ""
                        )
                        span.set_attribute("a2a.output.text", first_out[: self._max_bytes])
                    span.set_attribute("a2a.task.state", result.get("status", {}).get("state", ""))
            except (json.JSONDecodeError, AttributeError):
                pass

        return Response(
            content=raw_resp,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
