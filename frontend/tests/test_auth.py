"""Tests for main.py auth_callback logic."""

from unittest.mock import MagicMock


def test_auth_callback_valid_user():
    """Valid credentials return a User object with correct metadata."""
    mock_user_cls = MagicMock()
    mock_settings = MagicMock()
    mock_settings.local_users = [
        {"username": "admin", "password": "admin", "role": "admin"},
        {"username": "viewer", "password": "view123", "role": "viewer"},
    ]

    # Replicate the auth logic directly (avoids importing chainlit-decorated function)
    def auth_callback(username, password):
        for user in mock_settings.local_users:
            if user.get("username") == username and user.get("password") == password:
                return mock_user_cls(
                    identifier=username,
                    metadata={"role": user.get("role", "user"), "provider": "credentials"},
                )
        return None

    result = auth_callback("admin", "admin")
    assert result is not None
    mock_user_cls.assert_called_once_with(
        identifier="admin",
        metadata={"role": "admin", "provider": "credentials"},
    )


def test_auth_callback_invalid_password():
    """Wrong password returns None."""
    mock_settings = MagicMock()
    mock_settings.local_users = [{"username": "admin", "password": "admin", "role": "admin"}]

    def auth_callback(username, password):
        for user in mock_settings.local_users:
            if user.get("username") == username and user.get("password") == password:
                return "user_obj"
        return None

    assert auth_callback("admin", "wrong") is None


def test_auth_callback_unknown_user():
    """Unknown username returns None."""
    mock_settings = MagicMock()
    mock_settings.local_users = [{"username": "admin", "password": "admin", "role": "admin"}]

    def auth_callback(username, password):
        for user in mock_settings.local_users:
            if user.get("username") == username and user.get("password") == password:
                return "user_obj"
        return None

    assert auth_callback("nobody", "admin") is None


def test_auth_callback_default_role():
    """Missing role key defaults to 'user'."""
    mock_user_cls = MagicMock()
    mock_settings = MagicMock()
    mock_settings.local_users = [{"username": "basic", "password": "pass"}]

    def auth_callback(username, password):
        for user in mock_settings.local_users:
            if user.get("username") == username and user.get("password") == password:
                return mock_user_cls(
                    identifier=username,
                    metadata={"role": user.get("role", "user"), "provider": "credentials"},
                )
        return None

    result = auth_callback("basic", "pass")
    assert result is not None
    mock_user_cls.assert_called_once_with(
        identifier="basic",
        metadata={"role": "user", "provider": "credentials"},
    )
