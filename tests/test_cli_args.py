"""Tests for CLI argument parsing, especially -- delimiter handling."""

import os
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from nix_devbox.cli import cli


_captured_config = None


def _capture_config(config):
    global _captured_config
    _captured_config = config
    raise SystemExit(0)


class TestCLIArgumentParsing:
    """Tests for CLI argument parsing."""

    def setup_method(self):
        global _captured_config
        _captured_config = None

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def mock_execute(self):
        with patch("nix_devbox.cli._execute_run", _capture_config):
            yield

    @pytest.fixture
    def isolated_env(self, tmp_path):
        """Run tests in isolated temp directory to avoid extends from devbox.yaml."""
        orig_cwd = os.getcwd()
        os.chdir(tmp_path)
        yield tmp_path
        os.chdir(orig_cwd)

    def test_run_single_flake(self, runner, mock_execute, isolated_env):
        """Test basic run with a single flake reference."""
        result = runner.invoke(cli, ["run", "/path/to/flake"], catch_exceptions=True)
        assert result.exit_code == 0
        assert len(_captured_config.flake_refs) == 1
        assert _captured_config.flake_refs[0].url == "path:/path/to/flake"
        assert _captured_config.command is None

    def test_run_multiple_flakes(self, runner, mock_execute, isolated_env):
        """Test run with multiple flake references."""
        result = runner.invoke(
            cli, ["run", "/path/to/flake1", "/path/to/flake2"], catch_exceptions=True
        )
        assert result.exit_code == 0
        assert len(_captured_config.flake_refs) == 2
        assert _captured_config.command is None

    def test_run_registry_ref(self, runner, mock_execute, isolated_env):
        """Test run with registry reference."""
        result = runner.invoke(cli, ["run", "@nix-devbox/base"], catch_exceptions=True)
        assert result.exit_code == 0
        assert len(_captured_config.flake_refs) == 1

    def test_run_with_dash_dash_delimiter(self, runner, mock_execute, isolated_env):
        """Test run with -- delimiter and command."""
        result = runner.invoke(
            cli, ["run", "/path/to/flake", "--", "ls", "-la"], catch_exceptions=True
        )
        assert result.exit_code == 0
        assert len(_captured_config.flake_refs) == 1
        assert _captured_config.command == "ls -la"

    def test_run_with_dash_dash_delimiter_multiple_flakes(
        self, runner, mock_execute, isolated_env
    ):
        """Test run with multiple flakes and -- delimiter."""
        result = runner.invoke(
            cli,
            [
                "run",
                "@nix-devbox/base",
                "@nix-devbox/opencode",
                "--",
                "python",
                "script.py",
            ],
            catch_exceptions=True,
        )
        assert result.exit_code == 0
        assert len(_captured_config.flake_refs) == 2
        assert _captured_config.command == "python script.py"

    def test_run_with_options_before_dash_dash(
        self, runner, mock_execute, isolated_env
    ):
        """Test run with options before -- delimiter."""
        result = runner.invoke(
            cli,
            ["run", "--rebuild", "/path/to/flake", "--", "ls"],
            catch_exceptions=True,
        )
        assert result.exit_code == 0
        assert len(_captured_config.flake_refs) == 1
        assert _captured_config.command == "ls"
        assert _captured_config.rebuild is True

    def test_run_dash_dash_with_empty_command(self, runner, mock_execute, isolated_env):
        """Test run with -- delimiter but no command after it."""
        result = runner.invoke(
            cli, ["run", "/path/to/flake", "--"], catch_exceptions=True
        )
        assert result.exit_code == 0
        assert len(_captured_config.flake_refs) == 1
        assert _captured_config.command is None

    def test_run_option_like_flake_name(self, runner, mock_execute, isolated_env):
        """Test run with option-like flake name still works."""
        result = runner.invoke(cli, ["run", "./my-project"], catch_exceptions=True)
        assert result.exit_code == 0
        assert len(_captured_config.flake_refs) == 1

    def test_run_with_verbose_flag(self, runner, mock_execute, isolated_env):
        """Test run with verbose flag."""
        result = runner.invoke(
            cli,
            ["run", "--verbose", "/path/to/flake", "--", "echo", "hi"],
            catch_exceptions=True,
        )
        assert result.exit_code == 0
        assert _captured_config.command == "echo hi"

    def test_run_with_detach_flag(self, runner, mock_execute, isolated_env):
        """Test run with detach flag."""
        result = runner.invoke(
            cli, ["run", "-d", "/path/to/flake", "--", "bash"], catch_exceptions=True
        )
        assert result.exit_code == 0
        assert _captured_config.detach is True
        assert _captured_config.command == "bash"
