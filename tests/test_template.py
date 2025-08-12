"""Tests for notification template functionality."""

from datetime import datetime
from unittest.mock import patch

import pytest

from claude_code_pushbullet_notify.template import _format_template, _get_template_variables
from claude_code_pushbullet_notify.pushbullet import _send_notification


class TestTemplateFormatting:
    """Test template formatting functionality."""

    def test_format_template_basic(self):
        """Test basic template formatting."""
        template = "Repository: {GIT_REPO}, Branch: {GIT_BRANCH}"
        variables = {"GIT_REPO": "my-repo", "GIT_BRANCH": "main"}

        result = _format_template(template, variables)
        assert result == "Repository: my-repo, Branch: main"

    def test_format_template_multiple_occurrences(self):
        """Test template with multiple occurrences of same variable."""
        template = "{GIT_REPO} - {GIT_BRANCH} - {GIT_REPO}"
        variables = {"GIT_REPO": "test", "GIT_BRANCH": "dev"}

        result = _format_template(template, variables)
        assert result == "test - dev - test"

    def test_format_template_missing_variables(self):
        """Test template with variables not in the dictionary."""
        template = "{GIT_REPO} - {UNKNOWN_VAR}"
        variables = {"GIT_REPO": "repo"}

        result = _format_template(template, variables)
        assert result == "repo - {UNKNOWN_VAR}"

    def test_format_template_empty(self):
        """Test with empty template."""
        result = _format_template("", {"GIT_REPO": "repo"})
        assert result == ""

    def test_format_template_none(self):
        """Test with None template."""
        result = _format_template(None, {"GIT_REPO": "repo"})
        assert result is None

    def test_format_template_no_variables(self):
        """Test template without any variables."""
        template = "Static notification title"
        variables = {"GIT_REPO": "repo", "GIT_BRANCH": "main"}

        result = _format_template(template, variables)
        assert result == "Static notification title"


class TestTemplateVariables:
    """Test template variable generation."""

    @patch("claude_code_pushbullet_notify.template.datetime")
    def test_get_template_variables(self, mock_datetime):
        """Test getting all template variables."""
        mock_now = datetime(2024, 1, 15, 14, 30, 45)
        mock_datetime.now.return_value = mock_now

        variables = _get_template_variables("my-project", "feature-branch")

        assert variables["GIT_REPO"] == "my-project"
        assert variables["GIT_BRANCH"] == "feature-branch"
        assert variables["TIMESTAMP"] == "2024-01-15 14:30:45"
        assert variables["DATE"] == "2024-01-15"
        assert variables["TIME"] == "14:30:45"

    def test_get_template_variables_special_chars(self):
        """Test template variables with special characters."""
        variables = _get_template_variables("my-repo/sub", "feature/test-123")

        assert variables["GIT_REPO"] == "my-repo/sub"
        assert variables["GIT_BRANCH"] == "feature/test-123"


class TestNotificationWithTemplates:
    """Test notification sending with templates."""

    @patch("claude_code_pushbullet_notify.pushbullet.send_pushbullet_notification")
    @patch.dict("claude_code_pushbullet_notify.config.CONFIG", {
        "notification": {"title_template": "[{GIT_BRANCH}] {GIT_REPO} - Done"}
    })
    def test_send_notification_with_title_template(self, mock_send):
        """Test sending notification with custom title template."""
        mock_send.return_value = True

        _send_notification("awesome-project", "develop", "Task completed")

        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert args[0] == "[develop] awesome-project - Done"
        assert args[1] == "Task completed"

    @patch("claude_code_pushbullet_notify.pushbullet.send_pushbullet_notification")
    @patch.dict("claude_code_pushbullet_notify.config.CONFIG", {
        "notification": {
            "title_template": "Task completed: {GIT_REPO}",
            "body_template": "Repo: {GIT_REPO}\nBranch: {GIT_BRANCH}\nTime: {TIME}",
        }
    })
    def test_send_notification_with_body_template(self, mock_send):
        """Test sending notification with custom body template."""
        mock_send.return_value = True

        with patch("claude_code_pushbullet_notify.template.datetime") as mock_datetime:
            mock_now = datetime(2024, 1, 15, 14, 30, 45)
            mock_datetime.now.return_value = mock_now

            _send_notification("my-app", "main", "Original body")

        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert args[0] == "Task completed: my-app"
        assert "Repo: my-app" in args[1]
        assert "Branch: main" in args[1]
        assert "Time: 14:30:45" in args[1]

    @patch("claude_code_pushbullet_notify.pushbullet.send_pushbullet_notification")
    @patch.dict("claude_code_pushbullet_notify.config.CONFIG", {
        "notification": {}
    })
    def test_send_notification_no_template(self, mock_send):
        """Test sending notification without templates (fallback to default)."""
        mock_send.return_value = True

        _send_notification("default-repo", "master", "Task done")

        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert args[0] == "claude code task completed default-repo master"
        assert args[1] == "Task done"

    @patch("claude_code_pushbullet_notify.pushbullet.send_pushbullet_notification")
    @patch.dict("claude_code_pushbullet_notify.config.CONFIG", {
        "notification": {"title_template": "{GIT_REPO} - {DATE} {TIME}"}
    })
    @patch("claude_code_pushbullet_notify.template.datetime")
    def test_send_notification_with_timestamp(self, mock_datetime, mock_send):
        """Test notification with timestamp variables."""
        mock_now = datetime(2024, 3, 20, 9, 15, 30)
        mock_datetime.now.return_value = mock_now

        mock_send.return_value = True

        _send_notification("time-test", "main", "Body")

        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert args[0] == "time-test - 2024-03-20 09:15:30"

    @patch("claude_code_pushbullet_notify.pushbullet.send_pushbullet_notification")
    @patch.dict("claude_code_pushbullet_notify.config.CONFIG", {
        "notification": {"title_template": "Repo: {GIT_REPO} | Branch: {GIT_BRANCH}"}
    })
    def test_send_notification_escaping(self, mock_send):
        """Test that templates handle special characters correctly."""
        mock_send.return_value = True

        _send_notification("repo-with-dash", "feature/new-thing", "Done")

        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert args[0] == "Repo: repo-with-dash | Branch: feature/new-thing"
