"""Tests for configuration value passing (no expansion in Python)."""

from pathlib import Path

from nix_devbox.config import DevboxConfig


class TestConfigValuePassing:
    """Tests that config values are passed through as-is (no expansion)."""

    def test_volumes_passed_through(self, tmp_path: Path):
        """Volumes are passed through as-is for shell expansion."""
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

        # Values are kept as-is for shell expansion during docker run
        assert "$HOME/data:/data" in cfg.run.volumes
        assert "${PROJECT}:/project" in cfg.run.volumes

    def test_tmpfs_passed_through(self, tmp_path: Path):
        """Tmpfs values are passed through as-is."""
        config_file = tmp_path / "devbox.yaml"
        config_file.write_text(
            """
run:
  tmpfs:
    - /tmp/$USER-cache
"""
        )

        cfg = DevboxConfig.from_file(config_file)

        assert "/tmp/$USER-cache" in cfg.run.tmpfs

    def test_extra_args_passed_through(self, tmp_path: Path):
        """Extra args are passed through as-is."""
        config_file = tmp_path / "devbox.yaml"
        config_file.write_text(
            """
run:
  extra_args:
    - --label=user=$USER
"""
        )

        cfg = DevboxConfig.from_file(config_file)

        assert "--label=user=$USER" in cfg.run.extra_args

    def test_env_passed_through(self, tmp_path: Path):
        """Env values are passed through as-is."""
        config_file = tmp_path / "devbox.yaml"
        config_file.write_text(
            """
run:
  env:
    - KEY=$VAL
    - BUILD_TIME=$(date)
"""
        )

        cfg = DevboxConfig.from_file(config_file)

        # Values are kept as-is for shell expansion during docker run
        assert "KEY=$VAL" in cfg.run.env
        assert "BUILD_TIME=$(date)" in cfg.run.env

    def test_ports_unchanged(self, tmp_path: Path):
        """Ports are kept as-is."""
        config_file = tmp_path / "devbox.yaml"
        config_file.write_text(
            """
run:
  ports:
    - 8080:80
"""
        )

        cfg = DevboxConfig.from_file(config_file)

        assert cfg.run.ports == ["8080:80"]
