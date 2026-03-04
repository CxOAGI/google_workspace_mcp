"""
Credential Store API for Google Workspace MCP

This module provides a standardized interface for credential storage and retrieval,
supporting multiple backends configurable via environment variables.
"""

import os
import json
import logging
from abc import ABC, abstractmethod
from typing import Optional, List
from datetime import datetime
from google.oauth2.credentials import Credentials

DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/tasks",
]

logger = logging.getLogger(__name__)


class CredentialStore(ABC):
    """Abstract base class for credential storage."""

    @abstractmethod
    def get_credential(self, user_email: str) -> Optional[Credentials]:
        """
        Get credentials for a user by email.

        Args:
            user_email: User's email address

        Returns:
            Google Credentials object or None if not found
        """
        pass

    @abstractmethod
    def store_credential(self, user_email: str, credentials: Credentials) -> bool:
        """
        Store credentials for a user.

        Args:
            user_email: User's email address
            credentials: Google Credentials object to store

        Returns:
            True if successfully stored, False otherwise
        """
        pass

    @abstractmethod
    def delete_credential(self, user_email: str) -> bool:
        """
        Delete credentials for a user.

        Args:
            user_email: User's email address

        Returns:
            True if successfully deleted, False otherwise
        """
        pass

    @abstractmethod
    def list_users(self) -> List[str]:
        """
        List all users with stored credentials.

        Returns:
            List of user email addresses
        """
        pass


class LocalDirectoryCredentialStore(CredentialStore):
    """Credential store that uses local JSON files for storage."""

    def __init__(self, base_dir: Optional[str] = None):
        """
        Initialize the local JSON credential store.

        Args:
            base_dir: Base directory for credential files. If None, uses the directory
                     configured by environment variables in this order:
                     1. WORKSPACE_MCP_CREDENTIALS_DIR (preferred)
                     2. GOOGLE_MCP_CREDENTIALS_DIR (backward compatibility)
                     3. ~/.google_workspace_mcp/credentials (default)
        """
        if base_dir is None:
            # Check WORKSPACE_MCP_CREDENTIALS_DIR first (preferred)
            workspace_creds_dir = os.getenv("WORKSPACE_MCP_CREDENTIALS_DIR")
            google_creds_dir = os.getenv("GOOGLE_MCP_CREDENTIALS_DIR")

            if workspace_creds_dir:
                base_dir = os.path.expanduser(workspace_creds_dir)
                logger.info(
                    f"Using credentials directory from WORKSPACE_MCP_CREDENTIALS_DIR: {base_dir}"
                )
            # Fall back to GOOGLE_MCP_CREDENTIALS_DIR for backward compatibility
            elif google_creds_dir:
                base_dir = os.path.expanduser(google_creds_dir)
                logger.info(
                    f"Using credentials directory from GOOGLE_MCP_CREDENTIALS_DIR: {base_dir}"
                )
            else:
                home_dir = os.path.expanduser("~")
                if home_dir and home_dir != "~":
                    base_dir = os.path.join(
                        home_dir, ".google_workspace_mcp", "credentials"
                    )
                else:
                    base_dir = os.path.join(os.getcwd(), ".credentials")
                logger.info(f"Using default credentials directory: {base_dir}")

        self.base_dir = base_dir
        logger.info(
            f"LocalDirectoryCredentialStore initialized with base_dir: {base_dir}"
        )

    def _get_credential_path(self, user_email: str) -> str:
        """Get the file path for a user's credentials."""
        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir)
            logger.info(f"Created credentials directory: {self.base_dir}")
        return os.path.join(self.base_dir, f"{user_email}.json")

    def get_credential(self, user_email: str) -> Optional[Credentials]:
        """Get credentials from local JSON file."""
        creds_path = self._get_credential_path(user_email)

        if not os.path.exists(creds_path):
            logger.debug(f"No credential file found for {user_email} at {creds_path}")
            return None

        try:
            with open(creds_path, "r") as f:
                creds_data = json.load(f)

            # Parse expiry if present
            expiry = None
            if creds_data.get("expiry"):
                try:
                    expiry = datetime.fromisoformat(creds_data["expiry"])
                    # Ensure timezone-naive datetime for Google auth library compatibility
                    if expiry.tzinfo is not None:
                        expiry = expiry.replace(tzinfo=None)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Could not parse expiry time for {user_email}: {e}")

            credentials = Credentials(
                token=creds_data.get("token"),
                refresh_token=creds_data.get("refresh_token"),
                token_uri=creds_data.get("token_uri"),
                client_id=creds_data.get("client_id"),
                client_secret=creds_data.get("client_secret"),
                scopes=creds_data.get("scopes"),
                expiry=expiry,
            )

            logger.debug(f"Loaded credentials for {user_email} from {creds_path}")
            return credentials

        except (IOError, json.JSONDecodeError, KeyError) as e:
            logger.error(
                f"Error loading credentials for {user_email} from {creds_path}: {e}"
            )
            return None

    def store_credential(self, user_email: str, credentials: Credentials) -> bool:
        """Store credentials to local JSON file."""
        creds_path = self._get_credential_path(user_email)

        creds_data = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": credentials.scopes,
            "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
        }

        try:
            with open(creds_path, "w") as f:
                json.dump(creds_data, f, indent=2)
            logger.info(f"Stored credentials for {user_email} to {creds_path}")
            return True
        except IOError as e:
            logger.error(
                f"Error storing credentials for {user_email} to {creds_path}: {e}"
            )
            return False

    def delete_credential(self, user_email: str) -> bool:
        """Delete credential file for a user."""
        creds_path = self._get_credential_path(user_email)

        try:
            if os.path.exists(creds_path):
                os.remove(creds_path)
                logger.info(f"Deleted credentials for {user_email} from {creds_path}")
                return True
            else:
                logger.debug(
                    f"No credential file to delete for {user_email} at {creds_path}"
                )
                return True  # Consider it a success if file doesn't exist
        except IOError as e:
            logger.error(
                f"Error deleting credentials for {user_email} from {creds_path}: {e}"
            )
            return False

    def list_users(self) -> List[str]:
        """List all users with credential files."""
        if not os.path.exists(self.base_dir):
            return []

        users = []
        non_credential_files = {"oauth_states"}
        try:
            for filename in os.listdir(self.base_dir):
                if filename.endswith(".json"):
                    user_email = filename[:-5]  # Remove .json extension
                    if user_email in non_credential_files or "@" not in user_email:
                        continue
                    users.append(user_email)
            logger.debug(
                f"Found {len(users)} users with credentials in {self.base_dir}"
            )
        except OSError as e:
            logger.error(f"Error listing credential files in {self.base_dir}: {e}")

        return sorted(users)


