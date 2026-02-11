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

    def test_flake_with_ensure_dirs(self):
        """Test flake generation with ensure_dirs."""
        flake_refs = [FlakeRef.parse("/path/to/project")]
        image_ref = ImageRef.parse("test:latest")
        ensure_dirs = ["/build/.config", "/build/.cache"]

        flake_content = generate_flake(flake_refs, image_ref, ensure_dirs)

        assert "/build/.config" in flake_content
        assert "/build/.cache" in flake_content

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

    def test_flake_no_ensure_dirs(self):
        """Test flake generation without ensure_dirs defaults to /build only."""
        flake_refs = [FlakeRef.parse("/path/to/project")]
        image_ref = ImageRef.parse("test:latest")

        flake_content = generate_flake(flake_refs, image_ref)

        # /build should always be present
        assert '"/build"' in flake_content


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
        ensure_dirs = ["/build/.config"]

        flake_content = generate_flake(flake_refs, image_ref, ensure_dirs)

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
