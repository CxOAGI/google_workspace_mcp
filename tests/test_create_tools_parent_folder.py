"""
Behavioral tests for parent_folder_id on the create tools (create_doc,
create_presentation, create_form): when provided, the new resource is moved
into the folder via a lazily-acquired Drive service; when omitted, no secondary
Drive service is requested and behavior is unchanged.
"""

import sys
import os

import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import gdocs.docs_tools as docs_tools
import gslides.slides_tools as slides_tools
import gforms.forms_tools as forms_tools


def _unwrap(tool):
    fn = tool.fn if hasattr(tool, "fn") else tool
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


class _FakeCM:
    def __init__(self, svc, recorder):
        self.svc = svc
        self.recorder = recorder

    async def __aenter__(self):
        self.recorder["entered"] = True
        return self.svc

    async def __aexit__(self, *exc):
        self.recorder["exited"] = True
        return False


@pytest.fixture
def _patch_move(monkeypatch):
    """Patch secondary_google_service + move_file_to_folder in all 3 modules."""
    rec = {"secondary_calls": [], "move_calls": [], "entered": False, "exited": False}
    drive_sentinel = MagicMock(name="drive_service")

    def fake_secondary(*args, **kwargs):
        rec["secondary_calls"].append((args, kwargs))
        return _FakeCM(drive_sentinel, rec)

    async def fake_move(drive_service, file_id, parent_folder_id):
        rec["move_calls"].append((drive_service, file_id, parent_folder_id))
        return f"resolved::{parent_folder_id}"

    for mod in (docs_tools, slides_tools, forms_tools):
        monkeypatch.setattr(mod, "secondary_google_service", fake_secondary)
        monkeypatch.setattr(mod, "move_file_to_folder", fake_move)
    rec["drive_sentinel"] = drive_sentinel
    return rec


def _docs_service():
    svc = MagicMock()
    svc.documents.return_value.create.return_value.execute.return_value = {
        "documentId": "DOC1"
    }
    return svc


def _slides_service():
    svc = MagicMock()
    svc.presentations.return_value.create.return_value.execute.return_value = {
        "presentationId": "PRES1",
        "slides": [],
    }
    return svc


def _forms_service():
    svc = MagicMock()
    svc.forms.return_value.create.return_value.execute.return_value = {
        "formId": "FORM1",
        "responderUri": "https://docs.google.com/forms/d/FORM1/viewform",
        "info": {"title": "T"},
    }
    return svc


@pytest.mark.asyncio
class TestCreateDocMove:
    async def test_moves_when_parent_provided(self, _patch_move):
        msg = await _unwrap(docs_tools.create_doc)(
            _docs_service(), "u@example.com", "Title", parent_folder_id="FOLDER1"
        )
        assert _patch_move["move_calls"] == [
            (_patch_move["drive_sentinel"], "DOC1", "FOLDER1")
        ]
        assert _patch_move["entered"] and _patch_move["exited"]
        assert "FOLDER1" in msg

    async def test_no_secondary_service_when_omitted(self, _patch_move):
        await _unwrap(docs_tools.create_doc)(_docs_service(), "u@example.com", "Title")
        assert _patch_move["secondary_calls"] == []
        assert _patch_move["move_calls"] == []


@pytest.mark.asyncio
class TestCreatePresentationMove:
    async def test_moves_when_parent_provided(self, _patch_move):
        await _unwrap(slides_tools.create_presentation)(
            _slides_service(), "u@example.com", "Deck", parent_folder_id="FOLDER2"
        )
        assert _patch_move["move_calls"] == [
            (_patch_move["drive_sentinel"], "PRES1", "FOLDER2")
        ]

    async def test_no_secondary_service_when_omitted(self, _patch_move):
        await _unwrap(slides_tools.create_presentation)(
            _slides_service(), "u@example.com", "Deck"
        )
        assert _patch_move["secondary_calls"] == []


@pytest.mark.asyncio
class TestCreateFormMove:
    async def test_moves_when_parent_provided(self, _patch_move):
        await _unwrap(forms_tools.create_form)(
            _forms_service(), "u@example.com", "Survey", parent_folder_id="FOLDER3"
        )
        assert _patch_move["move_calls"] == [
            (_patch_move["drive_sentinel"], "FORM1", "FOLDER3")
        ]

    async def test_no_secondary_service_when_omitted(self, _patch_move):
        await _unwrap(forms_tools.create_form)(
            _forms_service(), "u@example.com", "Survey"
        )
        assert _patch_move["secondary_calls"] == []
