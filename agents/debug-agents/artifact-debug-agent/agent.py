"""
Artifact Debug Agent.

Purpose:
- Produce deterministic test artifacts backed by DeepLynx so the full artifact
  plumbing — upload, deeplynx:// URI emission, frontend resolution — can be
  exercised end-to-end.
- Convert SVG artifacts into PNG artifacts by fetching from DeepLynx, converting
  locally, and re-uploading.

Primary users:
- Orchestrator skill routing (client-agent) when testing artifact-aware tool calls.
- Frontend developers validating deeplynx:// artifact link rendering and resolution.
"""

import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from xml.sax.saxutils import escape as xml_escape

from a2a.server.agent_execution.context import RequestContext
from a2a.server.events import EventQueue
from prometheus_api.agent import ArtifactReference, PrometheusAgent
from prometheus_api.storage_client.async_client import AsyncStorageClient
from prometheus_api.storage_client.connection import ConnectionConfig


def _try_storage_config() -> Optional[ConnectionConfig]:
    """Return a ConnectionConfig from env, or None if credentials are missing."""
    try:
        return ConnectionConfig.from_env()
    except ValueError:
        return None


class ArtifactDebugAgent(PrometheusAgent):
    """Debug-only producer/converter for session-scoped artifact references backed by DeepLynx."""

    @staticmethod
    def _sanitize_stem(value: str, fallback: str = "artifact") -> str:
        """Create a filesystem-safe stem for generated artifact names."""
        candidate = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
        candidate = candidate.strip("._-")
        return candidate or fallback

    @staticmethod
    def _normalize_dimension(raw: Any, default_value: int) -> int:
        """Normalize untrusted width/height values and clamp to sensible bounds."""
        try:
            parsed = int(float(str(raw)))
        except Exception:
            parsed = default_value
        return max(64, min(parsed, 4096))

    def _resolve_artifact_from_payload(
        self,
        conversation_id: str,
        artifact_id: str,
        params: Dict[str, Any],
    ) -> Optional[ArtifactReference]:
        """Resolve an artifact from local registry or orchestrator-provided catalog."""
        source_ref = self.resolve_artifact_reference(conversation_id, artifact_id)
        if source_ref:
            return source_ref

        for artifact in params.get("artifacts") or []:
            if not isinstance(artifact, dict):
                continue
            candidate_id = str(
                artifact.get("artifact_id")
                or artifact.get("artifactId")
                or artifact.get("id")
                or ""
            ).strip()
            if candidate_id != artifact_id:
                continue
            try:
                source_ref = ArtifactReference.from_any(
                    artifact,
                    conversation_id=conversation_id,
                )
            except Exception:
                source_ref = None
            if source_ref:
                try:
                    self.artifact_registry.register(source_ref)
                except Exception as exc:
                    print(f"[WARN] Failed to cache artifact reference {artifact_id}: {exc}")
                return source_ref

        return None

    @staticmethod
    def _convert_svg_to_png(source_svg: Path, target_png: Path) -> str:
        """Convert SVG to PNG with CairoSVG."""
        try:
            import cairosvg  # type: ignore

            cairosvg.svg2png(url=str(source_svg), write_to=str(target_png))
        except Exception as exc:
            raise RuntimeError(f"CairoSVG failed to convert SVG to PNG: {exc}") from exc

        if not target_png.exists() or target_png.stat().st_size == 0:
            raise RuntimeError("CairoSVG did not produce a PNG file.")
        return "cairosvg"

    async def _handle_create_svg(
        self,
        params: Dict[str, Any],
        conversation_id: str,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> Dict[str, Any]:
        """Create an SVG artifact, upload to DeepLynx, and emit a deeplynx:// reference."""
        storage_config = _try_storage_config()
        if storage_config is None:
            return {
                "status": "error",
                "conversation_id": conversation_id,
                "message": "DEEPLYNX_* credentials not configured.",
            }

        word = str(params.get("word") or params.get("text") or "").strip()
        if not word:
            return {
                "status": "error",
                "conversation_id": conversation_id,
                "message": "Parameter 'word' is required to create an SVG artifact.",
            }

        width = self._normalize_dimension(params.get("width", 512), 512)
        height = self._normalize_dimension(params.get("height", 512), 512)
        background = str(params.get("background") or params.get("background_color") or "#f8fafc")
        text_color = str(params.get("color") or params.get("text_color") or "#0f172a")

        requested_name = str(params.get("name") or "").strip()
        stem = self._sanitize_stem(
            Path(requested_name).stem if requested_name else word.lower(),
            fallback="debug_svg",
        )
        file_name = f"{stem}.svg"
        description = str(params.get("description") or f"Debug SVG containing the word '{word}'.")

        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message=f"Creating SVG artifact '{file_name}'.",
        )

        escaped_word = xml_escape(word)
        svg_content = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"'
            f' viewBox="0 0 {width} {height}">'
            f'<rect width="100%" height="100%" fill="{xml_escape(background)}" />'
            f'<text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle"'
            f' fill="{xml_escape(text_color)}" font-size="48"'
            f' font-family="sans-serif">{escaped_word}</text>'
            "</svg>"
        )

        with tempfile.TemporaryDirectory() as tmp:
            svg_path = Path(tmp) / file_name
            svg_path.write_text(svg_content, encoding="utf-8")

            await self.send_status_update(
                context=context,
                event_queue=event_queue,
                message="Uploading SVG to DeepLynx.",
            )

            artifact_ref = await self.send_deeplynx_artifact(
                context=context,
                event_queue=event_queue,
                file_path=svg_path,
                name=file_name,
                description=description,
                storage_config=storage_config,
                mime_type="image/svg+xml",
                json_type="prometheus.debug.svg.v1",
                tags=["debug", "svg"],
                metadata={"word": word},
            )

        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message=f"Created SVG artifact {artifact_ref.artifact_id}.",
        )
        await self.send_conversation_message(
            context=context,
            event_queue=event_queue,
            message="SVG artifact created successfully.",
            metadata={"artifact_id": artifact_ref.artifact_id},
        )

        return {
            "status": "created",
            "conversation_id": conversation_id,
            "message": "SVG artifact created successfully.",
            "artifact": artifact_ref.to_dict(),
            "artifact_id": artifact_ref.artifact_id,
            "artifact_name": artifact_ref.name,
            "artifact_uri": artifact_ref.uri,
        }

    async def _handle_convert_svg_to_png(
        self,
        params: Dict[str, Any],
        conversation_id: str,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> Dict[str, Any]:
        """Fetch an SVG artifact from DeepLynx, convert to PNG, and upload the result."""
        storage_config = _try_storage_config()
        if storage_config is None:
            return {
                "status": "error",
                "conversation_id": conversation_id,
                "message": "DEEPLYNX_* credentials not configured.",
            }

        artifact_id = str(params.get("artifact_id") or "").strip()
        if not artifact_id:
            upstream = params.get("upstream_results") or {}
            for skill_result in upstream.values():
                if isinstance(skill_result, dict):
                    candidate = (
                        skill_result.get("artifact_id")
                        or (skill_result.get("artifact") or {}).get("artifact_id")
                        or ""
                    )
                    if candidate:
                        artifact_id = str(candidate)
                        break
        if not artifact_id:
            return {
                "status": "error",
                "conversation_id": conversation_id,
                "message": "Parameter 'artifact_id' is required for SVG to PNG conversion.",
            }

        source_ref = self._resolve_artifact_from_payload(
            conversation_id=conversation_id,
            artifact_id=artifact_id,
            params=params,
        )
        if not source_ref:
            return {
                "status": "error",
                "conversation_id": conversation_id,
                "message": f"Artifact '{artifact_id}' was not found in this conversation.",
            }

        source_dict = source_ref.to_dict()
        if Path(source_ref.name).suffix.lower() != ".svg":
            return {
                "status": "error",
                "conversation_id": conversation_id,
                "message": f"Artifact '{artifact_id}' is not an SVG file.",
                "source_artifact": source_dict,
            }

        file_id = source_ref.metadata.get("deeplynx_file_id")
        if not file_id:
            return {
                "status": "error",
                "conversation_id": conversation_id,
                "message": "Source artifact is missing 'deeplynx_file_id' metadata; cannot download.",
                "source_artifact": source_dict,
            }

        requested_name = str(params.get("name") or "").strip()
        base_stem = self._sanitize_stem(
            Path(requested_name).stem if requested_name else Path(source_ref.name).stem,
            fallback="converted",
        )
        description = str(
            params.get("description")
            or f"PNG converted from SVG artifact '{source_ref.name}'."
        )

        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message=f"Downloading SVG artifact '{source_ref.name}' from DeepLynx.",
        )

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            svg_path = tmp_path / source_ref.name
            png_name = f"{base_stem}.png"
            png_path = tmp_path / png_name

            async with AsyncStorageClient(storage_config) as client:
                await client.files.download(int(file_id), svg_path)

            await self.send_status_update(
                context=context,
                event_queue=event_queue,
                message=f"Converting artifact '{source_ref.name}' to PNG.",
            )

            try:
                conversion_backend = self._convert_svg_to_png(svg_path, png_path)
            except Exception as exc:
                return {
                    "status": "error",
                    "conversation_id": conversation_id,
                    "message": f"Failed to convert SVG artifact '{source_ref.name}' to PNG: {exc}",
                    "source_artifact": source_dict,
                }

            await self.send_status_update(
                context=context,
                event_queue=event_queue,
                message="Uploading PNG to DeepLynx.",
            )

            output_ref = await self.send_deeplynx_artifact(
                context=context,
                event_queue=event_queue,
                file_path=png_path,
                name=png_name,
                description=description,
                storage_config=storage_config,
                mime_type="image/png",
                tags=["debug", "png", "converted"],
                metadata={
                    "source_artifact_id": source_ref.artifact_id,
                    "conversion_backend": conversion_backend,
                },
            )

        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message=f"Created PNG artifact {output_ref.artifact_id}.",
        )
        await self.send_conversation_message(
            context=context,
            event_queue=event_queue,
            message="SVG artifact converted to PNG successfully.",
            metadata={"artifact_id": output_ref.artifact_id},
        )

        return {
            "status": "converted",
            "conversation_id": conversation_id,
            "message": "SVG artifact converted to PNG successfully.",
            "source_artifact": source_dict,
            "artifact": output_ref.to_dict(),
            "artifact_id": output_ref.artifact_id,
            "artifact_name": output_ref.name,
            "artifact_uri": output_ref.uri,
        }

    async def _handle_create_json_artifact(
        self,
        params: Dict[str, Any],
        conversation_id: str,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> Dict[str, Any]:
        """Create an inline JSON artifact with an explicit json_type."""
        json_type = str(params.get("json_type") or "").strip()
        if not json_type:
            return {
                "status": "error",
                "conversation_id": conversation_id,
                "message": "Parameter 'json_type' is required to create a JSON artifact.",
            }

        payload = params.get("payload")
        if payload is None:
            payload = {
                "message": "Debug JSON artifact",
                "requested_json_type": json_type,
            }
        if not isinstance(payload, dict):
            return {
                "status": "error",
                "conversation_id": conversation_id,
                "message": "Parameter 'payload' must be a JSON object.",
            }

        name = str(params.get("name") or "debug_json_artifact").strip() or "debug_json_artifact"
        description = str(params.get("description") or f"Debug JSON artifact for '{json_type}'.")

        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message=f"Creating JSON artifact '{name}'.",
        )

        artifact_ref = self.artifact_registry.register(
            ArtifactReference(
                artifact_id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                name=name,
                description=description,
                mime_type="application/json",
                json_type=json_type,
                json_body=payload,
                producer_agent_id=self._producer_agent_id,
                metadata={"debug": True},
            )
        )
        artifact_id = artifact_ref.artifact_id
        await self.send_json_artifact(
            context=context,
            event_queue=event_queue,
            payload=payload,
            name=name,
            description=description,
            json_type=json_type,
            artifact_id=artifact_id,
            metadata={"debug": True, "json_type": json_type},
        )
        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message=f"Created JSON artifact {artifact_id}.",
        )
        await self.send_conversation_message(
            context=context,
            event_queue=event_queue,
            message="JSON artifact created successfully.",
            metadata={"artifact_id": artifact_id, "json_type": json_type},
        )

        return {
            "status": "created",
            "conversation_id": conversation_id,
            "message": "JSON artifact created successfully.",
            "artifact": artifact_ref.to_dict(),
            "artifact_id": artifact_id,
            "json_type": json_type,
        }

    async def _execute(
        self,
        params: Dict[str, Any],
        context: RequestContext,
        event_queue: EventQueue,
    ) -> Dict[str, Any]:
        """Dispatch artifact debug operations based on required skill parameters."""
        conversation_id = str(params.get("conversation_id") or context.context_id or str(uuid.uuid4()))

        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message="Parsing artifact debug request.",
        )

        if params.get("json_type") or params.get("payload") is not None:
            return await self._handle_create_json_artifact(
                params=params,
                conversation_id=conversation_id,
                context=context,
                event_queue=event_queue,
            )

        if params.get("artifact_id"):
            return await self._handle_convert_svg_to_png(
                params=params,
                conversation_id=conversation_id,
                context=context,
                event_queue=event_queue,
            )

        return await self._handle_create_svg(
            params=params,
            conversation_id=conversation_id,
            context=context,
            event_queue=event_queue,
        )


if __name__ == "__main__":
    agent = ArtifactDebugAgent(agent_name="Artifact Debug Agent")
    agent.run(port=int(os.getenv("AGENT_PORT", "8000")))