# Global credential store instance
_credential_store: Optional[CredentialStore] = None


def bootstrap_credentials_from_env() -> None:
    """
    Bootstrap credential file from environment variables for headless/container deployments.

    If GOOGLE_REFRESH_TOKEN and USER_GOOGLE_EMAIL are set, writes a credential JSON file
    to the credential store directory (only if the file does not already exist).
    This allows the existing auth flow to pick up the credentials and refresh them on first use.
    """
    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
    user_email = os.getenv("USER_GOOGLE_EMAIL")

    if not refresh_token or not user_email:
        return

    # Resolve credentials directory using the same precedence as LocalDirectoryCredentialStore
    workspace_creds_dir = os.getenv("WORKSPACE_MCP_CREDENTIALS_DIR")
    google_creds_dir = os.getenv("GOOGLE_MCP_CREDENTIALS_DIR")

    if workspace_creds_dir:
        base_dir = os.path.expanduser(workspace_creds_dir)
    elif google_creds_dir:
        base_dir = os.path.expanduser(google_creds_dir)
    else:
        home_dir = os.path.expanduser("~")
        if home_dir and home_dir != "~":
            base_dir = os.path.join(home_dir, ".google_workspace_mcp", "credentials")
        else:
            base_dir = os.path.join(os.getcwd(), ".credentials")

    cred_path = os.path.join(base_dir, f"{user_email}.json")

    if os.path.exists(cred_path):
        logger.info(
            f"Credential file already exists for {user_email}, skipping env bootstrap"
        )
        return

    # Resolve scopes from env or use defaults
    scopes_env = os.getenv("GOOGLE_SCOPES")
    if scopes_env:
        scopes = [s.strip() for s in scopes_env.split(",") if s.strip()]
    else:
        scopes = list(DEFAULT_SCOPES)

    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")

    cred_data = {
        "token": "",
        "refresh_token": refresh_token,
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": scopes,
        "expiry": "2020-01-01T00:00:00",
    }

    try:
        os.makedirs(base_dir, exist_ok=True)
        with open(cred_path, "w") as f:
            json.dump(cred_data, f, indent=2)
        logger.info(
            f"Bootstrapped credentials from environment variables for {user_email}"
        )
    except OSError as e:
        logger.error(f"Failed to bootstrap credentials from environment: {e}")


def get_credential_store() -> CredentialStore:
    """
    Get the global credential store instance.

    Returns:
        Configured credential store instance
    """
    global _credential_store

    if _credential_store is None:
        bootstrap_credentials_from_env()
        # always use LocalJsonCredentialStore as the default
        # Future enhancement: support other backends via environment variables
        _credential_store = LocalDirectoryCredentialStore()
        logger.info(f"Initialized credential store: {type(_credential_store).__name__}")

    return _credential_store


def set_credential_store(store: CredentialStore):
    """
    Set the global credential store instance.

    Args:
        store: Credential store instance to use
    """
    global _credential_store
    _credential_store = store
    logger.info(f"Set credential store: {type(store).__name__}")
