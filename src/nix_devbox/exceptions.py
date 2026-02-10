"""Custom exceptions for nix-devbox."""


class DevboxError(Exception):
    """Base exception for all devbox errors."""

    pass


class BuildError(DevboxError):
    """Raised when building the Docker image fails."""

    pass


class DockerError(DevboxError):
    """Raised when a Docker command fails."""

    pass


class FlakeError(DevboxError):
    """Raised when flake.nix generation or parsing fails."""

    pass


class ConfigError(DevboxError):
    """Raised when configuration file parsing fails."""

    pass
