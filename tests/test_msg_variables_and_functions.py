"""Tests for MSG variables and string functions."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claude_code_pushbullet_notify.template import (
    _apply_string_functions,
    _format_template,
    _get_template_variables,
)
from claude_code_pushbullet_notify.pushbullet import _send_notification


class TestMsgVariables:
    """Test MSG0, MSG1, MSG2 template variables."""

    def create_test_transcript(self, messages):
        """Create a test transcript file with given messages."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for msg in messages:
                # Create assistant message in transcript format
                line = {"type": "assistant", "message": {"role": "assistant", "content": msg}}
                import json

                f.write(json.dumps(line) + "\n")
            return f.name

    def test_msg_variables_from_transcript(self):
        """Test MSG0, MSG1, MSG2 variables are extracted from transcript."""
        messages = [
            "First message in transcript",
            "Second message in transcript",
            "Third message in transcript",
            "Fourth message in transcript",
        ]

        transcript_path = self.create_test_transcript(messages)
        try:
            variables = _get_template_variables("repo", "branch", transcript_path)

            # MSG0 should be the latest (last in file)
            assert variables["MSG0"] == "Fourth message in transcript"
            assert variables["MSG1"] == "Third message in transcript"
            assert variables["MSG2"] == "Second message in transcript"
        finally:
            Path(transcript_path).unlink()

    def test_msg_variables_with_fewer_messages(self):
        """Test MSG variables when transcript has fewer than 3 messages."""
        messages = ["Only one message"]

        transcript_path = self.create_test_transcript(messages)
        try:
            variables = _get_template_variables("repo", "branch", transcript_path)

            assert variables["MSG0"] == "Only one message"
            assert variables["MSG1"] == ""
            assert variables["MSG2"] == ""
        finally:
            Path(transcript_path).unlink()

    def test_msg_variables_no_transcript(self):
        """Test MSG variables when no transcript is provided."""
        variables = _get_template_variables("repo", "branch", None)

        assert variables["MSG0"] == ""
        assert variables["MSG1"] == ""
        assert variables["MSG2"] == ""

    def test_msg_variables_nonexistent_transcript(self):
        """Test MSG variables when transcript file doesn't exist."""
        variables = _get_template_variables("repo", "branch", "/nonexistent/file.jsonl")

        assert variables["MSG0"] == ""
        assert variables["MSG1"] == ""
        assert variables["MSG2"] == ""

    def test_template_with_msg_variables(self):
        """Test template formatting with MSG variables."""
        messages = ["Latest update", "Previous update", "Older update"]
        transcript_path = self.create_test_transcript(messages)

        try:
            variables = _get_template_variables("test-repo", "main", transcript_path)
            template = "{GIT_REPO}: {MSG0}"
            result = _format_template(template, variables)

            assert result == "test-repo: Older update"
        finally:
            Path(transcript_path).unlink()


class TestStringFunctions:
    """Test truncate and substr string functions."""

    def create_test_transcript(self, messages):
        """Create a test transcript file with given messages."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for msg in messages:
                # Create assistant message in transcript format
                line = {"type": "assistant", "message": {"role": "assistant", "content": msg}}
                import json

                f.write(json.dumps(line) + "\n")
            return f.name

    def test_truncate_function(self):
        """Test truncate function in templates."""
        text = "This is a very long message that needs to be truncated"
        result = _apply_string_functions(f"{{truncate({text}, 20)}}")
        assert result == "This is a very lo..."

    def test_truncate_short_text(self):
        """Test truncate when text is shorter than limit."""
        text = "Short"
        result = _apply_string_functions(f"{{truncate({text}, 20)}}")
        assert result == "Short"

    def test_substr_function(self):
        """Test substr function in templates."""
        # Test with actual string in the function call
        result = _apply_string_functions("{substr(Hello, World!, 7, 5)}")
        assert result == "World"

    def test_substr_from_start(self):
        """Test substr from beginning."""
        text = "Testing substring"
        result = _apply_string_functions(f"{{substr({text}, 0, 7)}}")
        assert result == "Testing"

    def test_multiple_functions(self):
        """Test multiple functions in same template."""
        text1 = "First long text that needs truncation"
        text2 = "Second text for substring"

        template = f"{{truncate({text1}, 15)}} | {{substr({text2}, 7, 4)}}"
        result = _apply_string_functions(template)

        assert result == "First long t... | text"

    def test_functions_with_variables(self):
        """Test string functions with template variables."""
        variables = {
            "MSG0": "This is a very long message that should be truncated",
            "CWD": "/home/user/very/long/path/to/project",
        }

        # Note: In actual usage, _format_template handles this properly
        # This tests the _format_template function directly
        template = "Message: {truncate(MSG0, 25)}\nPath: {substr(CWD, 0, 15)}"
        result = _format_template(template, variables)

        assert "This is a very long me..." in result
        assert "/home/user/very" in result

    def test_nested_function_patterns(self):
        """Test that functions work with various spacing."""
        text = "Test text"

        # With spaces
        result1 = _apply_string_functions(f"{{truncate( {text} , 5 )}}")
        assert result1 == "Te..."

        # Without spaces
        result2 = _apply_string_functions(f"{{truncate({text},5)}}")
        assert result2 == "Te..."

    @patch("claude_code_pushbullet_notify.pushbullet.send_split_notifications")
    @patch.dict("claude_code_pushbullet_notify.config.CONFIG", {
        "notification": {
            "title_template": "{GIT_REPO}: {truncate(MSG0, 30)}",
            "body_template": "Latest: {MSG0}\nPrevious: {truncate(MSG1, 20)}",
        }
    })
    def test_integration_msg_and_functions(self, mock_send):
        """Test integration of MSG variables with string functions."""
        messages = [
            "This is the first very long message that contains a lot of information",
            "Second message",
            "Third message",
        ]

        transcript_path = self.create_test_transcript(messages)

        try:
            mock_send.return_value = True

            _send_notification("my-repo", "main", "ignored", transcript_path)

            mock_send.assert_called_once()
            title, body = mock_send.call_args[0]

            # Check title has truncated MSG0
            assert "my-repo:" in title
            assert "Third message" in title  # MSG0 is the latest (third)

            # Check body
            assert "Latest: Third message" in body
            assert "Previous: Second message" in body
        finally:
            Path(transcript_path).unlink()

    def test_format_template_full_integration(self):
        """Test full integration of variables and functions."""
        messages = ["Latest assistant response", "Previous response", "Older response"]
        transcript_path = self.create_test_transcript(messages)

        try:
            variables = _get_template_variables("test-repo", "main", transcript_path)

            template = """
Repository: {GIT_REPO}
Branch: {GIT_BRANCH}
Latest: {truncate(MSG0, 20)}
Previous: {substr(MSG1, 0, 10)}
"""

            result = _format_template(template, variables)

            assert "Repository: test-repo" in result
            assert "Branch: main" in result
            assert "Latest: Older response" in result  # MSG0 is last in file
            assert "Previous: Previous r" in result  # First 10 chars of MSG1
        finally:
            Path(transcript_path).unlink()

    def test_create_test_transcript(self):
        """Ensure test helper creates valid transcript."""
        messages = ["Test message"]
        transcript_path = self.create_test_transcript(messages)

        try:
            assert Path(transcript_path).exists()

            with open(transcript_path) as f:
                import json

                line = json.loads(f.readline())
                assert line["type"] == "assistant"
                assert line["message"]["content"] == "Test message"
        finally:
            Path(transcript_path).unlink()
