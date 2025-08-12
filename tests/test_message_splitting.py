#!/usr/bin/env python3
"""Test message splitting functionality."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
from claude_code_pushbullet_notify import (
    _split_message_into_chunks,
    _add_part_numbers_to_title,
    send_split_notifications,
)


class TestMessageSplitting:
    """Test suite for message splitting functionality."""

    def test_split_message_short(self):
        """Test that short messages are not split."""
        message = "This is a short message."
        max_length = 100
        
        chunks = _split_message_into_chunks(message, max_length)
        
        assert len(chunks) == 1
        assert chunks[0] == message

    def test_split_message_exact_length(self):
        """Test message exactly at max length."""
        message = "a" * 100
        max_length = 100
        
        chunks = _split_message_into_chunks(message, max_length)
        
        assert len(chunks) == 1
        assert chunks[0] == message

    def test_split_message_long(self):
        """Test splitting a long message."""
        message = "This is a very long message that needs to be split. " * 20
        max_length = 100
        
        chunks = _split_message_into_chunks(message, max_length)
        
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= max_length

    def test_split_message_word_boundary(self):
        """Test that splitting happens at word boundaries."""
        message = "The quick brown fox jumps over the lazy dog. " * 10
        max_length = 50
        
        chunks = _split_message_into_chunks(message, max_length)
        
        # Check that no chunk ends with a partial word
        for chunk in chunks[:-1]:  # Exclude last chunk
            assert not chunk.rstrip().endswith(("Th", "qui", "bro", "fo", "jum", "ove", "laz", "do"))
            assert len(chunk) <= max_length

    def test_split_message_with_newlines(self):
        """Test splitting messages with newlines."""
        message = "Line 1\nLine 2\n" + "Very long line that needs splitting " * 10 + "\nLine 4"
        max_length = 50
        
        chunks = _split_message_into_chunks(message, max_length)
        
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= max_length

    def test_split_message_single_long_word(self):
        """Test handling of a single word longer than max length."""
        message = "a" * 150
        max_length = 100
        
        chunks = _split_message_into_chunks(message, max_length)
        
        assert len(chunks) == 2
        assert len(chunks[0]) == 100
        assert len(chunks[1]) == 50

    def test_split_message_japanese(self):
        """Test splitting Japanese text."""
        message = "これは日本語のテストメッセージです。" * 10
        max_length = 50
        
        chunks = _split_message_into_chunks(message, max_length)
        
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= max_length

    def test_split_message_with_emoji(self):
        """Test splitting text with emojis."""
        message = "Hello 😊 World 🌍 " * 10
        max_length = 50
        
        chunks = _split_message_into_chunks(message, max_length)
        
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= max_length

    def test_split_message_empty(self):
        """Test splitting empty message."""
        message = ""
        max_length = 100
        
        chunks = _split_message_into_chunks(message, max_length)
        
        assert len(chunks) == 0 or (len(chunks) == 1 and chunks[0] == "")

    def test_split_message_accounting_for_numbering(self):
        """Test that split accounts for numbering space."""
        # Account for "[10/10] " = 8 characters
        message = "a" * 200
        max_length = 100
        
        chunks = _split_message_into_chunks(message, max_length, reserve_space=8)
        
        assert len(chunks) >= 2
        # Each chunk should leave room for numbering
        for chunk in chunks:
            assert len(chunk) <= (max_length - 8)


class TestPartNumbering:
    """Test suite for adding part numbers to titles."""

    def test_add_part_numbers_single(self):
        """Test that single part doesn't get numbered."""
        title = "Test Title"
        
        result = _add_part_numbers_to_title(title, 1, 1)
        
        assert result == title

    def test_add_part_numbers_multiple(self):
        """Test adding part numbers to multiple parts."""
        title = "Test Title"
        
        result1 = _add_part_numbers_to_title(title, 1, 3)
        result2 = _add_part_numbers_to_title(title, 2, 3)
        result3 = _add_part_numbers_to_title(title, 3, 3)
        
        assert result1 == "[1/3] Test Title"
        assert result2 == "[2/3] Test Title"
        assert result3 == "[3/3] Test Title"

    def test_add_part_numbers_large(self):
        """Test part numbers with large counts."""
        title = "Test Title"
        
        result = _add_part_numbers_to_title(title, 10, 15)
        
        assert result == "[10/15] Test Title"

    def test_add_part_numbers_empty_title(self):
        """Test part numbers with empty title."""
        title = ""
        
        result = _add_part_numbers_to_title(title, 1, 2)
        
        assert result == "[1/2] "


