"""
Tests for the lazy secondary-service helpers used by parent_folder_id create
tools: get_secondary_google_service and the secondary_google_service context
manager (auth/service_decorator.py).
"""

import sys
import os

import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import auth.service_decorator as sd
from auth.service_decorator import (
    get_secondary_google_service,
    secondary_google_service,
)


@pytest.fixture
def _patch_auth(monkeypatch):
    """Stub the auth plumbing so the helper can run without a live context."""
    captured = {}

    async def _fake_ctx(tool_name):
        return ("auth-user@example.com", "oauth21", "session-1")

    def _fake_detect(authenticated_user, mcp_session_id, tool_name):
        return True

    async def _fake_authenticate(
        use_oauth21,
        service_name,
        service_version,
        tool_name,
        user_google_email,
        resolved_scopes,
        mcp_session_id,
        authenticated_user,
    ):
        captured["service_name"] = service_name
        captured["resolved_scopes"] = resolved_scopes
        captured["user_google_email"] = user_google_email
        return (MagicMock(name="service"), user_google_email)

    monkeypatch.setattr(sd, "_get_auth_context", _fake_ctx)
    monkeypatch.setattr(sd, "_detect_oauth_version", _fake_detect)
    monkeypatch.setattr(sd, "_authenticate_service", _fake_authenticate)
    monkeypatch.setattr(sd, "is_oauth21_enabled", lambda: True)
    return captured


@pytest.mark.asyncio
async def test_unknown_service_type_raises():
    with pytest.raises(Exception):
        await get_secondary_google_service(
            "not-a-service", "drive_file", "create_doc", "u@example.com"
        )


@pytest.mark.asyncio
async def test_resolves_scopes_and_service(_patch_auth):
    service, email = await get_secondary_google_service(
        "drive", "drive_file", "create_doc", "u@example.com"
    )
    assert _patch_auth["service_name"] == "drive"
    assert _patch_auth["resolved_scopes"] == [
        "https://www.googleapis.com/auth/drive.file"
    ]
    assert service is not None


@pytest.mark.asyncio
async def test_oauth21_overrides_user_email(_patch_auth):
    # Caller passes a different email; OAuth 2.1 authenticated identity wins.
    await get_secondary_google_service(
        "drive", "drive_file", "create_doc", "caller@example.com"
    )
    assert _patch_auth["user_google_email"] == "auth-user@example.com"


@pytest.mark.asyncio
async def test_context_manager_closes_and_releases(monkeypatch):
    fake_service = MagicMock(name="service")
    released = {"count": 0}

    async def _fake_get(*args, **kwargs):
        return (fake_service, "u@example.com")

    monkeypatch.setattr(sd, "get_secondary_google_service", _fake_get)
    monkeypatch.setattr(
        sd,
        "_release_google_service_cycles",
        lambda: released.__setitem__("count", released["count"] + 1),
    )

    async with secondary_google_service(
        "drive", "drive_file", "create_doc", "u@example.com"
    ) as svc:
        assert svc is fake_service

    fake_service.close.assert_called_once()
    assert released["count"] == 1


@pytest.mark.asyncio
async def test_context_manager_closes_on_exception(monkeypatch):
    fake_service = MagicMock(name="service")
    released = {"count": 0}

    async def _fake_get(*args, **kwargs):
        return (fake_service, "u@example.com")

    monkeypatch.setattr(sd, "get_secondary_google_service", _fake_get)
    monkeypatch.setattr(
        sd,
        "_release_google_service_cycles",
        lambda: released.__setitem__("count", released["count"] + 1),
    )

    with pytest.raises(ValueError):
        async with secondary_google_service(
            "drive", "drive_file", "create_doc", "u@example.com"
        ):
            raise ValueError("boom")

    fake_service.close.assert_called_once()
    assert released["count"] == 1
