import uuid

import chainlit as cl

# Import plugins early so JSX components are copied to public/elements/
# before Chainlit starts serving custom elements.
import plugins as _visualization_plugins  # noqa: F401

from utils.settings import settings
from utils.memory_client import MemoryClient
from components.message_handler import message_handler
from components.settings_handler import configure_settings, settings_debug_options

_memory_client = MemoryClient(settings.redis_url)


@cl.password_auth_callback
def auth_callback(username: str, password: str):
    for user in settings.local_users:
        if user.get("username") == username and user.get("password") == password:
            return cl.User(identifier=username, metadata={"role": user.get("role", "user"), "provider": "credentials"})
    return None


@cl.on_message
async def on_message(message: cl.Message):
    content = message.content.strip()

    # Handle /memory command
    if content.lower().startswith("/memory"):
        args = content[7:].strip()
        if args.lower() == "clear":
            await _handle_memory_clear()
        elif args:
            await _handle_memory_search(args)
        else:
            await _handle_memory_list()
        return

    # Handle /history command
    if content.lower().startswith("/history"):
        await _handle_conversation_history()
        return

    # Handle /artifacts command
    if content.lower().startswith("/artifacts"):
        await _handle_artifacts_list()
        return

    await message_handler(message)


@cl.on_settings_update
async def on_settings_update(settings):
    await settings_debug_options(ui_settings=settings)


@cl.on_chat_start
async def on_chat_start():
    # Initialize conversation state for A2A multi-turn
    cl.user_session.set("conversation_id", str(uuid.uuid4()))
    cl.user_session.set("artifacts", [])

    await configure_settings()

    suggestions = cl.CustomElement(
        name="FollowUpSuggestions",
        props={"suggestions": settings.workflow_suggestions, "title": settings.chat_suggestion_title},
    )

    await cl.Message(content=settings.chat_intro, elements=[suggestions]).send()


# --- Memory commands ---


async def _handle_memory_list():
    """Display all stored factoids."""
    if not _memory_client.available:
        await cl.Message(content="Memory system unavailable (Redis not connected).").send()
        return

    factoids = _memory_client.get_all_factoids(limit=50)
    if not factoids:
        await cl.Message(content="No memories stored yet. Memories are created automatically when analyses complete.").send()
        return

    lines = [f"**Stored Memories ({len(factoids)} factoids):**\n"]
    for f in factoids:
        fid = f.get("factoid_id", "?")[:8]
        content = f.get("content", "")
        material = f.get("material_id", "—")
        analysis = f.get("analysis_type", "—")
        factoid_type = f.get("factoid_type", "—")
        confidence = f.get("confidence", "—")
        created = f.get("created_at", "")
        if created:
            created = created[:19]  # Trim to YYYY-MM-DDTHH:MM:SS

        lines.append(f"**`{fid}`** | {material} | {analysis} | {factoid_type}")
        lines.append(f"> {content}")
        if confidence != "—":
            lines.append(f"*Confidence: {confidence} | Created: {created}*")
        lines.append("")

    lines.append("---")
    lines.append("Use `/memory clear` to clear all memories, or `/memory <material>` to filter by material.")

    await cl.Message(content="\n".join(lines)).send()


async def _handle_memory_search(query: str):
    """Search factoids by material ID."""
    if not _memory_client.available:
        await cl.Message(content="Memory system unavailable (Redis not connected).").send()
        return

    factoids = _memory_client.get_factoids_by_material(query)
    if not factoids:
        await cl.Message(content=f"No memories found for material **{query}**.").send()
        return

    lines = [f"**Memories for material `{query}` ({len(factoids)} factoids):**\n"]
    for f in factoids:
        fid = f.get("factoid_id", "?")[:8]
        content = f.get("content", "")
        analysis = f.get("analysis_type", "—")
        factoid_type = f.get("factoid_type", "—")

        lines.append(f"**`{fid}`** | {analysis} | {factoid_type}")
        lines.append(f"> {content}")
        lines.append("")

    await cl.Message(content="\n".join(lines)).send()


async def _handle_memory_clear():
    """Clear all stored factoids with confirmation."""
    if not _memory_client.available:
        await cl.Message(content="Memory system unavailable (Redis not connected).").send()
        return

    res = await cl.AskActionMessage(
        content="Are you sure you want to clear all stored memories? This cannot be undone.",
        actions=[
            cl.Action(name="confirm", payload={"value": "confirm"}, label="Clear All Memories"),
            cl.Action(name="cancel", payload={"value": "cancel"}, label="Cancel"),
        ],
    ).send()

    if not res or res.get("name") == "cancel":
        await cl.Message(content="Memory clear cancelled.").send()
        return

    count = _memory_client.clear_all_factoids()
    await cl.Message(content=f"Cleared **{count}** factoids from memory.").send()


# --- Conversation history ---


async def _handle_conversation_history():
    """Display recent conversation history from Redis."""
    if not _memory_client.available:
        await cl.Message(content="History unavailable (Redis not connected).").send()
        return

    conversations = _memory_client.get_conversation_history(limit=20)
    if not conversations:
        await cl.Message(content="No conversation history found.").send()
        return

    lines = [f"**Recent Conversations ({len(conversations)}):**\n"]
    for conv in conversations:
        conv_id = conv.get("conversation_id", "?")[:8]
        query = conv.get("query", "—")
        status = conv.get("status", "—")
        material = conv.get("material_id") or ""
        timestamp = conv.get("timestamp", "")
        if timestamp:
            timestamp = timestamp[:19]

        status_icon = {"completed": "done", "executing": "running", "plan_ready": "pending"}.get(status, status)
        material_tag = f" | `{material}`" if material else ""
        lines.append(f"**`{conv_id}`** [{status_icon}]{material_tag}")
        if query:
            lines.append(f"> {query[:120]}{'...' if len(query) > 120 else ''}")
        if timestamp:
            lines.append(f"*{timestamp}*")
        lines.append("")

    await cl.Message(content="\n".join(lines)).send()


# --- Artifacts list ---


async def _handle_artifacts_list():
    """Display artifacts from the current conversation."""
    artifacts = cl.user_session.get("artifacts", [])
    if not artifacts:
        await cl.Message(content="No artifacts in the current conversation.").send()
        return

    lines = [f"**Artifacts ({len(artifacts)}):**\n"]
    for a in artifacts:
        name = a.get("name", "Unnamed")
        mime = a.get("mime_type", "")
        uri = a.get("uri", "")
        desc = a.get("description", "")
        aid = a.get("artifact_id", "?")[:8]
        tags = ", ".join(a.get("tags", []))

        lines.append(f"**`{aid}`** — {name}")
        if desc:
            lines.append(f"> {desc[:200]}")
        detail_parts = []
        if mime:
            detail_parts.append(f"Type: `{mime}`")
        if tags:
            detail_parts.append(f"Tags: {tags}")
        if uri:
            detail_parts.append(f"URI: `{uri}`")
        if detail_parts:
            lines.append(f"*{' | '.join(detail_parts)}*")
        lines.append("")

    await cl.Message(content="\n".join(lines)).send()
