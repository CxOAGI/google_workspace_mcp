"""
Tests for the mode-conditional discovery-tool registration decorator
(core.server.full_drive_access_tool) and the resulting advertised tool list.
"""

import sys
import os

import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import auth.scopes as scopes_module
import core.server as core_server
from core.server import full_drive_access_tool


@pytest.fixture(autouse=True)
def _reset_mode():
    scopes_module._DRIVE_ACCESS_MODE_OVERRIDE = None
    yield
    scopes_module._DRIVE_ACCESS_MODE_OVERRIDE = None


def test_full_mode_registers_via_server_tool(monkeypatch):
    scopes_module.set_drive_access_mode("full")
    sentinel = object()
    inner = MagicMock(return_value=sentinel)
    server_tool = MagicMock(return_value=inner)
    monkeypatch.setattr(core_server.server, "tool", server_tool)

    async def my_tool():
        return "ok"

    decorated = full_drive_access_tool(title="X")(my_tool)

    server_tool.assert_called_once_with(title="X")
    inner.assert_called_once_with(my_tool)
    assert decorated is sentinel


def test_file_mode_skips_registration(monkeypatch):
    scopes_module.set_drive_access_mode("file")
    server_tool = MagicMock()
    monkeypatch.setattr(core_server.server, "tool", server_tool)

    async def my_tool():
        return "ok"

    decorated = full_drive_access_tool(title="X")(my_tool)

    server_tool.assert_not_called()
    # The function is returned unchanged so it stays importable/testable.
    assert decorated is my_tool


@pytest.mark.asyncio
async def test_advertised_tools_match_mode():
    """Registered tool set reflects the mode the modules were imported under."""
    import gdrive.drive_tools  # noqa: F401
    import gdocs.docs_tools  # noqa: F401
    import gsheets.sheets_tools  # noqa: F401

    tools = await core_server.server.list_tools(run_middleware=False)
    names = {t.name for t in tools}

    discovery = {
        "search_drive_files",
        "list_drive_items",
        "search_docs",
        "list_docs_in_folder",
        "list_spreadsheets",
    }
    id_addressed = {"get_drive_file_content", "create_doc", "create_drive_folder"}

    # Tests run with the default (file) mode, so discovery tools must be absent
    # while ID-addressed tools remain registered.
    assert not (discovery & names), discovery & names
    assert id_addressed <= names
