"""Visualization plugin registry.

Auto-discovers plugin subdirectories, copies each plugin's JSX component to
public/elements/ (where Chainlit serves custom elements), and provides dispatch
functions for artifact rendering and file upload handling.

Plugin contract - each plugins/<name>/__init__.py must provide:
    MIMETYPES: list[str]        MIME types this plugin handles
    JSON_TYPES: list[str]       artifact.json_type values this plugin handles
    COMPONENT_NAME: str         name of the JSX CustomElement component

    async def render_artifact(artifact: dict) -> cl.Element | None
        Render an agent-produced artifact. Return None to fall through.

Optional:
    UPLOAD_EXTENSIONS: list[str]  File extensions (e.g. ".stl"). Used for UI
        allowlists and as the artifact-dispatch fallback when json_type/mime_type
        don't match (so agent-emitted artifacts render even with informal MIME).
    async def inspect_upload(context: UploadContext) -> UploadMatch | None
        Return a plugin MIME type and confidence for a user-uploaded file.
    async def process_upload(context: UploadContext) -> UploadRenderResult
        Handle a user-uploaded file for local preview.
"""

from dataclasses import replace
import importlib
import logging
import shutil
from pathlib import Path
from typing import Any

from .upload_contract import (
    GENERIC_UPLOAD_MIMETYPES,
    UploadContext,
    UploadMatch,
    UploadRenderResult,
    normalize_mime_type,
)

logger = logging.getLogger(__name__)

PLUGINS_DIR = Path(__file__).parent
ELEMENTS_DIR = PLUGINS_DIR.parent / "public" / "elements"

_mimetype_registry: dict[str, Any] = {}
_json_type_registry: dict[str, Any] = {}
_extension_registry: dict[str, Any] = {}
_upload_plugins: list[Any] = []


def _install_jsx(plugin_dir: Path) -> None:
    """Copy any *.jsx files from a plugin directory into public/elements/."""
    ELEMENTS_DIR.mkdir(parents=True, exist_ok=True)
    for jsx_file in plugin_dir.glob("*.jsx"):
        target = ELEMENTS_DIR / jsx_file.name
        if not target.exists() or jsx_file.stat().st_mtime > target.stat().st_mtime:
            shutil.copy2(jsx_file, target)
            logger.debug("Installed %s from plugin '%s'", jsx_file.name, plugin_dir.name)


def _load_plugins() -> None:
    for plugin_dir in sorted(PLUGINS_DIR.iterdir()):
        if not plugin_dir.is_dir() or plugin_dir.name.startswith("_"):
            continue
        try:
            module = importlib.import_module(f"plugins.{plugin_dir.name}")
        except Exception as exc:
            logger.warning("Failed to load plugin '%s': %s", plugin_dir.name, exc)
            continue

        for mime in getattr(module, "MIMETYPES", []):
            _mimetype_registry[normalize_mime_type(mime)] = module
        for json_type in getattr(module, "JSON_TYPES", []):
            _json_type_registry[json_type] = module
        for ext in getattr(module, "UPLOAD_EXTENSIONS", []):
            _extension_registry.setdefault(str(ext).lower(), module)
        if hasattr(module, "inspect_upload") or hasattr(module, "process_upload"):
            _upload_plugins.append(module)

        _install_jsx(plugin_dir)
        logger.info("Loaded visualization plugin: %s", plugin_dir.name)


def _artifact_suffix(artifact: dict) -> str:
    """Best-effort file extension for an artifact, from its name or URI."""
    for value in (artifact.get("name"), artifact.get("uri")):
        if not value:
            continue
        # Strip any query/fragment before reading the suffix off the last segment.
        path = str(value).split("?", 1)[0].split("#", 1)[0]
        suffix = Path(path).suffix.lower()
        if suffix:
            return suffix
    return ""


