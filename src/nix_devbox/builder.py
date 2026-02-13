"""Docker image building and container running functionality."""

import logging
import os
import shlex
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import click

from .exceptions import BuildError, DockerError

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
    if verbose:
        cmd.extend(["-vv", "--print-build-logs"])
    try:
        if verbose:
            # In verbose mode, show output in real-time
            subprocess.run(cmd, cwd=temp_dir, check=True)
        else:
            result = subprocess.run(
                cmd,
                cwd=temp_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            if result.stdout:
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
    cmd_str = _build_docker_command_string(
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
        click.echo(cmd_str)
        return

    if verbose:
        logger.info("Executing command: %s", cmd_str)

    # Execute via $SHELL -c to allow shell variable expansion
    shell = os.environ.get("SHELL", "/bin/sh")
    try:
        subprocess.run([shell, "-c", cmd_str], check=True)
    except subprocess.CalledProcessError as exc:
        # For interactive TTY mode, user exiting the shell is normal behavior
        if interactive and tty and exc.returncode in _NORMAL_EXIT_CODES:
            pass
        else:
            raise DockerError(f"Failed to run container: {exc}") from exc


def _build_docker_command_string(
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
) -> str:
    """Build the docker run command as a shell command string.

    Values are not quoted to allow shell variable expansion ($VAR, $(cmd)).
    """
    parts: list[str] = []

    # Base command
    parts.append("docker run")

    # Boolean flags
    if rm:
        parts.append("--rm")
    if interactive:
        parts.append("-i")
    if tty:
        parts.append("-t")
    if detach:
        parts.append("-d")

    # Named options
    if container_name:
        parts.append(f"--name={container_name}")
    if workdir:
        parts.append(f"-w={workdir}")
    if user:
        parts.append(f"-u={user}")

    # List options - values are passed as-is for shell expansion
    for port in ports or []:
        parts.append(f"-p={port}")
    for volume in volumes or []:
        parts.append(f"-v={volume}")
    for e in env or []:
        parts.append(f"-e={e}")
    for tmp in tmpfs or []:
        parts.append(f"--tmpfs={tmp}")

    # Extra args from config
    for arg in extra_args or []:
        parts.append(arg)

    # Image reference
    parts.append(shlex.quote(str(image_ref)))

    # Command to execute
    if command:
        # Quote each command part to handle spaces, but preserve $ for expansion
        cmd_str = " ".join(shlex.quote(arg) for arg in command)
        parts.append(cmd_str)

    return " ".join(parts)
