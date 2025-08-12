"""Pytest configuration and fixtures."""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def mock_git_info():
    """Mock git info for all tests."""
    with patch("claude_code_pushbullet_notify.template.get_git_info") as mock:
        mock.return_value = ("test-repo", "test-branch")
        yield mock
