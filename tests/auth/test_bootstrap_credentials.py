"""Tests for bootstrap_credentials_from_env() in credential_store.py."""

import json
import os
import pytest
from unittest import mock

from auth.credential_store import (
    DEFAULT_SCOPES,
    bootstrap_credentials_from_env,
    get_credential_store,
)


@pytest.fixture(autouse=True)
def reset_credential_store():
    """Reset global credential store singleton between tests."""
    import auth.credential_store as mod

    mod._credential_store = None
    yield
    mod._credential_store = None


@pytest.fixture
def tmp_creds_dir(tmp_path):
    """Provide a temporary credentials directory."""
    return str(tmp_path / "credentials")


class TestBootstrapCredentialsFromEnv:
    """Tests for the bootstrap_credentials_from_env function."""

    def test_no_env_vars_set_does_nothing(self, tmp_creds_dir):
        """When neither GOOGLE_REFRESH_TOKEN nor USER_GOOGLE_EMAIL are set, nothing happens."""
        env = {"WORKSPACE_MCP_CREDENTIALS_DIR": tmp_creds_dir}
        with mock.patch.dict(os.environ, env, clear=True):
            bootstrap_credentials_from_env()
        assert not os.path.exists(tmp_creds_dir)

    def test_only_refresh_token_set_does_nothing(self, tmp_creds_dir):
        """When only GOOGLE_REFRESH_TOKEN is set (no email), nothing happens."""
        env = {
            "GOOGLE_REFRESH_TOKEN": "test-refresh-token",
            "WORKSPACE_MCP_CREDENTIALS_DIR": tmp_creds_dir,
        }
        with mock.patch.dict(os.environ, env, clear=True):
            bootstrap_credentials_from_env()
        assert not os.path.exists(tmp_creds_dir)

    def test_only_email_set_does_nothing(self, tmp_creds_dir):
        """When only USER_GOOGLE_EMAIL is set (no refresh token), nothing happens."""
        env = {
            "USER_GOOGLE_EMAIL": "user@example.com",
            "WORKSPACE_MCP_CREDENTIALS_DIR": tmp_creds_dir,
        }
        with mock.patch.dict(os.environ, env, clear=True):
            bootstrap_credentials_from_env()
        assert not os.path.exists(tmp_creds_dir)

    def test_writes_credential_file(self, tmp_creds_dir):
        """When both required env vars are set, writes the credential file."""
        env = {
            "GOOGLE_REFRESH_TOKEN": "my-refresh-token",
            "USER_GOOGLE_EMAIL": "user@example.com",
            "GOOGLE_OAUTH_CLIENT_ID": "my-client-id",
            "GOOGLE_OAUTH_CLIENT_SECRET": "my-client-secret",
            "WORKSPACE_MCP_CREDENTIALS_DIR": tmp_creds_dir,
        }
        with mock.patch.dict(os.environ, env, clear=True):
            bootstrap_credentials_from_env()

        cred_path = os.path.join(tmp_creds_dir, "user@example.com.json")
        assert os.path.exists(cred_path)

        with open(cred_path) as f:
            data = json.load(f)

        assert data["token"] == ""
        assert data["refresh_token"] == "my-refresh-token"
        assert data["token_uri"] == "https://oauth2.googleapis.com/token"
        assert data["client_id"] == "my-client-id"
        assert data["client_secret"] == "my-client-secret"
        assert data["scopes"] == DEFAULT_SCOPES
        assert data["expiry"] == "2020-01-01T00:00:00"

    def test_does_not_overwrite_existing_file(self, tmp_creds_dir):
        """If the credential file already exists, it should not be overwritten."""
        os.makedirs(tmp_creds_dir, exist_ok=True)
        cred_path = os.path.join(tmp_creds_dir, "user@example.com.json")
        original_data = {"token": "existing-access-token", "refresh_token": "old-token"}
        with open(cred_path, "w") as f:
            json.dump(original_data, f)

        env = {
            "GOOGLE_REFRESH_TOKEN": "new-refresh-token",
            "USER_GOOGLE_EMAIL": "user@example.com",
            "WORKSPACE_MCP_CREDENTIALS_DIR": tmp_creds_dir,
        }
        with mock.patch.dict(os.environ, env, clear=True):
            bootstrap_credentials_from_env()

        with open(cred_path) as f:
            data = json.load(f)

        assert data["token"] == "existing-access-token"
        assert data["refresh_token"] == "old-token"

    def test_uses_custom_scopes_from_env(self, tmp_creds_dir):
        """When GOOGLE_SCOPES is set, uses those scopes instead of defaults."""
        env = {
            "GOOGLE_REFRESH_TOKEN": "my-refresh-token",
            "USER_GOOGLE_EMAIL": "user@example.com",
            "GOOGLE_SCOPES": "https://www.googleapis.com/auth/drive,https://www.googleapis.com/auth/calendar",
            "WORKSPACE_MCP_CREDENTIALS_DIR": tmp_creds_dir,
        }
        with mock.patch.dict(os.environ, env, clear=True):
            bootstrap_credentials_from_env()

        cred_path = os.path.join(tmp_creds_dir, "user@example.com.json")
        with open(cred_path) as f:
            data = json.load(f)

        assert data["scopes"] == [
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/calendar",
        ]

    def test_defaults_client_id_and_secret_to_empty(self, tmp_creds_dir):
        """When client ID/secret env vars are not set, defaults to empty strings."""
        env = {
            "GOOGLE_REFRESH_TOKEN": "my-refresh-token",
            "USER_GOOGLE_EMAIL": "user@example.com",
            "WORKSPACE_MCP_CREDENTIALS_DIR": tmp_creds_dir,
        }
        with mock.patch.dict(os.environ, env, clear=True):
            bootstrap_credentials_from_env()

        cred_path = os.path.join(tmp_creds_dir, "user@example.com.json")
        with open(cred_path) as f:
            data = json.load(f)

        assert data["client_id"] == ""
        assert data["client_secret"] == ""

    def test_respects_workspace_mcp_credentials_dir(self, tmp_path):
        """Uses WORKSPACE_MCP_CREDENTIALS_DIR when set."""
        custom_dir = str(tmp_path / "custom_creds")
        env = {
            "GOOGLE_REFRESH_TOKEN": "token",
            "USER_GOOGLE_EMAIL": "user@example.com",
            "WORKSPACE_MCP_CREDENTIALS_DIR": custom_dir,
        }
        with mock.patch.dict(os.environ, env, clear=True):
            bootstrap_credentials_from_env()

        assert os.path.exists(os.path.join(custom_dir, "user@example.com.json"))

    def test_respects_google_mcp_credentials_dir_fallback(self, tmp_path):
        """Falls back to GOOGLE_MCP_CREDENTIALS_DIR when WORKSPACE_MCP_CREDENTIALS_DIR is not set."""
        legacy_dir = str(tmp_path / "legacy_creds")
        env = {
            "GOOGLE_REFRESH_TOKEN": "token",
            "USER_GOOGLE_EMAIL": "user@example.com",
            "GOOGLE_MCP_CREDENTIALS_DIR": legacy_dir,
        }
        with mock.patch.dict(os.environ, env, clear=True):
            bootstrap_credentials_from_env()

        assert os.path.exists(os.path.join(legacy_dir, "user@example.com.json"))

    def test_creates_directory_if_not_exists(self, tmp_creds_dir):
        """Creates the credentials directory if it doesn't exist."""
        assert not os.path.exists(tmp_creds_dir)

        env = {
            "GOOGLE_REFRESH_TOKEN": "token",
            "USER_GOOGLE_EMAIL": "user@example.com",
            "WORKSPACE_MCP_CREDENTIALS_DIR": tmp_creds_dir,
        }
        with mock.patch.dict(os.environ, env, clear=True):
            bootstrap_credentials_from_env()

        assert os.path.isdir(tmp_creds_dir)

    def test_get_credential_store_calls_bootstrap(self, tmp_creds_dir):
        """get_credential_store() should call bootstrap on first initialization."""
        env = {
            "GOOGLE_REFRESH_TOKEN": "token-from-store-test",
            "USER_GOOGLE_EMAIL": "store@example.com",
            "GOOGLE_OAUTH_CLIENT_ID": "cid",
            "GOOGLE_OAUTH_CLIENT_SECRET": "csecret",
            "WORKSPACE_MCP_CREDENTIALS_DIR": tmp_creds_dir,
        }
        with mock.patch.dict(os.environ, env, clear=True):
            store = get_credential_store()

        cred_path = os.path.join(tmp_creds_dir, "store@example.com.json")
        assert os.path.exists(cred_path)

        # Verify the credential can be loaded by the store
        cred = store.get_credential("store@example.com")
        assert cred is not None
        assert cred.refresh_token == "token-from-store-test"

    def test_scopes_env_strips_whitespace(self, tmp_creds_dir):
        """GOOGLE_SCOPES env var handles whitespace around commas."""
        env = {
            "GOOGLE_REFRESH_TOKEN": "token",
            "USER_GOOGLE_EMAIL": "user@example.com",
            "GOOGLE_SCOPES": " scope1 , scope2 , scope3 ",
            "WORKSPACE_MCP_CREDENTIALS_DIR": tmp_creds_dir,
        }
        with mock.patch.dict(os.environ, env, clear=True):
            bootstrap_credentials_from_env()

        cred_path = os.path.join(tmp_creds_dir, "user@example.com.json")
        with open(cred_path) as f:
            data = json.load(f)

        assert data["scopes"] == ["scope1", "scope2", "scope3"]
