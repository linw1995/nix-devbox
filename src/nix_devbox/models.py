"""Domain models for nix-devbox."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DEFAULT_TAG = "latest"

# Flake shell attribute patterns
DEFAULT_SHELL_ATTR = "devShells.${system}.default"
DEVSHELLS_PREFIX = "devShells."

# Default container paths
DEFAULT_WORKDIR = "/workspace"

# Reserved paths for Nix internal use (buildNixShellImage uses /build)
RESERVED_PATHS = frozenset({"/build"})

# Base directory for user mount points (avoid conflicts with RESERVED_PATHS)
USER_MOUNT_BASE = "/home"

# Mapping for reserved paths: reserved_path -> alternative_path
# e.g., /build/.config -> /home/.config
RESERVED_PATH_MAPPING = "/home"

# Known flake URL schemes
REMOTE_SCHEMES = frozenset(
    {
        "github",
        "gitlab",
        "sourcehut",
        "bitbucket",
        "git",
        "hg",
        "http",
        "https",
        "file",
    }
)


@dataclass(frozen=True)
class FlakeURI:
    """Flake URI parser supporting various URL formats."""

    raw: str  # Original input string
    url: str  # Normalized URL for flake.nix inputs
    subdir: str | None  # Subdirectory path from ?dir= parameter
    is_local: bool  # Whether this is a local path

    @classmethod
    def parse(cls, ref: str) -> "FlakeURI":
        """Parse a flake reference string.

        Supports formats:
            /path/to/flake              -> path:/absolute/path
            /path/to/flake#shell        -> path:/absolute/path with shell
            github:owner/repo/ref       -> github:owner/repo/ref
            github:owner/repo/ref?dir=x -> github:owner/repo/ref with subdir
            git+https://...             -> git+https://...
            https://...                 -> https://...
        """
        ref = ref.strip()
        if not ref:
            raise ValueError("Flake reference cannot be empty")

        # Split path/shell if there's a #
        if "#" in ref:
            url_part, _, _ = ref.partition("#")
        else:
            url_part = ref

        # Check if it's a remote URL (has scheme and doesn't start with /)
        if ":" in url_part and not url_part.startswith("/"):
            return cls._parse_remote(url_part)

        # Otherwise treat as local path
        return cls._parse_local(url_part)

    @classmethod
    def _parse_remote(cls, url: str) -> "FlakeURI":
        """Parse a remote URL, extracting subdir if present."""
        scheme = url.split(":", 1)[0].lower()

        # Check if it's a known remote scheme
        is_known = any(
            scheme == s or scheme.startswith(f"{s}+") for s in REMOTE_SCHEMES
        )
        if not is_known:
            # Unknown scheme, treat as local path with colon
            return cls._parse_local(url)

        # Parse query parameters for ?dir=
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        subdir = query_params.get("dir", [None])[0]

        return cls(
            raw=url,
            url=url,
            subdir=subdir,
            is_local=False,
        )

    @classmethod
    def _parse_local(cls, path: str) -> "FlakeURI":
        """Parse a local path, converting to absolute path."""
        resolved = Path(path).resolve()
        abs_path = str(resolved)

        # Add path: prefix if not present
        if not abs_path.startswith("path:"):
            url = f"path:{abs_path}"
        else:
            url = abs_path

        return cls(
            raw=path,
            url=url,
            subdir=None,
            is_local=True,
        )


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
    """Flake reference with URI and shell attribute."""

    uri: FlakeURI
    shell: str

    @property
    def url(self) -> str:
        """Return the URL for flake.nix inputs."""
        return self.uri.url

    @property
    def shell_attr(self) -> str:
        """Return the shell attribute path.

        Note: subdir is handled in the flake URL (?dir= parameter),
        so the input already points to the correct flake directory.
        No need to prepend subdir to the shell path.
        """
        return self.shell

    @classmethod
    def parse(cls, ref: str) -> "FlakeRef":
        """
        Parse flake reference.

        Formats:
            /path/to/flake              -> (uri, devShells.${system}.default)
            /path/to/flake#shellname    -> (uri, devShells.${system}.shellname)
            /path/to/flake#devShells.x86_64-linux.shellname -> full path
            github:owner/repo           -> (uri, devShells.${system}.default)
            github:owner/repo#shell     -> (uri, devShells.${system}.shell)
            github:owner/repo?dir=subdir#shell -> (uri, subdir.devShells.${system}.shell)
        """
        if "#" not in ref:
            return cls._from_url_only(ref)

        return cls._from_url_with_shell(ref)

    @classmethod
    def _from_url_only(cls, ref: str) -> "FlakeRef":
        """Create FlakeRef from URL without shell specification."""
        uri = FlakeURI.parse(ref)
        return cls(
            uri=uri,
            shell=DEFAULT_SHELL_ATTR,
        )

    @classmethod
    def _from_url_with_shell(cls, ref: str) -> "FlakeRef":
        """Create FlakeRef from URL with shell specification."""
        url_part, _, shell = ref.partition("#")

        if not shell.startswith(DEVSHELLS_PREFIX) and "." not in shell:
            shell = f"{DEVSHELLS_PREFIX}${{system}}.{shell}"

        uri = FlakeURI.parse(url_part)
        return cls(uri=uri, shell=shell)

    def __str__(self) -> str:
        """Return flake reference as 'url#shell' string."""
        return f"{self.uri.raw}#{self.shell}"


class RemoteFlakeFetcher:
    """Fetch remote flakes and provide access to their files."""

    def __init__(self) -> None:
        """Initialize the fetcher with an empty cache."""
        self._cache: dict[str, Path] = {}

    def fetch(self, url: str) -> Path:
        """Fetch a remote flake and return the local store path.

        Uses nix flake prefetch to download the flake and cache it.
        Subsequent calls with the same URL return the cached path.

        Args:
            url: The flake URL (e.g., "github:owner/repo/ref")

        Returns:
            Path to the downloaded flake in the Nix store

        Raises:
            RuntimeError: If the fetch fails
        """
        if url in self._cache:
            return self._cache[url]

        try:
            result = subprocess.run(
                ["nix", "flake", "prefetch", "--json", url],
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(result.stdout)
            store_path = Path(data["storePath"])
            self._cache[url] = store_path
            return store_path
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to fetch flake {url}: {e.stderr}") from e
        except (json.JSONDecodeError, KeyError) as e:
            raise RuntimeError(f"Invalid response from nix prefetch: {e}") from e

    def get_file_path(self, url: str, filename: str) -> Path | None:
        """Get the path to a specific file in a remote flake.

        Args:
            url: The flake URL
            filename: Name of the file to locate (e.g., "devbox.yaml")

        Returns:
            Path to the file if it exists, None otherwise
        """
        flake_path = self.fetch(url)
        file_path = flake_path / filename
        return file_path if file_path.exists() else None

    def clear_cache(self) -> None:
        """Clear the fetch cache."""
        self._cache.clear()


# Global fetcher instance for reuse across the application
_flake_fetcher: RemoteFlakeFetcher | None = None


def get_flake_fetcher() -> RemoteFlakeFetcher:
    """Get the global flake fetcher instance."""
    global _flake_fetcher
    if _flake_fetcher is None:
        _flake_fetcher = RemoteFlakeFetcher()
    return _flake_fetcher
