"""Tests for gdrive.drive_helpers.move_file_to_folder (parent_folder_id support)."""

import sys
import os

import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import gdrive.drive_helpers as drive_helpers
from gdrive.drive_helpers import move_file_to_folder


def _fake_drive_service(current_parents):
    """A MagicMock drive service whose files().get() returns the given parents."""
    service = MagicMock()
    files_obj = service.files.return_value
    get_result = {"parents": current_parents} if current_parents is not None else {}
    files_obj.get.return_value.execute.return_value = get_result
    files_obj.update.return_value.execute.return_value = {"id": "FILE1"}
    return service, files_obj


@pytest.fixture(autouse=True)
def _stub_resolve_folder(monkeypatch):
    async def _fake_resolve(service, folder_id, **kwargs):
        return f"resolved::{folder_id}"

    monkeypatch.setattr(drive_helpers, "resolve_folder_id", _fake_resolve)


@pytest.mark.asyncio
async def test_move_detaches_current_parents_and_adds_target():
    service, files_obj = _fake_drive_service(["root"])

    resolved = await move_file_to_folder(service, "FILE1", "FOLDER123")

    assert resolved == "resolved::FOLDER123"
    files_obj.update.assert_called_once()
    _, kwargs = files_obj.update.call_args
    assert kwargs["fileId"] == "FILE1"
    assert kwargs["addParents"] == "resolved::FOLDER123"
    assert kwargs["removeParents"] == "root"
    assert kwargs["supportsAllDrives"] is True


@pytest.mark.asyncio
async def test_move_omits_removeparents_when_no_current_parents():
    service, files_obj = _fake_drive_service([])

    await move_file_to_folder(service, "FILE1", "FOLDER123")

    _, kwargs = files_obj.update.call_args
    assert kwargs["addParents"] == "resolved::FOLDER123"
    assert "removeParents" not in kwargs


@pytest.mark.asyncio
async def test_move_joins_multiple_current_parents():
    service, files_obj = _fake_drive_service(["p1", "p2"])

    await move_file_to_folder(service, "FILE1", "FOLDER123")

    _, kwargs = files_obj.update.call_args
    assert kwargs["removeParents"] == "p1,p2"
