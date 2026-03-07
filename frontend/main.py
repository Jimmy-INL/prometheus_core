import chainlit as cl
from typing import Optional

from utils.settings import settings
from components.message_handler import message_handler
from components.settings_handler import configure_settings, settings_debug_options


@cl.password_auth_callback
def auth_callback(username: str, password: str):
    for user in settings.local_users:
        if user.get("username") == username and user.get("password") == password:
            return cl.User(identifier=username, metadata={"role": user.get("role", "user"), "provider": "credentials"})
    return None


#@cl.oauth_callback
#def oauth_callback(
#    provider_id: str,
#    token: str,
#    raw_user_data: dict[str, str],
#    default_user: cl.User,
#) -> Optional[cl.User]:
#    return default_user


@cl.on_message
async def on_message(message: cl.Message):
    await message_handler(message)


@cl.on_settings_update
async def on_settings_update(settings):
    await settings_debug_options(ui_settings=settings)


@cl.on_chat_start
async def on_chat_start():
    await configure_settings()

    suggestions = cl.CustomElement(
        name="FollowUpSuggestions",
        props={"suggestions": settings.workflow_suggestions, "title": settings.chat_suggestion_title},
    )

    await cl.Message(content=settings.chat_intro, elements=[suggestions]).send()
