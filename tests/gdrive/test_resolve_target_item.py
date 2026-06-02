"""
Tests for resolve_target_item - the resolver for an item being OPERATED ON
(share / reparent / set-permissions). It tolerates the drive.file picker
asymmetry: a picked folder's files.get 404s even though the operation (e.g.
permissions.create, files.update) is permitted, so on a not-connected read
failure under drive.file it falls back to (file_id, {}).
"""

import os
import sys

import pytest
from httplib2 import Response
from googleapiclient.errors import HttpError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from gdrive.drive_helpers import resolve_target_item
from auth.scopes import set_drive_access_mode
import auth.scopes as scopes_module


@pytest.fixture(autouse=True)
def _reset_mode():
    scopes_module._DRIVE_ACCESS_MODE_OVERRIDE = None
    yield
    scopes_module._DRIVE_ACCESS_MODE_OVERRIDE = None


def _http_error(status: int, message: str) -> HttpError:
    resp = Response({"status": status})
    content = ('{"error": {"code": %d, "message": "%s"}}' % (status, message)).encode()
    return HttpError(resp, content)


def _service_raising(error: Exception):
    """A drive service whose files().get().execute raises `error`."""

    class _Exec:
        def execute(self, *a, **k):
            raise error

    class _Files:
        def get(self, *a, **k):
            return _Exec()

    class _Service:
        def files(self):
            return _Files()

    return _Service()


def _service_returning(metadata: dict):
    """A drive service whose files().get().execute returns `metadata`."""

    class _Exec:
        def execute(self, *a, **k):
            return metadata

    class _Files:
        def get(self, *a, **k):
            return _Exec()

    class _Service:
        def files(self):
            return _Files()

    return _Service()


@pytest.mark.asyncio
async def test_successful_read_returns_id_and_metadata():
    # A picked FILE's files.get succeeds: pass through id + metadata unchanged.
    set_drive_access_mode("file")
    service = _service_returning(
        {
            "id": "FILE123",
            "name": "Doc",
            "mimeType": "application/vnd.google-apps.document",
        }
    )
    resolved_id, metadata = await resolve_target_item(service, "FILE123")
    assert resolved_id == "FILE123"
    assert metadata["name"] == "Doc"


@pytest.mark.asyncio
async def test_file_mode_404_falls_back_to_raw_id_and_empty_metadata():
    # A picked FOLDER whose files.get 404s must still be operable: fall back to
    # the raw ID with empty metadata so the real operation runs.
    set_drive_access_mode("file")
    service = _service_raising(_http_error(404, "File not found: FOLDER123"))
    resolved_id, metadata = await resolve_target_item(service, "FOLDER123")
    assert resolved_id == "FOLDER123"
    assert metadata == {}


@pytest.mark.asyncio
async def test_file_mode_403_file_permission_falls_back():
    set_drive_access_mode("file")
    service = _service_raising(
        _http_error(403, "The user does not have sufficient permissions for file")
    )
    resolved_id, metadata = await resolve_target_item(service, "FOLDER123")
    assert resolved_id == "FOLDER123"
    assert metadata == {}


@pytest.mark.asyncio
async def test_strict_reraises_in_file_mode():
    # strict=True requires a successful, validated read even under drive.file.
    set_drive_access_mode("file")
    service = _service_raising(_http_error(404, "File not found: FOLDER123"))
    with pytest.raises(HttpError):
        await resolve_target_item(service, "FOLDER123", strict=True)


@pytest.mark.asyncio
async def test_full_mode_404_reraises():
    # In full-drive mode a 404 is a genuine error; do not mask it.
    set_drive_access_mode("full")
    service = _service_raising(_http_error(404, "File not found: FOLDER123"))
    with pytest.raises(HttpError):
        await resolve_target_item(service, "FOLDER123")


@pytest.mark.asyncio
async def test_file_mode_non_access_error_reraises():
    # A 500 (or other non "not connected" error) must not be swallowed.
    set_drive_access_mode("file")
    service = _service_raising(_http_error(500, "Backend Error"))
    with pytest.raises(HttpError):
        await resolve_target_item(service, "FOLDER123")
