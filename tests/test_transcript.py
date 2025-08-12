#!/usr/bin/env python3
"""Test transcript reading functionality."""

import pytest
from unittest.mock import patch, mock_open, MagicMock
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from claude_code_pushbullet_notify.transcript import get_last_messages_from_transcript


class TestTranscriptReading:
    """Test suite for transcript reading functionality."""

    @patch("pathlib.Path.exists")
    def test_get_last_messages_empty_file(self, mock_exists):
        """Test handling of empty transcript file."""
        mock_exists.return_value = True
        with patch("builtins.open", mock_open(read_data="")):
            result = get_last_messages_from_transcript("dummy.jsonl")
            assert result == "Task completed."

    @patch("pathlib.Path.exists")
    def test_get_last_messages_single_message(self, mock_exists):
        """Test extracting a single assistant message."""
        mock_exists.return_value = True
        transcript_data = (
            '{"type": "assistant", "message": {"role": "assistant", "content": "Hello, world!"}}\n'
            '{"type": "user", "message": {"role": "user", "content": "Hi there"}}\n'
        )
        with patch("builtins.open", mock_open(read_data=transcript_data)):
            result = get_last_messages_from_transcript("dummy.jsonl", num_lines=1)
            assert "Hello, world!" in result
            assert "Hi there" not in result

    @patch("pathlib.Path.exists")
    def test_get_last_messages_multiple_messages(self, mock_exists):
        """Test extracting multiple assistant messages."""
        mock_exists.return_value = True
        transcript_data = (
            '{"type": "assistant", "message": {"role": "assistant", "content": "First message"}}\n'
            '{"type": "user", "message": {"role": "user", "content": "User input"}}\n'
            '{"type": "assistant", "message": {"role": "assistant", "content": "Second message"}}\n'
            '{"type": "assistant", "message": {"role": "assistant", "content": "Third message"}}\n'
        )
        with patch("builtins.open", mock_open(read_data=transcript_data)):
            result = get_last_messages_from_transcript("dummy.jsonl", num_lines=2)
            assert "Second message" in result
            assert "Third message" in result
            assert "First message" not in result

    @patch("pathlib.Path.exists")
    def test_get_last_messages_truncation(self, mock_exists):
        """Test message truncation when exceeding max length."""
        mock_exists.return_value = True
        long_message = "A" * 1000
        transcript_data = (
            f'{{"type": "assistant", "message": {{"role": "assistant", "content": "{long_message}"}}}}\n'
        )
        with patch("builtins.open", mock_open(read_data=transcript_data)):
            # max_length is handled by CONFIG, not a parameter
            from unittest.mock import patch as config_patch
            with config_patch.dict('claude_code_pushbullet_notify.config.CONFIG', {
                'notification': {
                    'max_body_length': 100,
                    'num_messages': 3,
                    'split_long_messages': True  # With splitting enabled, no truncation
                }
            }):
                result = get_last_messages_from_transcript("dummy.jsonl")
                # When splitting is enabled, full message is returned (truncation happens during send)
                assert len(result) == 1000

    @patch("pathlib.Path.exists")
    def test_get_last_messages_invalid_json(self, mock_exists):
        """Test handling of invalid JSON lines."""
        mock_exists.return_value = True
        transcript_data = (
            'invalid json line\n'
            '{"type": "assistant", "message": {"role": "assistant", "content": "Valid message"}}\n'
        )
        with patch("builtins.open", mock_open(read_data=transcript_data)):
            result = get_last_messages_from_transcript("dummy.jsonl")
            assert "Valid message" in result

    @patch("pathlib.Path.exists")
    def test_get_last_messages_non_message_entries(self, mock_exists):
        """Test filtering of non-message entries."""
        mock_exists.return_value = True
        transcript_data = (
            '{"type": "tool_use", "content": "tool data"}\n'
            '{"type": "assistant", "message": {"role": "assistant", "content": "Assistant message"}}\n'
            '{"type": "event", "data": "event data"}\n'
        )
        with patch("builtins.open", mock_open(read_data=transcript_data)):
            result = get_last_messages_from_transcript("dummy.jsonl")
            assert "Assistant message" in result
            assert "tool data" not in result
            assert "event data" not in result

    def test_get_last_messages_file_not_found(self):
        """Test handling of missing transcript file."""
        result = get_last_messages_from_transcript("nonexistent.jsonl")
        assert result == "completed."
    
    @patch("pathlib.Path.exists")
    def test_get_last_messages_list_content(self, mock_exists):
        """Test handling of list content format."""
        mock_exists.return_value = True
        transcript_data = (
            '{"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Message from list"}]}}\n'
        )
        with patch("builtins.open", mock_open(read_data=transcript_data)):
            result = get_last_messages_from_transcript("dummy.jsonl")
            assert "Message from list" in result