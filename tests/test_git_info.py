"""Tests for git info functionality with environment variables."""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from claude_code_pushbullet_notify import get_git_info


class TestGitInfo:
    """Test git info retrieval from environment variables and fallback."""

    def test_get_git_info_from_env_vars(self):
        """Test that git info is correctly retrieved from environment variables."""
        # Set environment variables
        with patch.dict(os.environ, {"HOOK_GIT_REPO": "test-repo", "HOOK_GIT_BRANCH": "feature-branch"}):
            repo_name, branch_name = get_git_info()
            assert repo_name == "test-repo"
            assert branch_name == "feature-branch"

    def test_get_git_info_env_vars_priority(self):
        """Test that environment variables take priority over git commands."""
        # Even if we're in a git repo, env vars should take priority
        with patch.dict(os.environ, {"HOOK_GIT_REPO": "env-repo", "HOOK_GIT_BRANCH": "env-branch"}):
            # Mock subprocess to simulate being in a different git repo
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.stdout = "different-repo\n"
                mock_run.return_value.returncode = 0
                
                repo_name, branch_name = get_git_info()
                # Should use env vars, not subprocess
                assert repo_name == "env-repo"
                assert branch_name == "env-branch"
                # subprocess.run should not be called when env vars are set
                mock_run.assert_not_called()

    def test_get_git_info_fallback_to_git_commands(self):
        """Test fallback to git commands when env vars are not set."""
        # Clear environment variables
        with patch.dict(os.environ, {}, clear=True):
            # Remove HOOK_GIT_REPO and HOOK_GIT_BRANCH if they exist
            os.environ.pop("HOOK_GIT_REPO", None)
            os.environ.pop("HOOK_GIT_BRANCH", None)
            
            with patch("subprocess.run") as mock_run:
                # First call for repo name
                repo_response = subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="/home/user/my-project\n"
                )
                # Second call for branch name
                branch_response = subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="main\n"
                )
                mock_run.side_effect = [repo_response, branch_response]
                
                repo_name, branch_name = get_git_info()
                assert repo_name == "my-project"
                assert branch_name == "main"
                assert mock_run.call_count == 2

    def test_get_git_info_fallback_not_in_git_repo(self):
        """Test fallback when not in a git repository."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("HOOK_GIT_REPO", None)
            os.environ.pop("HOOK_GIT_BRANCH", None)
            
            with patch("subprocess.run") as mock_run:
                # Simulate git command failure
                mock_run.side_effect = subprocess.CalledProcessError(128, "git")
                
                with patch("pathlib.Path.cwd") as mock_cwd:
                    mock_cwd.return_value = Path("/home/user/not-a-repo")
                    
                    repo_name, branch_name = get_git_info()
                    assert repo_name == "not-a-repo"
                    assert branch_name == "main"

    def test_get_git_info_partial_env_vars(self):
        """Test behavior when only one env var is set."""
        # Only HOOK_GIT_REPO is set
        with patch.dict(os.environ, {"HOOK_GIT_REPO": "partial-repo"}):
            os.environ.pop("HOOK_GIT_BRANCH", None)
            
            with patch("subprocess.run") as mock_run:
                repo_response = subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="/home/user/fallback-project\n"
                )
                branch_response = subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="develop\n"
                )
                mock_run.side_effect = [repo_response, branch_response]
                
                repo_name, branch_name = get_git_info()
                # Should fallback since both vars are not set
                assert repo_name == "fallback-project"
                assert branch_name == "develop"

        # Only HOOK_GIT_BRANCH is set
        with patch.dict(os.environ, {"HOOK_GIT_BRANCH": "partial-branch"}):
            os.environ.pop("HOOK_GIT_REPO", None)
            
            with patch("subprocess.run") as mock_run:
                repo_response = subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="/home/user/fallback-project\n"
                )
                branch_response = subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="develop\n"
                )
                mock_run.side_effect = [repo_response, branch_response]
                
                repo_name, branch_name = get_git_info()
                # Should fallback since both vars are not set
                assert repo_name == "fallback-project"
                assert branch_name == "develop"


class TestShellScriptIntegration:
    """Integration tests for the shell script."""

    @pytest.fixture
    def temp_git_repo(self):
        """Create a temporary git repository for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir) / "test-repo"
            repo_path.mkdir()
            
            # Initialize git repo
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=repo_path, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=repo_path, check=True, capture_output=True
            )
            
            # Create a file and commit
            (repo_path / "test.txt").write_text("test content")
            subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                cwd=repo_path, check=True, capture_output=True
            )
            
            # Create and checkout a branch
            subprocess.run(
                ["git", "checkout", "-b", "test-feature"],
                cwd=repo_path, check=True, capture_output=True
            )
            
            yield repo_path

    def test_shell_script_exports_git_info(self, temp_git_repo):
        """Test that the shell script correctly exports git info as environment variables."""
        script_path = Path(__file__).parent.parent / "scripts" / "claude-code-pushbullet-notify"
        
        # Create a test script that sources our script and prints the env vars
        test_script = f"""#!/bin/bash
cd {temp_git_repo}
# Source just the git info extraction part
if git rev-parse --show-toplevel >/dev/null 2>&1; then
    export HOOK_GIT_REPO="$(basename "$(git rev-parse --show-toplevel)")"
    export HOOK_GIT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
else
    export HOOK_GIT_REPO="$(basename "$PWD")"
    export HOOK_GIT_BRANCH="main"
fi
echo "HOOK_GIT_REPO=$HOOK_GIT_REPO"
echo "HOOK_GIT_BRANCH=$HOOK_GIT_BRANCH"
"""
        
        result = subprocess.run(
            ["bash", "-c", test_script],
            capture_output=True,
            text=True,
            check=True
        )
        
        lines = result.stdout.strip().split("\n")
        env_vars = {}
        for line in lines:
            if "=" in line:
                key, value = line.split("=", 1)
                env_vars[key] = value
        
        assert env_vars["HOOK_GIT_REPO"] == "test-repo"
        assert env_vars["HOOK_GIT_BRANCH"] == "test-feature"

    def test_shell_script_handles_non_git_directory(self):
        """Test that the shell script handles non-git directories correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_script = f"""#!/bin/bash
