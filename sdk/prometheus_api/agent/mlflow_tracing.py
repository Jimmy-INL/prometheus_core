import os
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.starlette import StarletteInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

class MLFlowTracingMiddleware():

    def __init__(self, app):
        mlflow_tracking_uri = "https://mlflow.american-science-cloud.org"
        mlflow_experiment_id = "20"  # Must be numeric experiment ID, not name

        resource = Resource(
            attributes={
                "service.name": "Prometheus-test-integration",
                "service.version": "1.0",
            }
        )

        provider = TracerProvider(resource=resource)

        exporter = OTLPSpanExporter(
            endpoint=f"{mlflow_tracking_uri}/v1/traces",
            headers={"x-mlflow-experiment-id": mlflow_experiment_id},
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)

        StarletteInstrumentor().instrument_app(app)