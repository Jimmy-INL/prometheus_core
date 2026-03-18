import uuid

import chainlit as cl

# Import plugins early so JSX components are copied to public/elements/
# before Chainlit starts serving custom elements.
import plugins as _visualization_plugins  # noqa: F401

from utils.settings import settings
from utils.conversation_state_client import ConversationStateClient
from components.message_handler import message_handler
from components.settings_handler import configure_settings, settings_debug_options

_conversation_state_client = ConversationStateClient(settings.redis_url)


@cl.password_auth_callback
def auth_callback(username: str, password: str):
    for user in settings.local_users:
        if user.get("username") == username and user.get("password") == password:
            return cl.User(identifier=username, metadata={"role": user.get("role", "user"), "provider": "credentials"})
    return None


@cl.on_message
async def on_message(message: cl.Message):
    content = message.content.strip()

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


async def _handle_conversation_history():
    """Display recent conversation history from Redis."""
    if not _conversation_state_client.available:
        await cl.Message(content="History unavailable (Redis not connected).").send()
        return

    conversations = _conversation_state_client.get_conversation_history(limit=20)
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
        json_type = a.get("json_type", "")
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
        if json_type:
            detail_parts.append(f"JSON: `{json_type}`")
        if tags:
            detail_parts.append(f"Tags: {tags}")
        if uri:
            detail_parts.append(f"URI: `{uri}`")
        if detail_parts:
            lines.append(f"*{' | '.join(detail_parts)}*")
        lines.append("")

    await cl.Message(content="\n".join(lines)).send()
