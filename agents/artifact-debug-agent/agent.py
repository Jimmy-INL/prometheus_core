"""
Artifact Debug Agent.

Purpose:
- Produce deterministic test artifacts so artifact plumbing can be exercised end-to-end.
- Convert SVG artifacts into PNG artifacts without exposing raw file bytes to the LLM context.

Primary users:
- Orchestrator skill routing (`client-agent`) when testing artifact-aware tool calls.
- Frontend developers validating artifact link rendering and session-scoped artifact catalogs.
"""

import os
import re
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import unquote, urlparse
from xml.sax.saxutils import escape as xml_escape

from PIL import Image, ImageDraw, ImageFont
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events import EventQueue
from prometheus_api.agent import ArtifactReference, PrometheusAgent
from starlette.responses import FileResponse, JSONResponse


class ArtifactDebugAgent(PrometheusAgent):
    """Debug-only producer/converter for session-scoped artifact references."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.artifact_root = Path(os.getenv("SHARED_ARTIFACT_DIR", "/app/shared/artifact-debug"))
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    @property
    def public_base_url(self) -> str:
        """Base URL used when writing clickable artifact URIs for UI clients."""
        explicit = (os.getenv("AGENT_PUBLIC_URL") or "").strip().rstrip("/")
        if explicit:
            return explicit

        host = (os.getenv("AGENT_HOST") or "localhost").strip()
        port = (os.getenv("AGENT_PORT") or "8000").strip()
        return f"http://{host}:{port}".rstrip("/")

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

    def _conversation_dir(self, conversation_id: str) -> Path:
        """Session-scoped storage so artifacts can be traced and reused per conversation."""
        safe_conv = self._sanitize_stem(conversation_id, fallback=str(uuid.uuid4()))
        conv_dir = self.artifact_root / safe_conv
        conv_dir.mkdir(parents=True, exist_ok=True)
        return conv_dir

    @staticmethod
    def _unique_path(directory: Path, desired_filename: str) -> Path:
        """Return a non-colliding path by appending numeric suffixes when needed."""
        target = directory / desired_filename
        if not target.exists():
            return target

        stem = Path(desired_filename).stem
        suffix = Path(desired_filename).suffix
        for idx in range(2, 10000):
            candidate = directory / f"{stem}_{idx}{suffix}"
            if not candidate.exists():
                return candidate
        raise RuntimeError("Unable to allocate a unique artifact filename")

    def _artifact_uri_for_path(self, artifact_path: Path) -> str:
        """Build a UI-clickable URI for a file inside this agent's artifact store."""
        relative = artifact_path.relative_to(self.artifact_root).as_posix()
        return f"{self.public_base_url}/artifacts/{relative}"

    async def _register_reference_for_conversation(
        self,
        *,
        conversation_id: str,
        name: str,
        description: str,
        uri: str,
        context: RequestContext,
        event_queue: EventQueue,
        mime_type: Optional[str] = None,
        size_bytes: Optional[int] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ArtifactReference:
        """Register artifact metadata under the explicit request conversation_id.

        Why this exists:
        A2A `context_id` and user-level `conversation_id` can differ depending on caller.
        This helper ensures references are keyed by the conversation used for follow-up
        requests and artifact parameter resolution.
        """
        reference = ArtifactReference(
            artifact_id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            name=name,
            description=description,
            uri=uri,
            mime_type=mime_type,
            size_bytes=size_bytes,
            producer_agent_id=self.agent_name.lower().replace(" ", "-"),
            tags=list(tags or []),
            metadata=dict(metadata or {}),
        )
        registered = self.artifact_registry.register(reference)
        await self.send_json_artifact(
            context=context,
            event_queue=event_queue,
            payload={"artifact": registered.to_dict()},
            name="artifact_reference",
            metadata={"kind": "artifact_reference", **dict(metadata or {})},
        )
        return registered

    def _resolve_local_path(self, reference: Dict[str, Any]) -> Optional[Path]:
        """Resolve a registered artifact reference back to a local filesystem path.

        Used by conversion workflows that accept `artifact_id` rather than raw content.
        """
        metadata = reference.get("metadata") if isinstance(reference, dict) else None
        if isinstance(metadata, dict):
            local_path = metadata.get("local_path")
            if isinstance(local_path, str) and local_path.strip():
                path = Path(local_path).expanduser().resolve()
                if path.exists():
                    return path

        uri = str(reference.get("uri") or "").strip()
        if not uri:
            return None

        if uri.startswith("file://"):
            file_path = Path(uri[7:]).expanduser().resolve()
            return file_path if file_path.exists() else None

        parsed = urlparse(uri)
        path = unquote(parsed.path or "")
        marker = "/artifacts/"
        if marker not in path:
            return None

        relative = path.split(marker, 1)[1]
        candidate = (self.artifact_root / relative).resolve()
        root = self.artifact_root.resolve()
        if not str(candidate).startswith(f"{root}{os.sep}"):
            return None
        if candidate.exists():
            return candidate
        return None

    @staticmethod
    def _read_svg_payload(svg_path: Path) -> Dict[str, Any]:
        """Extract minimal rendering hints from SVG for fallback PNG conversion."""
        defaults: Dict[str, Any] = {
            "width": 512,
            "height": 512,
            "text": svg_path.stem,
            "background": "#ffffff",
            "text_color": "#1f2937",
        }

        try:
            tree = ET.parse(svg_path)
            root = tree.getroot()
            width_raw = root.attrib.get("width", defaults["width"])
            height_raw = root.attrib.get("height", defaults["height"])

            def parse_dim(value: Any, fallback: int) -> int:
                match = re.match(r"\s*(\d+(?:\.\d+)?)", str(value))
                if not match:
                    return fallback
                return max(64, min(int(float(match.group(1))), 4096))

            defaults["width"] = parse_dim(width_raw, defaults["width"])
            defaults["height"] = parse_dim(height_raw, defaults["height"])

            for element in root.iter():
                tag = element.tag.split("}")[-1]
                if tag == "rect" and element.attrib.get("fill"):
                    defaults["background"] = element.attrib.get("fill")
                if tag == "text":
                    text_value = "".join(element.itertext()).strip()
                    if text_value:
                        defaults["text"] = text_value
                    if element.attrib.get("fill"):
                        defaults["text_color"] = element.attrib.get("fill")
                    break
        except Exception:
            pass

        return defaults

    @staticmethod
    def _convert_svg_to_png_fallback(source_svg: Path, target_png: Path) -> str:
        """Fallback converter for debug SVGs when dedicated SVG renderers are unavailable."""
        payload = ArtifactDebugAgent._read_svg_payload(source_svg)
        image = Image.new("RGB", (payload["width"], payload["height"]), color=payload["background"])
        drawer = ImageDraw.Draw(image)
        font = ImageFont.load_default()

        text = str(payload["text"])
        text_bbox = drawer.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        x = (payload["width"] - text_width) // 2
        y = (payload["height"] - text_height) // 2

        drawer.text((x, y), text, fill=payload["text_color"], font=font)
        image.save(target_png, format="PNG")
        return "pillow-fallback"

    @staticmethod
    def _convert_svg_to_png(source_svg: Path, target_png: Path) -> str:
        """Convert SVG to PNG, preferring CairoSVG and falling back to PIL for debug SVGs."""
        try:
            import cairosvg  # type: ignore

            cairosvg.svg2png(url=str(source_svg), write_to=str(target_png))
            return "cairosvg"
        except Exception:
            return ArtifactDebugAgent._convert_svg_to_png_fallback(source_svg, target_png)

    async def _handle_create_svg(
        self,
        params: Dict[str, Any],
        conversation_id: str,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> Dict[str, Any]:
        """Create an SVG artifact with a user-provided word and register its metadata."""
        word = str(params.get("word") or params.get("text") or "").strip()
        if not word:
            return {
                "status": "error",
                "conversation_id": conversation_id,
                "message": "Parameter 'word' is required to create an SVG artifact.",
            }

        width = self._normalize_dimension(params.get("width", 512), 512)
        height = self._normalize_dimension(params.get("height", 512), 512)
        background = str(params.get("background") or "#f8fafc")
        text_color = str(params.get("color") or params.get("text_color") or "#0f172a")

        requested_name = str(params.get("name") or "").strip()
        if requested_name:
            stem = self._sanitize_stem(Path(requested_name).stem, fallback="debug_svg")
        else:
            stem = self._sanitize_stem(word.lower(), fallback="debug_svg")

        file_name = f"{stem}.svg"
        target_path = self._unique_path(self._conversation_dir(conversation_id), file_name)

        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message=f"Creating SVG artifact '{target_path.name}'.",
        )

        escaped_word = xml_escape(word)
        svg_content = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'  # noqa: E501
            f'<rect width="100%" height="100%" fill="{xml_escape(background)}" />'
            f'<text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" '
            f'fill="{xml_escape(text_color)}" font-size="48" font-family="sans-serif">{escaped_word}</text>'
            "</svg>"
        )
        target_path.write_text(svg_content, encoding="utf-8")

        description = str(params.get("description") or f"Debug SVG containing the word '{word}'.")
        artifact_ref = await self._register_reference_for_conversation(
            conversation_id=conversation_id,
            name=target_path.name,
            description=description,
            uri=self._artifact_uri_for_path(target_path),
            context=context,
            event_queue=event_queue,
            mime_type="image/svg+xml",
            size_bytes=target_path.stat().st_size,
            tags=["debug", "svg"],
            metadata={
                "local_path": str(target_path),
                "word": word,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message=f"Created SVG artifact {artifact_ref.artifact_id}.",
        )
        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message="SVG artifact created successfully.",
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
        """Convert an existing SVG artifact reference into a new PNG artifact reference."""
        artifact_id = str(params.get("artifact_id") or "").strip()
        if not artifact_id:
            return {
                "status": "error",
                "conversation_id": conversation_id,
                "message": "Parameter 'artifact_id' is required for SVG to PNG conversion.",
            }

        source_ref = self.resolve_artifact_reference(conversation_id, artifact_id)
        if not source_ref:
            return {
                "status": "error",
                "conversation_id": conversation_id,
                "message": f"Artifact '{artifact_id}' was not found in this conversation.",
            }

        source_dict = source_ref.to_dict()
        source_path = self._resolve_local_path(source_dict)
        if not source_path or not source_path.exists():
            return {
                "status": "error",
                "conversation_id": conversation_id,
                "message": "Source artifact URI is not a readable local file.",
                "source_artifact": source_dict,
            }

        if source_path.suffix.lower() != ".svg":
            return {
                "status": "error",
                "conversation_id": conversation_id,
                "message": f"Artifact '{artifact_id}' is not an SVG file.",
                "source_artifact": source_dict,
            }

        requested_name = str(params.get("name") or "").strip()
        base_stem = self._sanitize_stem(
            Path(requested_name).stem if requested_name else source_path.stem,
            fallback="converted",
        )
        target_path = self._unique_path(self._conversation_dir(conversation_id), f"{base_stem}.png")

        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message=f"Converting artifact '{source_ref.name}' to PNG.",
        )

        conversion_backend = self._convert_svg_to_png(source_path, target_path)

        description = str(
            params.get("description")
            or f"PNG converted from SVG artifact '{source_ref.name}' using {conversion_backend}."
        )
        output_ref = await self._register_reference_for_conversation(
            conversation_id=conversation_id,
            name=target_path.name,
            description=description,
            uri=self._artifact_uri_for_path(target_path),
            context=context,
            event_queue=event_queue,
            mime_type="image/png",
            size_bytes=target_path.stat().st_size,
            tags=["debug", "png", "converted"],
            metadata={
                "local_path": str(target_path),
                "source_artifact_id": source_ref.artifact_id,
                "converted_at": datetime.now(timezone.utc).isoformat(),
                "conversion_backend": conversion_backend,
            },
        )

        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message=f"Created PNG artifact {output_ref.artifact_id}.",
        )
        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message="SVG artifact converted to PNG successfully.",
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

    def configure_app(self, app) -> None:
        """Expose static artifact files for UI link rendering and manual debugging."""

        async def fetch_artifact(request):
            artifact_path = str(request.path_params.get("artifact_path") or "")
            if not artifact_path:
                return JSONResponse({"ok": False, "error": "Missing artifact path"}, status_code=400)

            safe_relative = unquote(artifact_path).lstrip("/")
            candidate = (self.artifact_root / safe_relative).resolve()
            root = self.artifact_root.resolve()
            if not str(candidate).startswith(f"{root}{os.sep}"):
                return JSONResponse({"ok": False, "error": "Invalid artifact path"}, status_code=400)
            if not candidate.exists() or not candidate.is_file():
                return JSONResponse({"ok": False, "error": "Artifact not found"}, status_code=404)

            return FileResponse(str(candidate))

        app.add_route("/artifacts/{artifact_path:path}", fetch_artifact, methods=["GET"])


if __name__ == "__main__":
    agent = ArtifactDebugAgent(agent_name="Artifact Debug Agent")
    agent.run(port=int(os.getenv("AGENT_PORT", "8000")))
