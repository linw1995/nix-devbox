"""Docker image building and container running functionality."""

import logging
import subprocess
from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING

from .exceptions import BuildError, DockerError
from .utils import expand_flagged_options

if TYPE_CHECKING:
    from .models import ImageRef

logger = logging.getLogger(__name__)
# Add null handler to avoid "No handler found" warnings
logger.addHandler(logging.NullHandler())


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
        subprocess.run(
            cmd,
            cwd=temp_dir,
            capture_output=not verbose,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr
        error_msg = f"Nix build failed (exit code {exc.returncode})"
        if stderr:
            error_msg += f":\n{stderr}"
        raise BuildError(error_msg) from exc


def _load_docker_image(temp_dir: str) -> None:
    """Load docker image from build result."""
    result_path = Path(temp_dir) / "result"
    try:
        subprocess.run(["docker", "load", "-i", str(result_path)], check=True)
    except subprocess.CalledProcessError as exc:
        raise DockerError(f"Docker import failed: {exc}") from exc


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
        detach=detach,
        extra_args=extra_args,
    )

    if dry_run:
        print(" ".join(docker_cmd))
        return

    if verbose:
        logger.info("Executing command: %s", " ".join(docker_cmd))

    try:
        subprocess.run(docker_cmd, check=True)
    except subprocess.CalledProcessError as exc:
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
    cmd_parts.append(_build_named_options(container_name, workdir))

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
    # Build flags list conditionally
    flags: list[str] = []
    if rm:
        flags.append("--rm")
    if interactive:
        flags.append("-i")
    if tty:
        flags.append("-t")
    if detach:
        flags.append("-d")
    return flags


def _build_named_options(container_name: str | None, workdir: str | None) -> list[str]:
    """Build list of named options (key-value pairs) for docker run."""
    # Use itertools.chain to flatten conditional option pairs
    return list(
        chain(
            ("--name", container_name) if container_name else (),
            ("-w", workdir) if workdir else (),
        )
    )
