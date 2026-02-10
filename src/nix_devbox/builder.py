"""Docker image building and container running functionality."""

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from .exceptions import BuildError, DockerError

if TYPE_CHECKING:
    from .models import ImageRef

logger = logging.getLogger(__name__)
# Add null handler to avoid "No handler found" warnings
logger.addHandler(logging.NullHandler())


def build_image(
    flake_content: str,
    image_ref: "ImageRef",
    tmp_dir: str,
    verbose: bool = False,
) -> None:
    """
    Build and load Docker image from flake.nix content.

    Args:
        flake_content: The generated flake.nix content
        image_ref: Image name and tag reference
        tmp_dir: Temporary directory for building
        verbose: Whether to print verbose output

    Raises:
        BuildError: If the build fails
        DockerError: If docker load fails
    """
    flake_path = Path(tmp_dir) / "flake.nix"
    flake_path.write_text(flake_content)

    if verbose:
        logger.debug("Generated flake.nix:\n%s", flake_content)

    _run_nix_build(tmp_dir, verbose)
    _load_docker_image(tmp_dir)


def _run_nix_build(tmp_dir: str, verbose: bool) -> None:
    """Run nix build command."""
    try:
        subprocess.run(
            ["nix", "build", "--impure", ".#image"],
            cwd=tmp_dir,
            capture_output=not verbose,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr
        raise BuildError(
            f"Build failed: {exc}\n{stderr}" if stderr else f"Build failed: {exc}"
        ) from exc


def _load_docker_image(tmp_dir: str) -> None:
    """Load docker image from build result."""
    result_path = Path(tmp_dir) / "result"
    try:
        subprocess.run(["docker", "load", "-i", str(result_path)], check=True)
    except subprocess.CalledProcessError as exc:
        raise DockerError(f"Docker import failed: {exc}") from exc


def image_exists(image_ref: "ImageRef") -> bool:
    """Check if a Docker image exists locally."""
    result = subprocess.run(
        ["docker", "image", "inspect", str(image_ref)],
        capture_output=True,
    )
    return result.returncode == 0


def run_container(
    image_ref: "ImageRef",
    *,
    command: list[str] | None = None,
    ports: list[str] | None = None,
    volumes: list[str] | None = None,
    env: list[str] | None = None,
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
    container_name: str | None,
    rm: bool,
    interactive: bool,
    tty: bool,
    workdir: str | None,
    detach: bool,
    extra_args: list[str] | None,
) -> list[str]:
    """Build the docker run command with all options."""
    docker_cmd = ["docker", "run"]

    # Add boolean flags
    flags = [
        (rm, "--rm"),
        (interactive, "-i"),
        (tty, "-t"),
        (detach, "-d"),
    ]
    for condition, flag in flags:
        if condition:
            docker_cmd.append(flag)

    # Add named options
    if container_name:
        docker_cmd.extend(["--name", container_name])

    if workdir:
        docker_cmd.extend(["-w", workdir])

    # Add list options
    for port in ports or []:
        docker_cmd.extend(["-p", port])

    for volume in volumes or []:
        docker_cmd.extend(["-v", volume])

    for env_var in env or []:
        docker_cmd.extend(["-e", env_var])

    if extra_args:
        docker_cmd.extend(extra_args)

    docker_cmd.append(str(image_ref))

    if command:
        docker_cmd.extend(command)

    return docker_cmd
