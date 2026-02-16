"""Nix devbox - Merge flake devShells, build and run containers."""

__version__ = "0.1.0"

try:
    from . import _version

    __commit_sha__ = _version.__commit_sha__
    __is_dirty__ = _version.__is_dirty__
except ImportError:
    __commit_sha__ = ""
    __is_dirty__ = False

from .config import DevboxConfig, merge_devbox_configs
from .exceptions import BuildError, ConfigError, DevboxError, DockerError, FlakeError
from .models import FlakeRef, ImageRef

__all__ = [
    "FlakeRef",
    "ImageRef",
    "DevboxConfig",
    "merge_devbox_configs",
    "DevboxError",
    "BuildError",
    "ConfigError",
    "DockerError",
    "FlakeError",
]
