"""Visualization plugin registry.

Auto-discovers plugin subdirectories, copies each plugin's JSX component to
public/elements/ (where Chainlit serves custom elements), and provides dispatch
functions for artifact rendering and file upload handling.

Plugin contract — each plugins/<name>/__init__.py must provide:
    MIMETYPES: list[str]        MIME types this plugin handles
    JSON_TYPES: list[str]       artifact.json_type values this plugin handles
    TAGS: list[str]             artifact.tags values this plugin handles
    EXTENSIONS: list[str]       URI file-extension suffixes this plugin handles
    COMPONENT_NAME: str         name of the JSX CustomElement component

    async def render_artifact(artifact: dict) -> cl.Element | None
        Render an agent-produced artifact. Return None to fall through.

Optional:
    UPLOAD_EXTENSIONS: list[str]
    async def process_upload(file_path: Path) -> tuple[str, list[cl.Element]]
        Handle a user-uploaded file. Returns (description_markdown, elements).
"""

import importlib
import logging
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PLUGINS_DIR = Path(__file__).parent
ELEMENTS_DIR = PLUGINS_DIR.parent / "public" / "elements"

_mimetype_registry: dict[str, Any] = {}
_json_type_registry: dict[str, Any] = {}
_tag_registry: dict[str, Any] = {}
_extension_registry: dict[str, Any] = {}
_upload_extension_registry: dict[str, Any] = {}


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
        for tag in getattr(module, "TAGS", []):
            _tag_registry[tag.lower()] = module
        for ext in getattr(module, "EXTENSIONS", []):
            _extension_registry[ext.lower()] = module
        for ext in getattr(module, "UPLOAD_EXTENSIONS", []):
            _upload_extension_registry[ext.lower()] = module

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

    tags = [t.lower() for t in (artifact.get("tags") or [])]
    for tag in tags:
        if tag in _tag_registry:
            return _tag_registry[tag]

    uri = artifact.get("uri") or ""
    if uri:
        ext = Path(uri).suffix.lower()
        if ext in _extension_registry:
            return _extension_registry[ext]

    return None


def find_plugin_for_upload(file_path: Path) -> Any | None:
    """Return the plugin module that handles a given uploaded file, or None."""
    return _upload_extension_registry.get(file_path.suffix.lower())


async def render_artifact(artifact: dict):
    """Render an artifact using the appropriate plugin. Returns cl.Element or None."""
    plugin = find_plugin_for_artifact(artifact)
    if plugin and hasattr(plugin, "render_artifact"):
        return await plugin.render_artifact(artifact)
    return None


async def process_upload(file_path: Path):
    """Process a file upload using the appropriate plugin.
    Returns (description_text, elements_list), or None if no plugin handles it.
    """
    plugin = find_plugin_for_upload(file_path)
    if plugin and hasattr(plugin, "process_upload"):
        return await plugin.process_upload(file_path)
    return None


# Discover and load all plugins at import time so JSX files are in place
# before Chainlit starts serving requests.
_load_plugins()
