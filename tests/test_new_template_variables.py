"""Tests for new template variables: HOSTNAME, USERNAME, CWD."""

import os
import socket
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claude_code_pushbullet_notify import (
    _format_template,
    _get_template_variables,
    _send_notification,
)


class TestNewTemplateVariables:
    """Test new template variables functionality."""

    def test_get_template_variables_includes_new_vars(self):
        """Test that _get_template_variables includes HOSTNAME, USERNAME, CWD, CWD_BASENAME."""
        variables = _get_template_variables("test-repo", "main")

        # Check all required keys are present
        assert "HOSTNAME" in variables
        assert "USERNAME" in variables
        assert "CWD" in variables
        assert "CWD_BASENAME" in variables

        # Check original variables still exist
        assert "GIT_REPO" in variables
        assert "GIT_BRANCH" in variables
        assert "TIMESTAMP" in variables
        assert "DATE" in variables
        assert "TIME" in variables

    @patch("socket.gethostname")
    def test_hostname_variable(self, mock_hostname):
        """Test HOSTNAME variable is correctly retrieved."""
        mock_hostname.return_value = "test-machine"

        variables = _get_template_variables("repo", "branch")
        assert variables["HOSTNAME"] == "test-machine"

    @patch("socket.gethostname")
    def test_hostname_fallback_on_error(self, mock_hostname):
        """Test HOSTNAME fallback when socket.gethostname fails."""
        mock_hostname.side_effect = Exception("Network error")

        variables = _get_template_variables("repo", "branch")
        assert variables["HOSTNAME"] == "unknown"

    @patch.dict("os.environ", {"USER": "testuser"})
    def test_username_from_user_env(self):
        """Test USERNAME from USER environment variable."""
        variables = _get_template_variables("repo", "branch")
        assert variables["USERNAME"] == "testuser"

    @patch.dict("os.environ", {"USERNAME": "winuser"}, clear=True)
    def test_username_from_username_env(self):
        """Test USERNAME from USERNAME environment variable (Windows)."""
        variables = _get_template_variables("repo", "branch")
        assert variables["USERNAME"] == "winuser"

    @patch.dict("os.environ", {"USER": "unixuser", "USERNAME": "winuser"})
    def test_username_prefers_user_over_username(self):
        """Test USERNAME prefers USER over USERNAME when both exist."""
        variables = _get_template_variables("repo", "branch")
        assert variables["USERNAME"] == "unixuser"

    @patch.dict("os.environ", {}, clear=True)
    def test_username_fallback(self):
        """Test USERNAME fallback when no environment variables set."""
        # Remove USER and USERNAME if they exist
        os.environ.pop("USER", None)
        os.environ.pop("USERNAME", None)

        variables = _get_template_variables("repo", "branch")
        assert variables["USERNAME"] == "unknown"

    @patch("os.getcwd")
    def test_cwd_variable(self, mock_getcwd):
        """Test CWD variable is correctly retrieved."""
        mock_getcwd.return_value = "/home/user/projects/myapp"

        variables = _get_template_variables("repo", "branch")
        assert variables["CWD"] == "/home/user/projects/myapp"

    def test_template_with_new_variables(self):
        """Test template formatting with new variables."""
        template = "{USERNAME}@{HOSTNAME}:{CWD} - {GIT_REPO}"
        variables = {"USERNAME": "john", "HOSTNAME": "dev-machine", "CWD": "/projects/app", "GIT_REPO": "myapp"}

        result = _format_template(template, variables)
        assert result == "john@dev-machine:/projects/app - myapp"

    @patch("claude_code_pushbullet_notify.send_pushbullet_notification")
    @patch("claude_code_pushbullet_notify.CONFIG")
    @patch("socket.gethostname")
    @patch("os.getcwd")
    @patch.dict("os.environ", {"USER": "alice"})
    def test_send_notification_with_all_new_variables(self, mock_getcwd, mock_hostname, mock_config, mock_send):
        """Test sending notification with template using all new variables."""
        mock_hostname.return_value = "workstation"
        mock_getcwd.return_value = "/home/alice/code"
        mock_config.get.return_value = {
            "title_template": "{USERNAME}@{HOSTNAME} - {GIT_REPO}",
            "body_template": "Working in: {CWD}\nBranch: {GIT_BRANCH}",
        }
        mock_send.return_value = True

        _send_notification("project", "feature", "ignored")

        mock_send.assert_called_once()
        title, body = mock_send.call_args[0]
        assert title == "alice@workstation - project"
        assert "Working in: /home/alice/code" in body
        assert "Branch: feature" in body

    def test_template_with_mixed_variables(self):
        """Test template with mix of old and new variables."""
        template = "{DATE} {TIME} - {USERNAME}@{HOSTNAME} - {GIT_REPO}/{GIT_BRANCH} in {CWD}"

        with patch("claude_code_pushbullet_notify.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 6, 15, 10, 30, 45)
            with patch("socket.gethostname") as mock_hostname:
                mock_hostname.return_value = "server"
                with patch.dict("os.environ", {"USER": "bob"}):
                    with patch("os.getcwd") as mock_cwd:
                        mock_cwd.return_value = "/workspace"

                        variables = _get_template_variables("app", "main")
                        result = _format_template(template, variables)

        expected = "2024-06-15 10:30:45 - bob@server - app/main in /workspace"
        assert result == expected

    @patch("claude_code_pushbullet_notify.send_pushbullet_notification")
    @patch("claude_code_pushbullet_notify.CONFIG")
    def test_cwd_with_spaces(self, mock_config, mock_send):
        """Test CWD variable with spaces in path."""
        mock_config.get.return_value = {"title_template": "Working in: {CWD}"}
        mock_send.return_value = True

        with patch("os.getcwd") as mock_cwd:
            mock_cwd.return_value = "/home/user/My Documents/Project Name"
            _send_notification("repo", "branch", "body")

        mock_send.assert_called_once()
        title, _ = mock_send.call_args[0]
        assert title == "Working in: /home/user/My Documents/Project Name"

    @patch("claude_code_pushbullet_notify.send_pushbullet_notification")
    @patch("claude_code_pushbullet_notify.CONFIG")
    def test_hostname_with_domain(self, mock_config, mock_send):
        """Test HOSTNAME variable with FQDN."""
        mock_config.get.return_value = {"title_template": "Host: {HOSTNAME}"}
        mock_send.return_value = True

        with patch("socket.gethostname") as mock_hostname:
            mock_hostname.return_value = "server.example.com"
            _send_notification("repo", "branch", "body")

        mock_send.assert_called_once()
        title, _ = mock_send.call_args[0]
        assert title == "Host: server.example.com"

    def test_all_variables_are_strings(self):
        """Test that all template variables are strings."""
        variables = _get_template_variables("repo", "branch")

        for key, value in variables.items():
            assert isinstance(value, str), f"{key} should be a string, got {type(value)}"

    @patch("os.getcwd")
    def test_cwd_basename_variable(self, mock_getcwd):
        """Test CWD_BASENAME variable is correctly extracted."""
        mock_getcwd.return_value = "/home/user/projects/my-awesome-project"

        variables = _get_template_variables("repo", "branch")
        assert variables["CWD_BASENAME"] == "my-awesome-project"

    @patch("os.getcwd")
    def test_cwd_basename_root_directory(self, mock_getcwd):
        """Test CWD_BASENAME for root directory."""
        mock_getcwd.return_value = "/"

        variables = _get_template_variables("repo", "branch")
        # os.path.basename("/") returns ""
        assert variables["CWD_BASENAME"] == ""

    @patch("os.getcwd")
    def test_cwd_basename_with_trailing_slash(self, mock_getcwd):
        """Test CWD_BASENAME with trailing slash in path."""
        mock_getcwd.return_value = "/home/user/project/"

        variables = _get_template_variables("repo", "branch")
        # Our implementation strips trailing slash before getting basename
        assert variables["CWD_BASENAME"] == "project"

    @patch("claude_code_pushbullet_notify.send_pushbullet_notification")
    @patch("claude_code_pushbullet_notify.CONFIG")
    @patch("os.getcwd")
    def test_template_with_cwd_basename(self, mock_getcwd, mock_config, mock_send):
        """Test template using CWD_BASENAME variable."""
        mock_getcwd.return_value = "/home/alice/development/super-app"
        mock_config.get.return_value = {"title_template": "Project: {CWD_BASENAME} - {GIT_REPO}"}
        mock_send.return_value = True

        _send_notification("repo", "branch", "body")

        mock_send.assert_called_once()
        title, _ = mock_send.call_args[0]
        assert title == "Project: super-app - repo"

    @patch("os.getcwd")
    def test_cwd_and_cwd_basename_relationship(self, mock_getcwd):
        """Test that CWD and CWD_BASENAME have correct relationship."""
        test_path = "/usr/local/bin/application"
        mock_getcwd.return_value = test_path

        variables = _get_template_variables("repo", "branch")
        assert variables["CWD"] == test_path
        assert variables["CWD_BASENAME"] == "application"
        assert variables["CWD"].endswith(variables["CWD_BASENAME"])
