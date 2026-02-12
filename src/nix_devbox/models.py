"""Domain models for nix-devbox."""

from dataclasses import dataclass
from pathlib import Path

DEFAULT_TAG = "latest"

# Flake shell attribute patterns
DEFAULT_SHELL_ATTR = "devShells.${system}.default"
DEVSHELLS_PREFIX = "devShells."

# Default container paths
DEFAULT_WORKDIR = "/workspace"


@dataclass(frozen=True)
class ImageRef:
    """Docker image reference with name and tag."""

    name: str
    tag: str

    def __str__(self) -> str:
        """Return image reference as 'name:tag' string."""
        return f"{self.name}:{self.tag}"

    @classmethod
    def parse(
        cls,
        value: str,
        *,
        name_override: str | None = None,
        tag_override: str | None = None,
    ) -> "ImageRef":
        """Parse image reference from string like 'name:tag' or 'name'."""
        if not value or not value.strip():
            raise ValueError("Image reference cannot be empty")

        # Use partition for cleaner splitting (EAFP style)
        # partition always returns 3 parts: (before, separator, after)
        name, sep, tag = value.partition(":")
        if not sep:
            tag = DEFAULT_TAG

        return cls(
            name=name_override or name,
            tag=tag_override or tag,
        )


@dataclass(frozen=True)
class FlakeRef:
    """Flake reference with path and shell attribute."""

    path: str
    shell: str

    @classmethod
    def parse(cls, ref: str) -> "FlakeRef":
        """
        Parse flake reference.

        Formats:
            /path/to/flake              -> (path, devShells.${system}.default)
            /path/to/flake#shellname    -> (path, devShells.${system}.shellname)
            /path/to/flake#devShells.x86_64-linux.shellname -> full path
        """
        if "#" not in ref:
            return cls._from_path_only(ref)

        return cls._from_path_with_shell(ref)

    @classmethod
    def _from_path_only(cls, ref: str) -> "FlakeRef":
        """Create FlakeRef from path without shell specification."""
        resolved_path = Path(ref).resolve()
        return cls(
            path=str(resolved_path),
            shell=DEFAULT_SHELL_ATTR,
        )

    @classmethod
    def _from_path_with_shell(cls, ref: str) -> "FlakeRef":
        """Create FlakeRef from path with shell specification."""
        # Use partition for safer splitting
        path_str, _, shell = ref.partition("#")

        if not shell.startswith(DEVSHELLS_PREFIX) and "." not in shell:
            shell = f"{DEVSHELLS_PREFIX}${{system}}.{shell}"

        resolved_path = Path(path_str).resolve()
        return cls(path=str(resolved_path), shell=shell)

    def __str__(self) -> str:
        """Return flake reference as 'path#shell' string."""
        return f"{self.path}#{self.shell}"
