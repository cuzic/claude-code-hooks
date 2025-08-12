#!/usr/bin/env python3
"""Test Pushbullet notification functionality."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from claude_code_pushbullet_notify.pushbullet import main, send_pushbullet_notification


class TestPushbulletNotification:
    """Test suite for Pushbullet notification functionality."""

    @patch("claude_code_pushbullet_notify.pushbullet.subprocess.run")
    def test_send_notification_with_curl(self, mock_subprocess):
        """Test notification sending using curl fallback."""
        mock_subprocess.return_value.returncode = 0

        # Mock requests to not exist, forcing curl fallback
        with patch.dict("sys.modules", {"requests": None}):
            with patch.dict("os.environ", {"PUSHBULLET_TOKEN": "test_token"}):
                result = send_pushbullet_notification("Test Title", "Test Body")

        assert result is True
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        assert "curl" in call_args
        assert "test_token" in str(call_args)

    @patch("claude_code_pushbullet_notify.pushbullet.subprocess.run")
    def test_send_notification_failure_curl(self, mock_subprocess):
        """Test notification sending failure with curl."""
        mock_subprocess.return_value.returncode = 1

        with patch.dict("os.environ", {"PUSHBULLET_TOKEN": "invalid_token"}):
            result = send_pushbullet_notification("Test Title", "Test Body")

        assert result is False

    def test_send_notification_no_token(self):
        """Test notification sending without token."""
        with patch.dict("os.environ", {}, clear=True):
            with patch.dict("claude_code_pushbullet_notify.config.CONFIG", {"pushbullet": {}}):
                result = send_pushbullet_notification("Test Title", "Test Body")

        assert result is False


class TestMainFunction:
    """Test suite for main function."""

    @patch("claude_code_pushbullet_notify.pushbullet._handle_hook_mode")
    @patch("claude_code_pushbullet_notify.pushbullet.argparse.ArgumentParser.parse_args")
    @patch("sys.stdin")
    @patch.dict("os.environ", {"PUSHBULLET_TOKEN": "test_key"})
    @patch.dict("claude_code_pushbullet_notify.config.CONFIG", {"notification": {}})
    def test_main_with_hook_data(self, mock_stdin, mock_parse_args, mock_handle_hook_mode):
        """Test main function with Claude Code hook data."""
        import json
        from argparse import Namespace
        
        hook_data = {"hook_event_name": "Stop", "transcript_path": "/test/transcript.jsonl"}
        mock_stdin.read.return_value = json.dumps(hook_data)
        mock_parse_args.return_value = Namespace(test=False, transcript_path=None)

        main()

        # Check that _handle_hook_mode was called with the correct hook data
        mock_handle_hook_mode.assert_called_once()
        called_hook_data = mock_handle_hook_mode.call_args[0][0]
        assert called_hook_data["hook_event_name"] == "Stop"
        assert called_hook_data["transcript_path"] == "/test/transcript.jsonl"

    @patch("sys.argv", ["script"])
    @patch("claude_code_pushbullet_notify.pushbullet.send_pushbullet_notification")
    @patch("claude_code_pushbullet_notify.transcript.read_hook_input")
    @patch.dict("os.environ", {"PUSHBULLET_TOKEN": "test_key"})
    def test_main_no_hook_data(self, mock_read_input, mock_send):
        """Test main function in legacy mode (no hook data)."""
        mock_read_input.return_value = None
        mock_send.return_value = True

        main()

        mock_send.assert_called_once()
        call_args = mock_send.call_args[0]
        assert "Claude Code Task completed" in call_args[0]
        assert "Test mode - no transcript available" in call_args[1]

    @patch("sys.argv", ["script"])
    @patch("claude_code_pushbullet_notify.pushbullet.send_pushbullet_notification")
    @patch("claude_code_pushbullet_notify.transcript.read_hook_input")
    @patch.dict("os.environ", {}, clear=True)
    def test_main_no_api_key(self, mock_read_input, mock_send):
        """Test main function without API key - should still run but notification fails."""
        mock_read_input.return_value = None
        mock_send.return_value = False  # Notification fails due to no token

        with patch.dict("claude_code_pushbullet_notify.config.CONFIG", {"pushbullet": {}}):
            main()  # Should not raise exception

        mock_send.assert_called_once()

    @patch("sys.argv", ["script", "--test"])
    @patch("claude_code_pushbullet_notify.pushbullet.send_pushbullet_notification")
    @patch.dict("os.environ", {"PUSHBULLET_TOKEN": "test_key"})
    def test_main_explicit_test_mode(self, mock_send):
        """Test main function with --test flag."""
        mock_send.return_value = True

        main()

        mock_send.assert_called_once()
        call_args = mock_send.call_args[0]
        assert "Claude Code Task completed" in call_args[0]
        assert "Test mode - no transcript available" in call_args[1]

    @patch("claude_code_pushbullet_notify.pushbullet._handle_test_mode")
    @patch("claude_code_pushbullet_notify.pushbullet.argparse.ArgumentParser.parse_args")
    @patch.dict("os.environ", {"PUSHBULLET_TOKEN": "test_key"})
    @patch.dict("claude_code_pushbullet_notify.config.CONFIG", {"notification": {}})
    def test_main_test_mode_with_transcript(self, mock_parse_args, mock_handle_test_mode):
        """Test main function with --test flag and transcript path."""
        # Mock ArgumentParser.parse_args to return the expected args
        from argparse import Namespace
        # Note: argparse converts --transcript-path to transcript_path attribute
        mock_parse_args.return_value = Namespace(test=True, transcript_path="/test/transcript.jsonl")

        main()

        # Check that _handle_test_mode was called with the correct args
        mock_handle_test_mode.assert_called_once()
        called_args = mock_handle_test_mode.call_args[0][0]
        assert called_args.test is True
        assert called_args.transcript_path == "/test/transcript.jsonl"