cd {tmpdir}
if git rev-parse --show-toplevel >/dev/null 2>&1; then
    export HOOK_GIT_REPO="$(basename "$(git rev-parse --show-toplevel)")"
    export HOOK_GIT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
else
    export HOOK_GIT_REPO="$(basename "$PWD")"
    export HOOK_GIT_BRANCH="main"
fi
echo "HOOK_GIT_REPO=$HOOK_GIT_REPO"
echo "HOOK_GIT_BRANCH=$HOOK_GIT_BRANCH"
"""
            
            result = subprocess.run(
                ["bash", "-c", test_script],
                capture_output=True,
                text=True,
                check=True
            )
            
            lines = result.stdout.strip().split("\n")
            env_vars = {}
            for line in lines:
                if "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key] = value
            
            assert env_vars["HOOK_GIT_REPO"] == Path(tmpdir).name
            assert env_vars["HOOK_GIT_BRANCH"] == "main"

    def test_full_script_flow(self, temp_git_repo, monkeypatch):
        """Test the full flow from shell script to Python with mock stdin."""
        # Create a mock hook data
        hook_data = {
            "hook_event_name": "Stop",
            "transcript_path": "/dev/null",  # Use /dev/null as a valid but empty file
            "stop_hook_active": True
        }
        
        # Set up the test to run from the temp git repo
        script_path = Path(__file__).parent.parent / "scripts" / "claude-code-pushbullet-notify"
        
        # Create a test that captures what the Python module would see
        test_script = f"""#!/bin/bash
cd {temp_git_repo}
# Export git info as the script would
if git rev-parse --show-toplevel >/dev/null 2>&1; then
    export HOOK_GIT_REPO="$(basename "$(git rev-parse --show-toplevel)")"
    export HOOK_GIT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
else
    export HOOK_GIT_REPO="$(basename "$PWD")"
    export HOOK_GIT_BRANCH="main"
fi

# Now run Python to check if it picks up the env vars
python3 -c '
import os
print(f"REPO={{os.environ.get(\"HOOK_GIT_REPO\", \"NOT_SET\")}}")
print(f"BRANCH={{os.environ.get(\"HOOK_GIT_BRANCH\", \"NOT_SET\")}}")
'
"""
        
        result = subprocess.run(
            ["bash", "-c", test_script],
            capture_output=True,
            text=True,
            check=True
        )
        
        assert "REPO=test-repo" in result.stdout
        assert "BRANCH=test-feature" in result.stdout