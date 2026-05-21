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
    UPLOAD_EXTENSIONS: list[str]  Legacy metadata for UI allowlists, not dispatch.
    async def detect_upload_mime(file_path: Path, mime_type: str) -> str | None
        Return a plugin MIME type after inspecting generic binary uploads.
    async def process_upload(file_path: Path, ...) -> tuple[str, list[cl.Element]]
        Handle a user-uploaded file. Returns (description_markdown, elements).
"""

import importlib
import inspect
import logging
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PLUGINS_DIR = Path(__file__).parent
ELEMENTS_DIR = PLUGINS_DIR.parent / "public" / "elements"

_mimetype_registry: dict[str, Any] = {}
_json_type_registry: dict[str, Any] = {}
_upload_detectors: list[Any] = []
_upload_process_params: dict[str, frozenset[str]] = {}

GENERIC_UPLOAD_MIMETYPES = {"", "application/octet-stream", "binary/octet-stream"}


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
            _mimetype_registry[mime.lower()] = module
        for json_type in getattr(module, "JSON_TYPES", []):
            _json_type_registry[json_type] = module
        if hasattr(module, "detect_upload_mime"):
            _upload_detectors.append(module)

        _install_jsx(plugin_dir)
        logger.info("Loaded visualization plugin: %s", plugin_dir.name)


def find_plugin_for_artifact(artifact: dict) -> Any | None:
    """Return the plugin module that can handle a given artifact, or None."""
    json_type = artifact.get("json_type") or (artifact.get("metadata") or {}).get("json_type")
    if json_type and json_type in _json_type_registry:
        return _json_type_registry[json_type]

    mime = (artifact.get("mime_type") or "").lower()
    if mime and mime in _mimetype_registry:
        return _mimetype_registry[mime]

    return None


def normalize_mime_type(mime_type: str | None) -> str:
    """Normalize a MIME value for registry lookup."""
    return (mime_type or "").split(";", 1)[0].strip().lower()


async def detect_upload_mime(file_path: Path, mime_type: str | None = None) -> str:
    """Return the best MIME type available for an uploaded file.

    Plugin dispatch remains MIME based. Detectors are only consulted when the
    browser provided a generic binary MIME type.
    """
    normalized = normalize_mime_type(mime_type)
    if normalized not in GENERIC_UPLOAD_MIMETYPES:
        return normalized

    for plugin in _upload_detectors:
        detector = plugin.detect_upload_mime
        try:
            detected = detector(file_path, normalized)
            if inspect.isawaitable(detected):
                detected = await detected
        except Exception as exc:
            logger.debug("Upload MIME detector failed for %s: %s", plugin.__name__, exc)
            continue
        detected = normalize_mime_type(detected)
        if detected and detected in _mimetype_registry:
            return detected

    return normalized or "application/octet-stream"


def find_plugin_for_upload(file_path: Path, *, mime_type: str | None = None) -> Any | None:
    """Return the plugin module that handles an uploaded MIME type, or None."""
    return _mimetype_registry.get(normalize_mime_type(mime_type))


async def render_artifact(artifact: dict):
    """Render an artifact using the appropriate plugin. Returns cl.Element or None."""
    plugin = find_plugin_for_artifact(artifact)
    if plugin and hasattr(plugin, "render_artifact"):
        return await plugin.render_artifact(artifact)
    return None


async def process_upload(
    file_path: Path,
    *,
    mime_type: str | None = None,
    display_name: str | None = None,
):
    """Process a file upload using the appropriate plugin.
    Returns (description_text, elements_list), or None if no plugin handles it.
    """
    plugin = find_plugin_for_upload(file_path, mime_type=mime_type)
    if plugin and hasattr(plugin, "process_upload"):
        process = plugin.process_upload
        module_name = getattr(plugin, "__name__", "")
        if module_name not in _upload_process_params:
            _upload_process_params[module_name] = frozenset(inspect.signature(process).parameters)
        params = _upload_process_params[module_name]
        kwargs: dict[str, Any] = {}
        if "mime_type" in params:
            kwargs["mime_type"] = normalize_mime_type(mime_type)
        if "display_name" in params:
            kwargs["display_name"] = display_name
        return await process(file_path, **kwargs)
    return None


# Discover and load all plugins at import time so JSX files are in place
# before Chainlit starts serving requests.
_load_plugins()
