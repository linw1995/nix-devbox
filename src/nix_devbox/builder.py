"""Docker image building and container running functionality."""

import logging
import subprocess
from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING

import click

from .exceptions import BuildError, DockerError
from .utils import expand_flagged_options

if TYPE_CHECKING:
    from .models import ImageRef

logger = logging.getLogger(__name__)
# Add null handler to avoid "No handler found" warnings
logger.addHandler(logging.NullHandler())

# Exit codes treated as normal for interactive TTY containers
# 0   - Normal exit (typing 'exit' or ctrl+d)
# 1   - General error, but often used by shells on normal exit
# 130 - SIGINT (ctrl+c)
# 143 - SIGTERM (container terminated gracefully)
_NORMAL_EXIT_CODES = frozenset({0, 1, 130, 143})


def build_image(
    flake_content: str,
    image_ref: "ImageRef",
    temp_dir: str,
    verbose: bool = False,
) -> None:
    """
    Build and load Docker image from flake.nix content.

    Args:
        flake_content: The generated flake.nix content
        image_ref: Image name and tag reference
        temp_dir: Temporary directory for building
        verbose: Whether to print verbose output

    Raises:
        BuildError: If the build fails
        DockerError: If docker load fails
    """
    flake_path = Path(temp_dir) / "flake.nix"
    flake_path.write_text(flake_content)

    if verbose:
        logger.debug("Generated flake.nix:\n%s", flake_content)

    _run_nix_build(temp_dir, verbose)
    _load_docker_image(temp_dir)


def _run_nix_build(temp_dir: str, verbose: bool) -> None:
    """Run nix build command."""
    cmd = ["nix", "build", "--impure", ".#image"]
    try:
        result = subprocess.run(
            cmd,
            cwd=temp_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        if verbose and result.stdout:
            logger.debug("nix build output:\n%s", result.stdout)
    except subprocess.CalledProcessError as exc:
        stderr_info = f":\n{exc.stderr}" if exc.stderr else ""
        raise BuildError(
            f"Nix build failed (exit code {exc.returncode}){stderr_info}"
        ) from exc


def _load_docker_image(temp_dir: str) -> None:
    """Load docker image from build result."""
    result_path = Path(temp_dir) / "result"
    try:
        subprocess.run(["docker", "load", "-i", str(result_path)], check=True)
    except subprocess.CalledProcessError as exc:
        raise DockerError(f"Docker load failed: {exc}") from exc


def image_exists(image_ref: "ImageRef") -> bool:
    """Check if a Docker image exists locally."""
    try:
        result: subprocess.CompletedProcess[bytes] = subprocess.run(
            ["docker", "image", "inspect", str(image_ref)],
            capture_output=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        # Docker command not found - assume image doesn't exist
        # This will trigger a build attempt which will fail with clearer error
        return False


def run_container(
    image_ref: "ImageRef",
    *,
    command: list[str] | None = None,
    ports: list[str] | None = None,
    volumes: list[str] | None = None,
    env: list[str] | None = None,
    tmpfs: list[str] | None = None,
    container_name: str | None = None,
    rm: bool = True,
    interactive: bool = True,
    tty: bool = True,
    workdir: str | None = None,
    user: str | None = None,
    detach: bool = False,
    extra_args: list[str] | None = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> None:
    """
    Run a Docker container.

    Args:
        image_ref: Image name and tag reference
        command: Command to run in the container
        ports: Port mappings
        volumes: Volume mounts
        env: Environment variables
        tmpfs: tmpfs mounts
        container_name: Name for the container
        rm: Whether to remove the container when it exits
        interactive: Whether to keep stdin open
        tty: Whether to allocate a pseudo-TTY
        workdir: Working directory inside the container
        user: User to run container as (uid:gid format, e.g., "1000:1000")
        detach: Whether to run in detached mode
        extra_args: Additional docker run arguments
        dry_run: If True, print the command without executing
        verbose: Whether to print verbose output

    Raises:
        DockerError: If the container fails to start
    """
    docker_cmd = _build_docker_command(
        image_ref=image_ref,
        command=command,
        ports=ports,
        volumes=volumes,
        env=env,
        tmpfs=tmpfs,
        container_name=container_name,
        rm=rm,
        interactive=interactive,
        tty=tty,
        workdir=workdir,
        user=user,
        detach=detach,
        extra_args=extra_args,
    )

    if dry_run:
        click.echo(" ".join(docker_cmd))
        return

    if verbose:
        logger.info("Executing command: %s", " ".join(docker_cmd))

    try:
        subprocess.run(docker_cmd, check=True)
    except subprocess.CalledProcessError as exc:
        # For interactive TTY mode, user exiting the shell is normal behavior
        if interactive and tty and exc.returncode in _NORMAL_EXIT_CODES:
            pass
        else:
            raise DockerError(f"Failed to run container: {exc}") from exc


def _build_docker_command(
    image_ref: "ImageRef",
    *,
    command: list[str] | None,
    ports: list[str] | None,
    volumes: list[str] | None,
    env: list[str] | None,
    tmpfs: list[str] | None,
    container_name: str | None,
    rm: bool,
    interactive: bool,
    tty: bool,
    workdir: str | None,
    user: str | None,
    detach: bool,
    extra_args: list[str] | None,
) -> list[str]:
    """Build the docker run command with all options."""
    cmd_parts: list[list[str]] = []

    # Base command
    cmd_parts.append(["docker", "run"])

    # Boolean flags
    cmd_parts.append(_build_boolean_flags(rm, interactive, tty, detach))

    # Named options
    cmd_parts.append(_build_named_options(container_name, workdir, user))

    # List options with flags
    cmd_parts.append(expand_flagged_options("-p", ports))
    cmd_parts.append(expand_flagged_options("-v", volumes))
    cmd_parts.append(expand_flagged_options("-e", env))
    cmd_parts.append(expand_flagged_options("--tmpfs", tmpfs))

    # Extra args from config
    if extra_args:
        cmd_parts.append(extra_args)

    # Image reference
    cmd_parts.append([str(image_ref)])

    # Command to execute
    if command:
        cmd_parts.append(command)

    # Flatten all parts
    return [arg for part in cmd_parts for arg in part]


def _build_boolean_flags(
    rm: bool, interactive: bool, tty: bool, detach: bool
) -> list[str]:
    """Build list of boolean flags for docker run."""
    # Use list comprehension with conditional expressions for clarity
    flags = [
        ("--rm" if rm else None),
        ("-i" if interactive else None),
        ("-t" if tty else None),
        ("-d" if detach else None),
    ]
    return [f for f in flags if f is not None]


def _build_named_options(
    container_name: str | None, workdir: str | None, user: str | None
) -> list[str]:
    """Build list of named options (key-value pairs) for docker run."""
    # Use itertools.chain to flatten conditional option pairs
    return list(
        chain(
            ("--name", container_name) if container_name else (),
            ("-w", workdir) if workdir else (),
            ("-u", user) if user else (),
        )
    )
