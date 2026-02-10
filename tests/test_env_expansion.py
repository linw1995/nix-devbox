"""Tests for environment variable expansion."""

from pathlib import Path


from nix_devbox.config import (
    DevboxConfig,
    expand_env_vars,
    expand_env_vars_in_list,
)


class TestExpandEnvVars:
    """Tests for expand_env_vars helper."""

    def test_expand_dollar_var(self, monkeypatch):
        """Test $VAR syntax."""
        monkeypatch.setenv("TEST_VAR", "test_value")
        result = expand_env_vars("/home/$TEST_VAR/file")
        assert result == "/home/test_value/file"

    def test_expand_brace_var(self, monkeypatch):
        """Test ${VAR} syntax."""
        monkeypatch.setenv("TEST_VAR", "test_value")
        result = expand_env_vars("/home/${TEST_VAR}/file")
        assert result == "/home/test_value/file"

    def test_unknown_var_unchanged(self):
        """Unknown variables are left unchanged."""
        result = expand_env_vars("/home/$UNKNOWN_VAR/file")
        assert result == "/home/$UNKNOWN_VAR/file"

    def test_no_vars_unchanged(self):
        """Strings without env vars are unchanged."""
        result = expand_env_vars("/home/user/file")
        assert result == "/home/user/file"

    def test_multiple_vars(self, monkeypatch):
        """Multiple variables in one string."""
        monkeypatch.setenv("VAR1", "path1")
        monkeypatch.setenv("VAR2", "path2")
        result = expand_env_vars("/$VAR1/$VAR2/file")
        assert result == "/path1/path2/file"

    def test_mixed_syntax(self, monkeypatch):
        """Mix of $VAR and ${VAR} syntax."""
        monkeypatch.setenv("VAR1", "v1")
        monkeypatch.setenv("VAR2", "v2")
        result = expand_env_vars("/$VAR1/${VAR2}/end")
        assert result == "/v1/v2/end"


class TestExpandEnvVarsInList:
    """Tests for expand_env_vars_in_list helper."""

    def test_expand_list(self, monkeypatch):
        """Expand all items in a list."""
        monkeypatch.setenv("HOME", "/home/user")
        monkeypatch.setenv("USER", "testuser")

        items = ["$HOME/data", "/tmp/$USER-cache"]
        result = expand_env_vars_in_list(items)

        assert result == ["/home/user/data", "/tmp/testuser-cache"]

    def test_empty_list(self):
        """Empty list returns empty list."""
        result = expand_env_vars_in_list([])
        assert result == []

    def test_no_expansion_needed(self):
        """List without env vars is unchanged."""
        items = ["/plain/path", "another/path"]
        result = expand_env_vars_in_list(items)
        assert result == items


class TestConfigEnvExpansion:
    """Tests for env var expansion in config parsing."""

    def test_volumes_expansion(self, tmp_path: Path, monkeypatch):
        """Volumes have env vars expanded."""
        monkeypatch.setenv("HOME", "/home/testuser")
        monkeypatch.setenv("PROJECT", "myproject")

        config_file = tmp_path / "devbox.yaml"
        config_file.write_text(
            """
run:
  volumes:
    - $HOME/data:/data
    - ${PROJECT}:/project
"""
        )

        cfg = DevboxConfig.from_file(config_file)

        assert "/home/testuser/data:/data" in cfg.run.volumes
        assert "myproject:/project" in cfg.run.volumes

    def test_tmpfs_expansion(self, tmp_path: Path, monkeypatch):
        """Tmpfs has env vars expanded."""
        monkeypatch.setenv("USER", "testuser")

        config_file = tmp_path / "devbox.yaml"
        config_file.write_text(
            """
run:
  tmpfs:
    - /tmp/$USER-cache
"""
        )

        cfg = DevboxConfig.from_file(config_file)

        assert "/tmp/testuser-cache" in cfg.run.tmpfs

    def test_extra_args_expansion(self, tmp_path: Path, monkeypatch):
        """Extra args have env vars expanded."""
        monkeypatch.setenv("USER", "testuser")

        config_file = tmp_path / "devbox.yaml"
        config_file.write_text(
            """
run:
  extra_args:
    - --label=user=$USER
"""
        )

        cfg = DevboxConfig.from_file(config_file)

        assert "--label=user=testuser" in cfg.run.extra_args

    def test_ports_not_expanded(self, tmp_path: Path, monkeypatch):
        """Ports should not have env vars expanded."""
        monkeypatch.setenv("PORT", "8080")

        config_file = tmp_path / "devbox.yaml"
        config_file.write_text(
            """
run:
  ports:
    - 8080:80
"""
        )

        cfg = DevboxConfig.from_file(config_file)

        # Ports are kept as-is (no env var expansion)
        assert cfg.run.ports == ["8080:80"]

    def test_env_not_expanded(self, tmp_path: Path, monkeypatch):
        """Env vars list should not have env vars expanded (container-side)."""
        monkeypatch.setenv("VAL", "value")

        config_file = tmp_path / "devbox.yaml"
        config_file.write_text(
            """
run:
  env:
    - KEY=$VAL
"""
        )

        cfg = DevboxConfig.from_file(config_file)

        # Env values are kept as-is for container-side expansion
        assert cfg.run.env == ["KEY=$VAL"]
