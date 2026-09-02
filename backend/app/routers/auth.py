"""Authentication endpoints — login, logout, me, and a reserved OAuth callback.

Replaces Chainlit's built-in auth surface. Login issues a JWT session cookie
(httpOnly, SameSite=Lax, Secure outside debug); ``/api/auth/me`` replaces the
React app's ``fetch("/user")`` probe. The OAuth ``callback`` route is reserved and
returns 501 until a real identity provider is wired (see :mod:`app.security`).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db_session
from app.security import (
    User,
    current_user,
    get_provider,
    issue_token,
    revoke_session,
    set_session_cookie,
    verify_token,
)
from app.sessions import get_store

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginResult(BaseModel):
    user: User


async def _read_credentials(request: Request) -> tuple[Optional[str], Optional[str]]:
    """Extract ``(username, password)`` from a JSON or form-encoded request body.

    FastAPI can't declare both ``Body`` and ``Form`` params on one endpoint (the
    presence of ``Form`` forces multipart/form decoding), so dispatch on the
    Content-Type ourselves to accept either shape.
    """
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        try:
            data = await request.json()
        except Exception:
            return None, None
        if not isinstance(data, dict):
            return None, None
        return data.get("username"), data.get("password")
    form = await request.form()
    username = form.get("username")
    password = form.get("password")
    return (
        username if isinstance(username, str) else None,
        password if isinstance(password, str) else None,
    )


@router.post("/login", response_model=LoginResult)
async def login(request: Request, response: Response, db: AsyncSession = Depends(get_db_session)) -> LoginResult:
    """Accept form-encoded or JSON ``{username, password}`` and set the cookie."""
    username, password = await _read_credentials(request)
    if not username or not password:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="username and password required")

    provider = get_provider("credentials")
    user = await provider.authenticate(username, password, db) if provider else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = issue_token(user)
    # Register the freshly minted session id so downstream endpoints can look it up.
    get_store(request).get_or_create(verify_token(token).sid)
    set_session_cookie(response, token)
    return LoginResult(user=user)


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict[str, bool]:
    """Clear the session cookie and forget any server-side session state."""
    cookie = request.cookies.get(settings.cookie_name)
    if cookie:
        try:
            claims = verify_token(cookie)
            get_store(request).drop(claims.sid)
            # AU-1: revoke the sid so the (still-unexpired) JWT can't be replayed.
            revoke_session(claims.sid, claims.exp)
        except Exception:
            # A bad/expired cookie has nothing to clean up; still clear it below.
            pass
    response.delete_cookie(key=settings.cookie_name, path="/")
    return {"ok": True}


@router.get("/me", response_model=User)
async def me(user: User = Depends(current_user)) -> User:
    """Return the authenticated user, or 401. Replaces the React ``/user`` probe."""
    return user


@router.get("/callback/{provider}")
async def oauth_callback(provider: str) -> Response:
    """OAuth redirect callback — resolved through the provider registry (AU-6).

    A registered provider completes the handshake via ``IdentityProvider.callback``.
    No OAuth provider is wired today, so this returns 501 — but the seam is real: a
    future provider registered via ``security.register_provider`` is picked up here
    without changing this route.
    """
    impl = get_provider(provider)
    if impl is not None:
        try:
            impl.callback(provider, {})
        except NotImplementedError:
            pass  # fall through to 501 below
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"OAuth provider '{provider}' is not configured",
    )
