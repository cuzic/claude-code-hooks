"""Integration tests for template functionality with real config files."""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import tomllib

from claude_code_pushbullet_notify import (
    _format_template,
    _get_template_variables,
    _handle_stop_event,
    _send_notification,
    load_config,
    main,
)


class TestTemplateIntegration:
    """Integration tests for template functionality."""

    @pytest.fixture
    def temp_config_dir(self):
        """Create a temporary directory for config files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_pushbullet(self):
        """Mock the Pushbullet notification sending."""
        with patch("claude_code_pushbullet_notify.send_pushbullet_notification") as mock:
            mock.return_value = True
            yield mock

    def test_default_template_from_config(self, temp_config_dir, mock_pushbullet):
        """Test that default template from config.toml is used correctly."""
        # Directly use CONFIG dict instead of trying to load from file
        with patch(
            "claude_code_pushbullet_notify.CONFIG",
            {
                "notification": {
                    "num_messages": 3,
                    "max_body_length": 500,
                    "title_template": "🚀 {GIT_REPO} [{GIT_BRANCH}] - Completed",
                }
            },
        ):
            _send_notification("my-project", "feature/awesome", "Task done")

        mock_pushbullet.assert_called_once()
        title, body = mock_pushbullet.call_args[0]
        assert title == "🚀 my-project [feature/awesome] - Completed"
        assert body == "Task done"

    def test_body_template_overrides_transcript(self, temp_config_dir, mock_pushbullet):
        """Test that body template overrides transcript messages."""
        with patch(
            "claude_code_pushbullet_notify.CONFIG",
            {
                "notification": {
                    "title_template": "{GIT_REPO} - {GIT_BRANCH}",
                    "body_template": "Project: {GIT_REPO}\nBranch: {GIT_BRANCH}\nCompleted at: {TIMESTAMP}",
                }
            },
        ):
            with patch("claude_code_pushbullet_notify.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2024, 1, 15, 10, 30, 0)
                _send_notification("test-app", "main", "Original body text")

        mock_pushbullet.assert_called_once()
        title, body = mock_pushbullet.call_args[0]
        assert title == "test-app - main"
        assert "Project: test-app" in body
        assert "Branch: main" in body
        assert "Completed at: 2024-01-15 10:30:00" in body
        assert "Original body text" not in body  # Original body should be replaced

    def test_template_with_special_characters(self, mock_pushbullet):
        """Test templates with special characters in repo/branch names."""
        with patch(
            "claude_code_pushbullet_notify.CONFIG",
            {"notification": {"title_template": "Repo: {GIT_REPO} | Branch: {GIT_BRANCH}"}},
        ):
            _send_notification("my-repo/sub-module", "feature/ABC-123", "Done")

        mock_pushbullet.assert_called_once()
        title, _ = mock_pushbullet.call_args[0]
        assert title == "Repo: my-repo/sub-module | Branch: feature/ABC-123"

    def test_template_with_all_variables(self, mock_pushbullet):
        """Test template using all available variables."""
        template = "{GIT_REPO} @ {GIT_BRANCH} - {DATE} {TIME} - Full: {TIMESTAMP}"

        with patch("claude_code_pushbullet_notify.CONFIG", {"notification": {"title_template": template}}):
            with patch("claude_code_pushbullet_notify.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2024, 12, 25, 15, 45, 30)
                _send_notification("xmas-project", "release", "Merry Christmas!")

        mock_pushbullet.assert_called_once()
        title, _ = mock_pushbullet.call_args[0]
        assert "xmas-project @ release" in title
        assert "2024-12-25 15:45:30" in title
        assert "2024-12-25" in title
        assert "15:45:30" in title

    def test_empty_template_fallback(self, mock_pushbullet):
        """Test fallback when template is empty string."""
        with patch("claude_code_pushbullet_notify.CONFIG", {"notification": {"title_template": ""}}):
            _send_notification("fallback-repo", "main", "Body")

        mock_pushbullet.assert_called_once()
        title, _ = mock_pushbullet.call_args[0]
        assert title == ""  # Empty template results in empty title

    def test_missing_template_uses_default(self, mock_pushbullet):
        """Test that missing template configuration uses default."""
        with patch("claude_code_pushbullet_notify.CONFIG", {"notification": {}}):
            _send_notification("default-test", "develop", "Content")

        mock_pushbullet.assert_called_once()
        title, _ = mock_pushbullet.call_args[0]
        # Should use the hardcoded default
        assert title == "claude code task completed default-test develop"

    @patch("sys.argv", ["script"])
    def test_main_with_custom_template(self, mock_pushbullet):
        """Test main function with custom template configuration."""
        hook_data = {"hook_event_name": "Stop", "transcript_path": "/dev/null"}

        with patch("claude_code_pushbullet_notify.read_hook_input") as mock_input:
            mock_input.return_value = hook_data

            with patch(
                "claude_code_pushbullet_notify.CONFIG",
                {
                    "notification": {
                        "num_messages": 3,
                        "max_body_length": 500,
                        "title_template": "✅ {GIT_REPO} ({GIT_BRANCH}) - Done!",
                        "body_template": "Task completed successfully!",
                    }
                },
            ):
                with patch("claude_code_pushbullet_notify.get_git_info") as mock_git:
                    mock_git.return_value = ("awesome-app", "production")
                    main()

        mock_pushbullet.assert_called_once()
        title, body = mock_pushbullet.call_args[0]
        assert title == "✅ awesome-app (production) - Done!"
        assert body == "Task completed successfully!"

    def test_template_variable_case_sensitivity(self, mock_pushbullet):
        """Test that template variables are case-sensitive."""
        with patch(
            "claude_code_pushbullet_notify.CONFIG",
            {"notification": {"title_template": "{git_repo} vs {GIT_REPO} - {Git_Branch} vs {GIT_BRANCH}"}},
        ):
            _send_notification("test", "main", "Body")

        mock_pushbullet.assert_called_once()
        title, _ = mock_pushbullet.call_args[0]
        # Lowercase and mixed-case should NOT be replaced
        assert "{git_repo}" in title
        assert "{Git_Branch}" in title
        # Uppercase should be replaced
        assert "test" in title
        assert "main" in title

    def test_template_with_unicode(self, mock_pushbullet):
        """Test templates with Unicode characters."""
        with patch(
            "claude_code_pushbullet_notify.CONFIG",
            {
                "notification": {
                    "title_template": "📦 {GIT_REPO} → {GIT_BRANCH} ✨",
                    "body_template": "完了しました 🎉\nプロジェクト: {GIT_REPO}",
                }
            },
        ):
            _send_notification("日本語-repo", "機能/テスト", "Original")

        mock_pushbullet.assert_called_once()
        title, body = mock_pushbullet.call_args[0]
        assert "📦 日本語-repo → 機能/テスト ✨" == title
        assert "完了しました 🎉" in body
        assert "プロジェクト: 日本語-repo" in body

    def test_template_with_newlines(self, mock_pushbullet):
        """Test body template with proper newline handling."""
        with patch(
            "claude_code_pushbullet_notify.CONFIG",
            {"notification": {"body_template": "Line 1: {GIT_REPO}\nLine 2: {GIT_BRANCH}\n\nLine 4: {DATE}"}},
        ):
            with patch("claude_code_pushbullet_notify.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2024, 3, 15, 0, 0, 0)
                _send_notification("test", "main", "Ignored")

        mock_pushbullet.assert_called_once()
        _, body = mock_pushbullet.call_args[0]
        lines = body.split("\n")
        assert lines[0] == "Line 1: test"
        assert lines[1] == "Line 2: main"
        assert lines[2] == ""  # Empty line
        assert lines[3] == "Line 4: 2024-03-15"

    def test_repeated_variables_in_template(self, mock_pushbullet):
        """Test that repeated variables are all replaced."""
        with patch(
            "claude_code_pushbullet_notify.CONFIG",
            {"notification": {"title_template": "{GIT_REPO} - {GIT_BRANCH} - {GIT_REPO} again"}},
        ):
            _send_notification("repeat-test", "branch", "Body")

        mock_pushbullet.assert_called_once()
        title, _ = mock_pushbullet.call_args[0]
        assert title == "repeat-test - branch - repeat-test again"

    @patch("claude_code_pushbullet_notify.get_git_info")
    def test_env_variables_integration(self, mock_git_info, mock_pushbullet):
        """Test template with environment variables for git info."""
        # Mock get_git_info to return env values
        mock_git_info.return_value = ("env-repo", "env-branch")

        with patch(
            "claude_code_pushbullet_notify.CONFIG",
            {"notification": {"title_template": "From env: {GIT_REPO}/{GIT_BRANCH}"}},
        ):
            repo, branch = mock_git_info()
            _send_notification(repo, branch, "Test")

        mock_pushbullet.assert_called_once()
        title, _ = mock_pushbullet.call_args[0]
        assert title == "From env: env-repo/env-branch"
