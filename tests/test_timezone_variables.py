"""Tests for timezone support in template variables."""

import zoneinfo
from datetime import datetime
from unittest.mock import patch

import pytest

from claude_code_pushbullet_notify.template import _get_template_variables, _format_template


class TestTimezoneVariables:
    """Test timezone functionality for time variables."""

    @patch.dict("claude_code_pushbullet_notify.config.CONFIG", {
        "notification": {"timezone": "UTC"}
    })
    @patch("claude_code_pushbullet_notify.template.datetime")
    def test_timezone_utc(self, mock_datetime):
        """Test that UTC timezone is correctly applied."""
        # Mock datetime.now to return a specific time in UTC
        mock_datetime.now.return_value = datetime(2024, 8, 12, 15, 30, 45, tzinfo=zoneinfo.ZoneInfo("UTC"))
        
        variables = _get_template_variables("test-repo", "main")
        
        assert variables["TIMESTAMP"] == "2024-08-12 15:30:45"
        assert variables["DATE"] == "2024-08-12"
        assert variables["TIME"] == "15:30:45"
        assert variables["TIMEZONE"] == "UTC"
        assert variables["TIMESTAMP_TZ"] == "2024-08-12 15:30:45 UTC"

    @patch.dict("claude_code_pushbullet_notify.config.CONFIG", {
        "notification": {"timezone": "Asia/Tokyo"}
    })
    @patch("claude_code_pushbullet_notify.template.datetime")
    def test_timezone_tokyo(self, mock_datetime):
        """Test that Asia/Tokyo timezone is correctly applied."""
        # Mock datetime.now to return a specific time in JST
        mock_datetime.now.return_value = datetime(2024, 8, 12, 15, 30, 45, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo"))
        
        variables = _get_template_variables("test-repo", "main")
        
        assert variables["TIMESTAMP"] == "2024-08-12 15:30:45"
        assert variables["DATE"] == "2024-08-12"
        assert variables["TIME"] == "15:30:45"
        assert variables["TIMEZONE"] == "JST"
        assert variables["TIMESTAMP_TZ"] == "2024-08-12 15:30:45 JST"

    @patch.dict("claude_code_pushbullet_notify.config.CONFIG", {
        "notification": {"timezone": "America/New_York"}
    })
    @patch("claude_code_pushbullet_notify.template.datetime")
    def test_timezone_new_york(self, mock_datetime):
        """Test that America/New_York timezone is correctly applied."""
        # Mock for EST (winter time)
        mock_datetime.now.return_value = datetime(2024, 1, 12, 10, 30, 45, tzinfo=zoneinfo.ZoneInfo("America/New_York"))
        
        variables = _get_template_variables("test-repo", "main")
        
        assert variables["TIMESTAMP"] == "2024-01-12 10:30:45"
        assert variables["DATE"] == "2024-01-12"
        assert variables["TIME"] == "10:30:45"
        assert variables["TIMEZONE"] == "EST"
        assert variables["TIMESTAMP_TZ"] == "2024-01-12 10:30:45 EST"

    @patch.dict("claude_code_pushbullet_notify.config.CONFIG", {
        "notification": {}  # No timezone specified
    })
    @patch("claude_code_pushbullet_notify.template.datetime")
    def test_no_timezone_config(self, mock_datetime):
        """Test fallback to system timezone when no timezone is configured."""
        # Mock datetime.now to return local time without timezone info
        mock_datetime.now.return_value = datetime(2024, 8, 12, 15, 30, 45)
        
        variables = _get_template_variables("test-repo", "main")
        
        assert variables["TIMESTAMP"] == "2024-08-12 15:30:45"
        assert variables["DATE"] == "2024-08-12"
        assert variables["TIME"] == "15:30:45"
        assert variables["TIMEZONE"] == ""
        assert variables["TIMESTAMP_TZ"] == "2024-08-12 15:30:45"

    @patch.dict("claude_code_pushbullet_notify.config.CONFIG", {
        "notification": {"timezone": "Invalid/Timezone"}
    })
    @patch("claude_code_pushbullet_notify.template.datetime")
    def test_invalid_timezone_fallback(self, mock_datetime):
        """Test fallback to system timezone when invalid timezone is specified."""
        # Mock datetime.now to return local time for fallback
        mock_datetime.now.return_value = datetime(2024, 8, 12, 15, 30, 45)
        
        variables = _get_template_variables("test-repo", "main")
        
        assert variables["TIMESTAMP"] == "2024-08-12 15:30:45"
        assert variables["DATE"] == "2024-08-12"
        assert variables["TIME"] == "15:30:45"
        assert variables["TIMEZONE"] == ""
        assert variables["TIMESTAMP_TZ"] == "2024-08-12 15:30:45"

    def test_timezone_template_formatting(self):
        """Test that timezone variables work correctly in templates."""
        variables = {
            "GIT_REPO": "my-repo",
            "TIMESTAMP_TZ": "2024-08-12 15:30:45 JST",
            "TIMEZONE": "JST",
            "DATE": "2024-08-12",
            "TIME": "15:30:45"
        }
        
        # Test various template combinations
        templates = [
            ("{GIT_REPO} completed at {TIMESTAMP_TZ}", "my-repo completed at 2024-08-12 15:30:45 JST"),
            ("Timezone: {TIMEZONE}", "Timezone: JST"),
            ("{DATE} {TIME} {TIMEZONE}", "2024-08-12 15:30:45 JST"),
        ]
        
        for template, expected in templates:
            result = _format_template(template, variables)
            assert result == expected

    @patch.dict("claude_code_pushbullet_notify.config.CONFIG", {
        "notification": {"timezone": "Europe/London"}
    })
    @patch("claude_code_pushbullet_notify.template.datetime")
    def test_timezone_london_summer_time(self, mock_datetime):
        """Test BST (British Summer Time) timezone."""
        # Mock for BST (summer time)
        mock_datetime.now.return_value = datetime(2024, 7, 12, 15, 30, 45, tzinfo=zoneinfo.ZoneInfo("Europe/London"))
        
        variables = _get_template_variables("test-repo", "main")
        
        assert variables["TIMEZONE"] == "BST"
        assert variables["TIMESTAMP_TZ"] == "2024-07-12 15:30:45 BST"

    @patch.dict("claude_code_pushbullet_notify.config.CONFIG", {
        "notification": {"timezone": "Australia/Sydney"}
    })
    @patch("claude_code_pushbullet_notify.template.datetime")
    def test_timezone_sydney(self, mock_datetime):
        """Test Australia/Sydney timezone."""
        # Mock for AEST (Australian Eastern Standard Time)
        mock_datetime.now.return_value = datetime(2024, 8, 12, 15, 30, 45, tzinfo=zoneinfo.ZoneInfo("Australia/Sydney"))
        
        variables = _get_template_variables("test-repo", "main")
        
        assert variables["TIMESTAMP"] == "2024-08-12 15:30:45"
        assert variables["TIMEZONE"] == "AEST"
        assert variables["TIMESTAMP_TZ"] == "2024-08-12 15:30:45 AEST"

    def test_all_timezone_variables_present(self):
        """Test that all timezone-related variables are included."""
        variables = _get_template_variables("test-repo", "main")
        
        # Check that all timezone variables are present
        timezone_vars = ["TIMESTAMP", "DATE", "TIME", "TIMEZONE", "TIMESTAMP_TZ"]
        for var in timezone_vars:
            assert var in variables, f"Variable {var} should be present in template variables"
            assert isinstance(variables[var], str), f"Variable {var} should be a string"