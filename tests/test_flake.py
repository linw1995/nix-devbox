"""Tests for flake.nix generation."""

import subprocess
import tempfile
from pathlib import Path

import pytest

from nix_devbox.core import generate_flake
from nix_devbox.models import FlakeRef, ImageRef


@pytest.fixture(autouse=True)
def set_uid_gid_env(monkeypatch):
    """Set NIX_DEVBOX_UID and NIX_DEVBOX_GID for all tests."""
    monkeypatch.setenv("NIX_DEVBOX_UID", "1000")
    monkeypatch.setenv("NIX_DEVBOX_GID", "100")


class TestFlakeGeneration:
    """Tests for flake.nix generation."""

    def test_basic_flake_generation(self):
        """Test basic flake.nix generation."""
        flake_refs = [FlakeRef.parse("/path/to/project")]
        image_ref = ImageRef.parse("test:latest")

        flake_content = generate_flake(flake_refs, image_ref)

        assert "pkgs.writeShellScriptBin" in flake_content
        assert "entrypoint" in flake_content
        assert 'name = "test"' in flake_content  # Image name
        assert 'tag = "latest"' in flake_content  # Image tag
        assert "/path/to/project" in flake_content

    def test_multiple_flake_refs(self):
        """Test flake generation with multiple flake references."""
        flake_refs = [
            FlakeRef.parse("/path/to/project1"),
            FlakeRef.parse("/path/to/project2#devShells.default"),
        ]
        image_ref = ImageRef.parse("test:latest")

        flake_content = generate_flake(flake_refs, image_ref)

        assert "shell0" in flake_content
        assert "shell1" in flake_content
        assert "proj0" in flake_content
        assert "proj1" in flake_content

    def test_flake_generation(self):
        """Test basic flake generation."""
        flake_refs = [FlakeRef.parse("/path/to/project")]
        image_ref = ImageRef.parse("test:latest")

        flake_content = generate_flake(flake_refs, image_ref)

        # Verify basic structure
        assert "inputs = {" in flake_content
        assert "outputs = {" in flake_content
        assert "buildNixShellImage" in flake_content

    def test_flake_generation_with_mount_points(self):
        """Test flake generation with mount points."""
        flake_refs = [FlakeRef.parse("/path/to/project")]
        image_ref = ImageRef.parse("test:latest")
        mount_points = ["/data", "/cache", "/home/user/.config"]

        flake_content = generate_flake(flake_refs, image_ref, mount_points)

        # Verify mount point directories are created via extraCommands
        assert "extraCommands" in flake_content
        # extraCommands uses relative paths (./path instead of /path)
        assert "mkdir -p './data'" in flake_content
        assert "mkdir -p './cache'" in flake_content
        assert "mkdir -p './home/user/.config'" in flake_content
        assert "chown 1000:100 './data'" in flake_content
        assert "chown 1000:100 './cache'" in flake_content
        assert "chown 1000:100 './home/user/.config'" in flake_content

    def test_flake_generation_default_mount_point(self):
        """Test that default /workspace is always included."""
        flake_refs = [FlakeRef.parse("/path/to/project")]
        image_ref = ImageRef.parse("test:latest")

        # Without explicit mount_points, /workspace should still be created
        flake_content = generate_flake(flake_refs, image_ref)

        assert "extraCommands" in flake_content
        # extraCommands uses relative paths
        assert "mkdir -p './workspace'" in flake_content
        assert "chown 1000:100 './workspace'" in flake_content


@pytest.mark.skipif(
    subprocess.run(["which", "nix"], capture_output=True).returncode != 0,
    reason="Nix not installed",
)
class TestFlakeSyntax:
    """Tests for flake.nix syntax validation using Nix."""

    def test_nix_instantiate_parse(self):
        """Test that generated flake can be parsed by nix-instantiate.

        This validates Nix syntax without evaluating or building.
        """
        flake_refs = [FlakeRef.parse("/tmp/test-project")]
        image_ref = ImageRef.parse("test:latest")

        flake_content = generate_flake(flake_refs, image_ref)

        with tempfile.TemporaryDirectory() as tmp_dir:
            flake_path = Path(tmp_dir) / "flake.nix"
            flake_path.write_text(flake_content)

            # Use nix-instantiate --parse to check syntax only
            result = subprocess.run(
                ["nix-instantiate", "--parse", str(flake_path)],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0, (
                f"Nix syntax error:\n{result.stderr}\n\n"
                f"Generated flake:\n{flake_content[:500]}..."
            )