class TestSplitNotifications:
    """Test suite for split notification sending."""

    @patch("claude_code_pushbullet_notify.send_pushbullet_notification")
    @patch.dict("claude_code_pushbullet_notify.CONFIG", {
        "notification": {"max_body_length": 100, "split_long_messages": True}
    })
    def test_send_split_notifications_short(self, mock_send):
        """Test that short messages are sent without splitting."""
        mock_send.return_value = True
        
        result = send_split_notifications("Test Title", "Short message")
        
        assert result is True
        mock_send.assert_called_once_with("Test Title", "Short message")

    @patch("claude_code_pushbullet_notify.send_pushbullet_notification")
    @patch.dict("claude_code_pushbullet_notify.CONFIG", {
        "notification": {"max_body_length": 50, "split_long_messages": True}
    })
    def test_send_split_notifications_long(self, mock_send):
        """Test that long messages are split and sent."""
        mock_send.return_value = True
        long_message = "This is a very long message that needs to be split. " * 5
        
        result = send_split_notifications("Test Title", long_message)
        
        assert result is True
        assert mock_send.call_count > 1
        # Check that titles have part numbers
        calls = mock_send.call_args_list
        assert "[1/" in calls[0][0][0]
        assert "[2/" in calls[1][0][0]

    @patch("claude_code_pushbullet_notify.send_pushbullet_notification")
    @patch.dict("claude_code_pushbullet_notify.CONFIG", {
        "notification": {"max_body_length": 50, "split_long_messages": False}
    })
    def test_send_split_notifications_disabled(self, mock_send):
        """Test that splitting is disabled when configured."""
        mock_send.return_value = True
        long_message = "This is a very long message that needs to be split. " * 5
        
        result = send_split_notifications("Test Title", long_message)
        
        assert result is True
        # Should send as single notification even if long
        mock_send.assert_called_once()

    @patch("time.sleep")
    @patch("claude_code_pushbullet_notify.send_pushbullet_notification")
    @patch.dict("claude_code_pushbullet_notify.CONFIG", {
        "notification": {"max_body_length": 50, "split_long_messages": True, "split_delay_ms": 500}
    })
    def test_send_split_notifications_with_delay(self, mock_send, mock_sleep):
        """Test that delay is applied between split notifications."""
        mock_send.return_value = True
        long_message = "This is a very long message that needs to be split. " * 5
        
        result = send_split_notifications("Test Title", long_message)
        
        assert result is True
        assert mock_send.call_count > 1
        # Check that sleep was called between notifications (but not after the last one)
        assert mock_sleep.call_count == mock_send.call_count - 1
        mock_sleep.assert_called_with(0.5)  # 500ms = 0.5s

    @patch("claude_code_pushbullet_notify.send_pushbullet_notification")
    @patch.dict("claude_code_pushbullet_notify.CONFIG", {
        "notification": {"max_body_length": 50, "split_long_messages": True}
    })
    def test_send_split_notifications_partial_failure(self, mock_send):
        """Test handling of partial send failures."""
        long_message = "This is a very long message that needs to be split. " * 10
        
        # Calculate expected number of chunks
        chunks = _split_message_into_chunks(long_message, 50, 8)
        num_chunks = len(chunks)
        
        # Create side effect list: First succeeds, second fails, rest succeed
        side_effects = [True] + [False] + [True] * (num_chunks - 2)
        mock_send.side_effect = side_effects
        
        result = send_split_notifications("Test Title", long_message)
        
        # Should return False if any part fails
        assert result is False
        assert mock_send.call_count == num_chunks

    @patch("claude_code_pushbullet_notify.send_pushbullet_notification")
    @patch.dict("claude_code_pushbullet_notify.CONFIG", {
        "notification": {"max_body_length": 100, "split_long_messages": True}
    })
    def test_send_split_notifications_empty_body(self, mock_send):
        """Test handling of empty body."""
        mock_send.return_value = True
        
        result = send_split_notifications("Test Title", "")
        
        assert result is True
        mock_send.assert_called_once_with("Test Title", "")

    @patch("claude_code_pushbullet_notify.send_pushbullet_notification")
    def test_send_split_notifications_explicit_params(self, mock_send):
        """Test with explicitly provided parameters."""
        mock_send.return_value = True
        long_message = "Test " * 50
        
        result = send_split_notifications(
            "Test Title", 
            long_message, 
            max_length=30, 
            split_enabled=True
        )
        
        assert result is True
        assert mock_send.call_count > 1
        # Check that each chunk is under 30 chars (minus numbering space)
        for call in mock_send.call_args_list:
            body = call[0][1]
            assert len(body) <= 30