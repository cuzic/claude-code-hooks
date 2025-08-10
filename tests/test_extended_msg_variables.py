"""Tests for extended MSG variables (MSG3-MSG9) and regex function."""

import tempfile
from pathlib import Path

from claude_code_pushbullet_notify import (
    _apply_string_functions,
    _format_template,
    _get_template_variables,
)


class TestExtendedMsgVariables:
    """Test MSG3-MSG9 template variables."""

    def create_test_transcript(self, messages):
        """Create a test transcript file with given messages."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for msg in messages:
                # Create assistant message in transcript format
                line = {"type": "assistant", "message": {"role": "assistant", "content": msg}}
                import json

                f.write(json.dumps(line) + "\n")
            return f.name

    def test_msg_variables_up_to_msg9(self):
        """Test MSG0-MSG9 variables are extracted from transcript."""
        messages = [
            "Message 1",
            "Message 2", 
            "Message 3",
            "Message 4",
            "Message 5",
            "Message 6",
            "Message 7",
            "Message 8",
            "Message 9",
            "Message 10",
            "Message 11",
            "Message 12",
        ]

        transcript_path = self.create_test_transcript(messages)
        try:
            variables = _get_template_variables("repo", "branch", transcript_path)

            # MSG0 should be the latest (last in file)
            assert variables["MSG0"] == "Message 12"
            assert variables["MSG1"] == "Message 11"
            assert variables["MSG2"] == "Message 10"
            assert variables["MSG3"] == "Message 9"
            assert variables["MSG4"] == "Message 8"
            assert variables["MSG5"] == "Message 7"
            assert variables["MSG6"] == "Message 6"
            assert variables["MSG7"] == "Message 5"
            assert variables["MSG8"] == "Message 4"
            assert variables["MSG9"] == "Message 3"
        finally:
            Path(transcript_path).unlink()

    def test_msg_variables_with_fewer_than_10_messages(self):
        """Test MSG variables when transcript has fewer than 10 messages."""
        messages = ["Only message 1", "Only message 2", "Only message 3"]

        transcript_path = self.create_test_transcript(messages)
        try:
            variables = _get_template_variables("repo", "branch", transcript_path)

            assert variables["MSG0"] == "Only message 3"
            assert variables["MSG1"] == "Only message 2"
            assert variables["MSG2"] == "Only message 1"
            assert variables["MSG3"] == ""
            assert variables["MSG4"] == ""
            assert variables["MSG5"] == ""
            assert variables["MSG6"] == ""
            assert variables["MSG7"] == ""
            assert variables["MSG8"] == ""
            assert variables["MSG9"] == ""
        finally:
            Path(transcript_path).unlink()

    def test_template_with_extended_msg_variables(self):
        """Test template formatting with extended MSG variables."""
        messages = [f"Message {i}" for i in range(1, 11)]  # 10 messages
        transcript_path = self.create_test_transcript(messages)

        try:
            variables = _get_template_variables("test-repo", "main", transcript_path)
            template = "{GIT_REPO}: {MSG0} | {MSG5} | {MSG9}"
            result = _format_template(template, variables)

            assert result == "test-repo: Message 10 | Message 5 | Message 1"
        finally:
            Path(transcript_path).unlink()


class TestRegexFunction:
    """Test regex string function."""

    def test_regex_function_extract_number(self):
        """Test regex function extracting numbers."""
        text = "Version 1.2.3 is available"
        result = _apply_string_functions(f'{{regex({text}, "[0-9]+\\.[0-9]+\\.[0-9]+")}}')
        assert result == "1.2.3"

    def test_regex_function_extract_first_match(self):
        """Test regex function returns only first match."""
        text = "Error 404 and Error 500 occurred"
        result = _apply_string_functions(f'{{regex({text}, "Error [0-9]+")}}')
        assert result == "Error 404"

    def test_regex_function_no_match(self):
        """Test regex function when no match found."""
        text = "No numbers here"
        result = _apply_string_functions(f'{{regex({text}, "[0-9]+")}}')
        assert result == ""

    def test_regex_function_invalid_pattern(self):
        """Test regex function with invalid pattern."""
        text = "Some text"
        result = _apply_string_functions(f'{{regex({text}, "[")}}')  # Invalid regex
        assert result == ""

    def test_regex_function_with_variables(self):
        """Test regex function with template variables."""
        variables = {
            "MSG0": "Task completed in 2.5 seconds with 100% success",
            "MSG1": "Started processing at 14:30:25 UTC",
        }

        template = "Time: {regex(MSG0, [0-9]+\\.[0-9]+)} | Clock: {regex(MSG1, [0-9]{2}:[0-9]{2}:[0-9]{2})}"
        result = _format_template(template, variables)

        assert "Time: 2.5" in result
        assert "Clock: 14:30:25" in result

    def test_regex_function_extract_url(self):
        """Test regex function extracting URLs."""
        text = "Check out https://example.com/path for more info"
        result = _apply_string_functions(f'{{regex({text}, "https?://[^\\s]+")}}')
        assert result == "https://example.com/path"

    def test_regex_function_extract_email(self):
        """Test regex function extracting email addresses."""
        text = "Contact us at support@example.com or admin@test.org"
        result = _apply_string_functions(f'{{regex({text}, "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]+")}}')
        assert result == "support@example.com"

    def test_regex_function_with_quotes(self):
        """Test regex function with quoted patterns."""
        text = "Temperature: 25.6°C"
        result = _apply_string_functions(f'{{regex({text}, "[0-9]+\\.[0-9]+")}}')
        assert result == "25.6"

    def test_multiple_regex_functions(self):
        """Test multiple regex functions in same template."""
        variables = {
            "MSG0": "Build #123 completed at 2023-12-25",
            "MSG1": "Previous build #122 failed",
        }

        template = "Latest: #{regex(MSG0, [0-9]+)} on {regex(MSG0, [0-9]{4}-[0-9]{2}-[0-9]{2})} | Previous: #{regex(MSG1, [0-9]+)}"
        result = _format_template(template, variables)

        assert "Latest: #123 on 2023-12-25" in result
        assert "Previous: #122" in result

    def test_regex_with_special_characters(self):
        """Test regex function with special regex characters."""
        text = "File: /path/to/file.txt (size: 1024 bytes)"
        result = _apply_string_functions(f'{{regex({text}, "/[^\\s]+\\.txt")}}')
        assert result == "/path/to/file.txt"

    def test_regex_function_case_sensitive(self):
        """Test regex function is case sensitive by default."""
        text = "Status: SUCCESS and Error: failure"
        result = _apply_string_functions(f'{{regex({text}, "SUCCESS")}}')
        assert result == "SUCCESS"

        result = _apply_string_functions(f'{{regex({text}, "success")}}')
        assert result == ""

    def test_regex_function_with_whitespace_handling(self):
        """Test regex function with various spacing."""
        text = "RESULT"
        
        # With spaces around arguments
        result1 = _apply_string_functions(f'{{regex( {text} , "[A-Z]+" )}}')
        assert result1 == "RESULT"
        
        # Without spaces
        result2 = _apply_string_functions(f'{{regex({text},"[A-Z]+")}}')
        assert result2 == "RESULT"