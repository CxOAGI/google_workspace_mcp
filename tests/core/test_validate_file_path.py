import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from core.utils import _get_allowed_file_dirs, validate_file_path


def test_get_allowed_file_dirs_strips_whitespace(monkeypatch, tmp_path):
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()

    monkeypatch.setenv("ALLOWED_FILE_DIRS", f"  {allowed_dir}  ")

    assert _get_allowed_file_dirs() == [allowed_dir.resolve()]


def test_validate_file_path_blocks_dot_ssh_anywhere(monkeypatch, tmp_path):
    allowed_dir = tmp_path / "allowed"
    secret_dir = allowed_dir / "nested" / ".ssh"
    secret_dir.mkdir(parents=True)
    secret_file = secret_dir / "config"
    secret_file.write_text("host example", encoding="utf-8")

    monkeypatch.setenv("ALLOWED_FILE_DIRS", str(allowed_dir))

    with pytest.raises(ValueError, match="commonly contains secrets or credentials"):
        validate_file_path(str(secret_file))


def test_validate_file_path_blocks_dot_aws_anywhere(monkeypatch, tmp_path):
    allowed_dir = tmp_path / "allowed"
    secret_dir = allowed_dir / "team" / ".aws"
    secret_dir.mkdir(parents=True)
    secret_file = secret_dir / "credentials"
    secret_file.write_text("[default]", encoding="utf-8")

    monkeypatch.setenv("ALLOWED_FILE_DIRS", str(allowed_dir))

    with pytest.raises(ValueError, match="commonly contains secrets or credentials"):
        validate_file_path(str(secret_file))


def test_validate_file_path_blocks_dot_env_variant_anywhere(monkeypatch, tmp_path):
    allowed_dir = tmp_path / "allowed"
    secret_dir = allowed_dir / "nested"
    secret_dir.mkdir(parents=True)
    secret_file = secret_dir / ".env.production"
    secret_file.write_text("API_KEY=secret", encoding="utf-8")

    monkeypatch.setenv("ALLOWED_FILE_DIRS", str(allowed_dir))

    with pytest.raises(ValueError, match="\\.env files may contain secrets"):
        validate_file_path(str(secret_file))