def find_plugin_for_artifact(artifact: dict) -> Any | None:
    """Return the plugin module that can handle a given artifact, or None.

    Dispatch order: explicit ``json_type``, then ``mime_type``, then a fallback on
    the artifact's file extension (name/URI). The extension fallback makes
    agent-emitted artifacts robust to mislabeled or informal MIME types — an agent
    that returns ``foo.stl`` renders even if it tags it ``application/octet-stream``.
    """
    json_type = artifact.get("json_type") or (artifact.get("metadata") or {}).get("json_type")
    if json_type and json_type in _json_type_registry:
        return _json_type_registry[json_type]

    mime = (artifact.get("mime_type") or "").lower()
    if mime and mime in _mimetype_registry:
        return _mimetype_registry[mime]

    suffix = _artifact_suffix(artifact)
    if suffix and suffix in _extension_registry:
        return _extension_registry[suffix]

    return None


async def render_artifact(artifact: dict):
    """Render an artifact using the appropriate plugin. Returns cl.Element or None."""
    plugin = find_plugin_for_artifact(artifact)
    if plugin and hasattr(plugin, "render_artifact"):
        return await plugin.render_artifact(artifact)
    return None


def _plugin_name(plugin: Any) -> str:
    return str(getattr(plugin, "__name__", ""))


def _plugin_mimetypes(plugin: Any) -> set[str]:
    return {normalize_mime_type(mime) for mime in getattr(plugin, "MIMETYPES", [])}


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


def _coerce_upload_match(plugin: Any, value: Any) -> UploadMatch | None:
    if value is None:
        return None
    if isinstance(value, UploadMatch):
        match = value
    elif isinstance(value, str):
        match = UploadMatch(mime_type=value)
    elif isinstance(value, dict):
        match = UploadMatch(
            mime_type=str(value.get("mime_type") or ""),
            confidence=int(value.get("confidence", 50)),
            reason=str(value.get("reason") or ""),
        )
    else:
        logger.debug("Ignoring invalid upload match from %s: %r", _plugin_name(plugin), value)
        return None

    mime_type = normalize_mime_type(match.mime_type)
    if not mime_type:
        return None
    if mime_type not in _plugin_mimetypes(plugin):
        logger.debug("Ignoring unsupported upload MIME %r from %s", mime_type, _plugin_name(plugin))
        return None
    confidence = max(0, min(100, int(match.confidence)))
    return replace(match, mime_type=mime_type, confidence=confidence, plugin=plugin)


def _coerce_render_result(value: Any) -> UploadRenderResult | None:
    if value is None:
        return None
    if isinstance(value, UploadRenderResult):
        return value
    if isinstance(value, tuple) and len(value) >= 2:
        return UploadRenderResult(
            description=str(value[0]),
            elements=list(value[1] or []),
        )
    logger.debug("Ignoring invalid upload render result: %r", value)
    return None


async def inspect_upload(context: UploadContext) -> UploadMatch | None:
    """Return the highest-confidence plugin match for an uploaded file."""
    candidates: list[UploadMatch] = []
    request_mime = normalize_mime_type(context.mime_type)

    for plugin in _upload_plugins:
        inspector = getattr(plugin, "inspect_upload", None)
        if inspector is not None:
            try:
                match = _coerce_upload_match(
                    plugin,
                    await _maybe_await(inspector(context)),
                )
            except Exception as exc:
                logger.debug("Upload inspector failed for %s: %s", _plugin_name(plugin), exc)
                continue
            if match is not None:
                candidates.append(match)
            continue

        if request_mime and request_mime in _plugin_mimetypes(plugin):
            candidates.append(
                UploadMatch(
                    mime_type=request_mime,
                    confidence=50,
                    reason="declared MIME type",
                    plugin=plugin,
                )
            )

    if not candidates:
        return None
    return sorted(candidates, key=lambda match: (-match.confidence, _plugin_name(match.plugin)))[0]


async def process_upload(
    context: UploadContext,
    *,
    match: UploadMatch | None = None,
) -> UploadRenderResult | None:
    """Process a file upload using the selected plugin, if any."""
    selected = match
    if selected is None or selected.plugin is None:
        selected = await inspect_upload(context)
    if selected is None or selected.plugin is None:
        return None

    process = getattr(selected.plugin, "process_upload", None)
    if process is None:
        return None
    return _coerce_render_result(await _maybe_await(process(context)))


# Discover and load all plugins at import time so JSX files are in place
# before Chainlit starts serving requests.
_load_plugins()
