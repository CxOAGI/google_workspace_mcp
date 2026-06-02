"""
Tests for resolve_destination_folder_id - the create/move folder resolver that
tolerates the drive.file picker asymmetry (create-in-folder allowed even when
files.get on the folder returns 404).
"""

import os
import sys

import pytest
from httplib2 import Response
from googleapiclient.errors import HttpError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from gdrive.drive_helpers import resolve_destination_folder_id
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


@pytest.mark.asyncio
async def test_root_short_circuits_without_api_call():
    # 'root' must never trigger a files.get (which would 404 under drive.file).
    set_drive_access_mode("file")
    service = _service_raising(AssertionError("files.get should not be called"))
    assert await resolve_destination_folder_id(service, "root") == "root"


@pytest.mark.asyncio
async def test_file_mode_404_falls_back_to_raw_id():
    # The reported bug: a picked folder whose files.get 404s must still be usable
    # as a create target under drive.file.
    set_drive_access_mode("file")
    service = _service_raising(_http_error(404, "File not found: FOLDER123"))
    assert await resolve_destination_folder_id(service, "FOLDER123") == "FOLDER123"


@pytest.mark.asyncio
async def test_file_mode_403_file_permission_falls_back():
    set_drive_access_mode("file")
    service = _service_raising(
        _http_error(403, "The user does not have sufficient permissions for file")
    )
    assert await resolve_destination_folder_id(service, "FOLDER123") == "FOLDER123"


@pytest.mark.asyncio
async def test_full_mode_404_reraises():
    # In full-drive mode a 404 is a genuine error; do not mask it.
    set_drive_access_mode("full")
    service = _service_raising(_http_error(404, "File not found: FOLDER123"))
    with pytest.raises(HttpError):
        await resolve_destination_folder_id(service, "FOLDER123")


@pytest.mark.asyncio
async def test_file_mode_non_access_error_reraises():
    # A 500 (or other non "not connected" error) must not be swallowed.
    set_drive_access_mode("file")
    service = _service_raising(_http_error(500, "Backend Error"))
    with pytest.raises(HttpError):
        await resolve_destination_folder_id(service, "FOLDER123")
