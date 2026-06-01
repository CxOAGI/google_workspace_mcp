"""
Tests for the "file not connected to the app" error translation in
handle_http_errors (Task 4 of the drive.file access-mode work).
"""

import sys
import os

import pytest
from httplib2 import Response
from googleapiclient.errors import HttpError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from core.utils import handle_http_errors, _is_file_not_connected_error
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


class TestIsFileNotConnected:
    def test_404_notfound_is_not_connected(self):
        assert _is_file_not_connected_error(404, "File not found: abc")
        assert _is_file_not_connected_error(404, '{"reason": "notFound"}')

    def test_404_without_notfound_reason_is_not_translated(self):
        # A 404 that is not a Drive notFound (e.g. wrong endpoint) must not match.
        assert not _is_file_not_connected_error(404, "method not allowed somewhere")

    def test_403_insufficient_file_permissions(self):
        assert _is_file_not_connected_error(403, "insufficientFilePermissions")

    def test_403_generic_scope_is_not_translated(self):
        assert not _is_file_not_connected_error(403, "ACCESS_TOKEN_SCOPE_INSUFFICIENT")

    def test_403_generic_insufficient_permissions_not_translated(self):
        # Must not collide with the file-level reason substring.
        assert not _is_file_not_connected_error(403, "insufficientPermissions")

    def test_401_is_not_translated(self):
        assert not _is_file_not_connected_error(401, "invalid credentials")


@pytest.mark.asyncio
class TestHandleHttpErrorsTranslation:
    async def test_drive_404_translated_to_picker_message(self):
        @handle_http_errors("get_doc_content", service_type="drive")
        async def tool(user_google_email: str = "u@example.com"):
            raise _http_error(404, "File not found: XYZ")

        with pytest.raises(Exception) as exc:
            await tool()
        msg = str(exc.value)
        assert "isn't connected to the app" in msg
        assert "Drive file picker" in msg

    async def test_docs_403_file_permission_translated(self):
        @handle_http_errors("read_sheet_values", service_type="sheets")
        async def tool(user_google_email: str = "u@example.com"):
            raise _http_error(
                403, "The user does not have sufficient permissions for file"
            )

        with pytest.raises(Exception) as exc:
            await tool()
        assert "isn't connected to the app" in str(exc.value)

    async def test_generic_403_uses_reauth_path_not_picker(self):
        @handle_http_errors("get_doc_content", service_type="drive")
        async def tool(user_google_email: str = "u@example.com"):
            raise _http_error(403, "ACCESS_TOKEN_SCOPE_INSUFFICIENT")

        with pytest.raises(Exception) as exc:
            await tool()
        msg = str(exc.value)
        assert "isn't connected to the app" not in msg
        assert "re-authenticate" in msg

    async def test_non_file_service_404_not_translated(self):
        @handle_http_errors("list_events", service_type="calendar")
        async def tool(user_google_email: str = "u@example.com"):
            raise _http_error(404, "Not Found")

        with pytest.raises(Exception) as exc:
            await tool()
        assert "isn't connected to the app" not in str(exc.value)

    async def test_forms_subresource_404_not_translated(self):
        # H1 guard: a 404 on a form RESPONSE id must not become a picker prompt.
        @handle_http_errors("get_form_response", service_type="forms")
        async def tool(user_google_email: str = "u@example.com"):
            raise _http_error(404, "Requested entity was not found.")

        with pytest.raises(Exception) as exc:
            await tool()
        assert "Drive file picker" not in str(exc.value)

    async def test_script_subresource_404_not_translated(self):
        @handle_http_errors("get_version", service_type="script")
        async def tool(user_google_email: str = "u@example.com"):
            raise _http_error(404, "Version not found")

        with pytest.raises(Exception) as exc:
            await tool()
        assert "Drive file picker" not in str(exc.value)

    async def test_404_without_notfound_reason_not_translated(self):
        @handle_http_errors("get_doc_content", service_type="docs")
        async def tool(user_google_email: str = "u@example.com"):
            raise _http_error(404, "Method not allowed")

        with pytest.raises(Exception) as exc:
            await tool()
        assert "Drive file picker" not in str(exc.value)

    async def test_file_mode_message_includes_resource_id(self):
        set_drive_access_mode("file")

        @handle_http_errors("get_doc_content", service_type="docs")
        async def tool(document_id: str, user_google_email: str = "u@example.com"):
            raise _http_error(404, "File not found")

        with pytest.raises(Exception) as exc:
            await tool(document_id="DOC123")
        msg = str(exc.value)
        assert "isn't connected to the app" in msg
        assert "DOC123" in msg
        assert "Drive file picker" in msg

    async def test_full_mode_uses_plain_message_not_picker(self):
        # M1 guard: in full mode the picker is the wrong remediation.
        set_drive_access_mode("full")

        @handle_http_errors("get_doc_content", service_type="docs")
        async def tool(document_id: str, user_google_email: str = "u@example.com"):
            raise _http_error(404, "File not found")

        with pytest.raises(Exception) as exc:
            await tool(document_id="DOC123")
        msg = str(exc.value)
        assert "Drive file picker" not in msg
        assert "isn't accessible" in msg
        assert "DOC123" in msg
