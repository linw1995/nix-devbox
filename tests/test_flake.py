"""Tests for flake.nix generation."""

import subprocess
import tempfile
from pathlib import Path

import pytest

from nix_devbox.core import generate_flake
from nix_devbox.models import FlakeRef, ImageRef


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
        """Test flake generation with mount points - only parent dirs created."""
        flake_refs = [FlakeRef.parse("/path/to/project")]
        image_ref = ImageRef.parse("test:latest")
        mount_points = ["/data", "/cache", "/home/user/.config"]

        flake_content = generate_flake(flake_refs, image_ref, mount_points)

        # Verify mount point parent directories are created via fakeRootCommands
        assert "fakeRootCommands" in flake_content
        # /data and /cache are direct children of root, no parent to create
        assert "mkdir -p './data'" not in flake_content
        assert "mkdir -p './cache'" not in flake_content
        # /home/user/.config has parents: /home, /home/user
        assert "mkdir -p './home'" in flake_content
        assert "chown" in flake_content
        assert "mkdir -p './home/user'" in flake_content
        # Mount point itself is NOT created
        assert "mkdir -p './home/user/.config'" not in flake_content

    def test_flake_generation_default_mount_point(self):
        """Test that default /workspace parent dirs are created."""
        flake_refs = [FlakeRef.parse("/path/to/project")]
        image_ref = ImageRef.parse("test:latest")

        # /workspace is at root level, no parent dirs to create
        flake_content = generate_flake(flake_refs, image_ref)

        assert "fakeRootCommands" in flake_content
        # /workspace has no parent dirs (except root), so no mkdir commands
        assert "mkdir -p './workspace'" not in flake_content
        # The mount point itself is NOT created in fakeRootCommands
        assert "chown" not in flake_content or "'./workspace'" not in flake_content

    def test_flake_generation_parent_directories(self):
        """Test that only parent directories are created, not mount points."""
        flake_refs = [FlakeRef.parse("/path/to/project")]
        image_ref = ImageRef.parse("test:latest")
        # Nested path - should create /data, /data/subdir but NOT /data/subdir/deep
        mount_points = ["/data/subdir/deep"]

        flake_content = generate_flake(flake_refs, image_ref, mount_points)

        assert "fakeRootCommands" in flake_content
        # Parent directories should be created and chowned
        assert "mkdir -p './data'" in flake_content
        assert "chown" in flake_content
        assert "mkdir -p './data/subdir'" in flake_content
        # Mount point itself is NOT created (docker creates it when mounting)
        assert "mkdir -p './data/subdir/deep'" not in flake_content

    def test_flake_generation_excludes_special_dirs(self):
        """Test that /tmp is excluded but other paths are handled."""
        flake_refs = [FlakeRef.parse("/path/to/project")]
        image_ref = ImageRef.parse("test:latest")
        # Include paths under /tmp which should be handled specially
        # /tmp/cache is not under /build so it's allowed
        mount_points = ["/tmp/cache", "/data"]

        flake_content = generate_flake(flake_refs, image_ref, mount_points)

        assert "fakeRootCommands" in flake_content
        # /tmp itself should NOT be created (it needs special permissions)
        assert "mkdir -p './tmp'" not in flake_content
        # /data has no parent (direct child of root), not created
        assert "mkdir -p './data'" not in flake_content


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
