"""CLI interface using Click."""

import logging
import os
import re
import shlex
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import click

from . import __version__ as VERSION
from .builder import build_image, image_exists, run_container
from .config import (
    DevboxConfig,
    RunConfig,
    find_config,
    merge_devbox_configs,
)
from .core import _validate_mount_point, generate_flake
from .exceptions import DevboxError
from .models import DEFAULT_WORKDIR, FlakeRef, ImageRef
from .utils import extract_part_by_separator

if TYPE_CHECKING:
    from click import Context


# Constants
TEMP_DIR_PREFIX = "nix-devbox."

# Module logger
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def _sanitize_name_for_docker(value: str) -> str:
    """Sanitize a string for use as Docker image name.

    Docker image names must be lowercase and can only contain
    alphanumeric characters, hyphens, underscores, and periods.

    Args:
        value: The string to sanitize

    Returns:
        Sanitized string safe for use as image name component
    """
    # Replace non-alphanumeric chars with hyphens, collapse multiple hyphens
    sanitized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return sanitized or "devbox"


def _get_default_image_name() -> str:
    """Get default image name based on current directory name.

    Returns:
        Image name in format 'dirname-dev:latest'
    """
    dir_name = Path.cwd().name
    safe_name = _sanitize_name_for_docker(dir_name)
    return f"{safe_name}-dev:latest"


@dataclass(frozen=True)
class ContainerLaunchConfig:
    """Configuration for launching a container from CLI."""

    image_ref: ImageRef
    flake_refs: list[FlakeRef]
    container_name: str | None = None
    ports: list[str] = field(default_factory=list)
    volumes: list[str] = field(default_factory=list)
    env: list[str] = field(default_factory=list)
    workdir: str | None = None
    user: str | None = None
    detach: bool = False
    rm: bool = True
    rebuild: bool = False
    dry_run: bool = False
    verbose: bool = False
    command: str | None = None
    devbox_config: DevboxConfig | None = None


def format_flake_refs(refs: list[FlakeRef]) -> str:
    """Format flake references for display."""
    lines = ["DevShells to be merged:"]
    for i, ref in enumerate(refs, 1):
        lines.append(f"  {i}. {ref.path} -> {ref.shell}")
    lines.append("")
    return "\n".join(lines)


def build_image_with_progress(
    flake_refs: list[FlakeRef],
    image_ref: ImageRef,
    verbose: bool,
    dry_run: bool = False,
    mount_points: list[str] | None = None,
) -> None:
    """
    Build the Docker image with progress output.

    Args:
        flake_refs: List of flake references to merge
        image_ref: Target image reference
        verbose: Whether to print verbose output
        dry_run: If True, show flake content without building
        mount_points: List of directories to create in image for volume mounts

    Raises:
        DevboxError: If build fails
    """
    # Set UID/GID for flake generation (from environment or current user)
    os.environ["NIX_DEVBOX_UID"] = os.getenv("NIX_DEVBOX_UID", str(os.getuid()))
    os.environ["NIX_DEVBOX_GID"] = os.getenv("NIX_DEVBOX_GID", str(os.getgid()))
    flake_content = generate_flake(flake_refs, image_ref, mount_points)

    if dry_run:
        # Create temp directory without auto-cleanup so user can inspect it
        temp_dir = tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX)
        flake_path = Path(temp_dir) / "flake.nix"
        flake_path.write_text(flake_content)

        click.echo(f"Image name: {image_ref}")
        click.echo()
        click.secho("Generated files:", fg="cyan")
        click.echo(f"  Directory: {temp_dir}")
        click.echo(f"  Flake:     {flake_path}")
        return

    with tempfile.TemporaryDirectory(prefix=TEMP_DIR_PREFIX) as temp_dir:
        click.echo(f"Building image {image_ref}...")
        build_image(flake_content, image_ref, temp_dir, verbose)
        click.echo()
        click.secho(f"✅ Image built successfully: {image_ref}", fg="green")


@click.group(invoke_without_command=True)
@click.pass_context
@click.version_option(version=VERSION, prog_name="nix-devbox")
def cli(ctx: "Context") -> None:
    """
    Nix devbox - Merge multiple flake devShells, build and run Docker containers

    \b
    Usage examples:
        # Build image
        nix-devbox build /path/to/project1

        # Build and run
        nix-devbox run /path/to/project1

    \b
    Supported flake-ref formats:
        /path/to/flake              - Use default devShell
        /path/to/flake#shellname    - Use specified devShell
        /path/to/flake#devShells.x86_64-linux.shellname - Full attribute path
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


def _execute_build(
    flakes: tuple[str, ...],
    output: str,
    name: str | None,
    tag: str | None,
    verbose: bool,
    dry_run: bool = False,
) -> None:
    """Execute Docker image build with parsed arguments."""
    actual_output = output() if callable(output) else output
    image_ref = ImageRef.parse(actual_output, name_override=name, tag_override=tag)
    flake_refs = [FlakeRef.parse(ref) for ref in flakes]

    if verbose or dry_run:
        click.echo(format_flake_refs(flake_refs))

    # Load devbox config and collect mount points
    devbox_config = _load_devbox_config(flake_refs)
    mount_points: list[str] = []
    if devbox_config:
        # Extract container paths from volumes
        for vol in devbox_config.run.volumes:
            parts = vol.split(":")
            if len(parts) >= 2:
                mount_points.append(parts[1])
        # Note: tmpfs paths are not included here as they are mounted at runtime
        # Add ensure_dirs from init config
        mount_points.extend(devbox_config.init.ensure_dirs)

    build_image_with_progress(
        flake_refs, image_ref, verbose, dry_run, mount_points if mount_points else None
    )


@cli.command()
@click.argument("flakes", nargs=-1, required=True)
@click.option(
    "-o",
    "--output",
    default=_get_default_image_name,
    help="Output image name and tag (default: <dirname>-dev:latest)",
    metavar="name:tag",
)
@click.option("-n", "--name", help="Output image name (overrides --output)")
@click.option("-t", "--tag", help="Output image tag (overrides --output)")
@click.option("-v", "--verbose", is_flag=True, help="Show verbose output")
@click.option(
    "--dry-run", is_flag=True, help="Show generated flake.nix without building"
)
@click.pass_context
def build(
    ctx: "Context",
    flakes: tuple[str, ...],
    output: str,
    name: str | None,
    tag: str | None,
    verbose: bool,
    dry_run: bool,
) -> None:
    """Build Docker image."""
    try:
        _execute_build(flakes, output, name, tag, verbose, dry_run)
    except DevboxError as exc:
        raise click.ClickException(str(exc)) from exc


def _load_devbox_config(flake_refs: list[FlakeRef]) -> DevboxConfig:
    """Load and merge devbox configs from all flake directories.

    Configs are merged in order: first flake's config is the base,
    subsequent configs override/merge with it.
    """
    if not flake_refs:
        return DevboxConfig()

    # Load config from each flake directory
    configs = [
        find_config(Path(flake_ref.path) / "flake.nix") for flake_ref in flake_refs
    ]
    # Filter out default (empty) configs
    non_default_configs = [cfg for cfg in configs if cfg != DevboxConfig()]

    if not non_default_configs:
        return DevboxConfig()

    # Merge all configs
    return merge_devbox_configs(non_default_configs)


def _build_launch_config(
    flakes: tuple[str, ...],
    output: str,
    name: str | None,
    tag: str | None,
    container_name: str | None,
    port: tuple[str, ...],
    volume: tuple[str, ...],
    env: tuple[str, ...],
    workdir: str | None,
    user: str | None,
    detach: bool,
    no_rm: bool,
    rebuild: bool,
    dry_run: bool,
    verbose: bool,
    command: str | None,
) -> ContainerLaunchConfig:
    """Build container launch configuration from CLI arguments."""
    actual_output = output() if callable(output) else output
    flake_refs = [FlakeRef.parse(ref) for ref in flakes]
    devbox_config = _load_devbox_config(flake_refs)

    return ContainerLaunchConfig(
        image_ref=ImageRef.parse(actual_output, name_override=name, tag_override=tag),
        flake_refs=flake_refs,
        container_name=container_name,
        ports=list(port),
        volumes=list(volume),
        env=list(env),
        workdir=workdir,
        user=user,
        detach=detach,
        rm=not no_rm,
        rebuild=rebuild,
        dry_run=dry_run,
        verbose=verbose,
        command=command,
        devbox_config=devbox_config,
    )


def _execute_run(config: ContainerLaunchConfig) -> None:
    """Execute container run with the given configuration."""
    if config.verbose:
        click.echo(format_flake_refs(config.flake_refs))
        if config.devbox_config and config.devbox_config.run.resources.memory:
            click.echo("Using devbox config from flake directory")

    # Collect all directories that need to be created in the image
    # Includes: volume mount points and ensure_dirs (but not tmpfs - mounted at runtime)
    mount_points: list[str] = []
    if config.devbox_config:
        # Extract container paths from volumes
        for vol in config.devbox_config.run.volumes:
            # Volume format: host:container[:options]
            parts = vol.split(":")
            if len(parts) >= 2:
                mount_points.append(parts[1])
        # Note: tmpfs paths are excluded as they are mounted at runtime
        # Add ensure_dirs from init config
        mount_points.extend(config.devbox_config.init.ensure_dirs)

    _ensure_image_exists(
        flake_refs=config.flake_refs,
        image_ref=config.image_ref,
        force_rebuild=config.rebuild,
        verbose=config.verbose,
        mount_points=mount_points if mount_points else None,
    )
    _run_container_with_config(config)


@cli.command()
@click.argument("flakes", nargs=-1, required=True)
@click.option(
    "-o",
    "--output",
    default=_get_default_image_name,
    help="Image name and tag (default: <dirname>-dev:latest)",
    metavar="name:tag",
)
@click.option("-n", "--name", help="Image name (overrides --output)")
@click.option("-t", "--tag", help="Image tag (overrides --output)")
@click.option("--container-name", help="Container name")
@click.option(
    "-p",
    "--port",
    multiple=True,
    help="Port mapping (can be used multiple times, e.g., -p 8080:80)",
)
@click.option(
    "--volume",
    "-V",
    multiple=True,
    help="Volume mount (can be used multiple times, e.g., -V /host:/container)",
)
@click.option(
    "-e",
    "--env",
    multiple=True,
    help="Environment variable (can be used multiple times, e.g., -e KEY=value)",
)
@click.option("-w", "--workdir", help="Working directory")
@click.option(
    "-u",
    "--user",
    help="User to run container as (uid:gid format, e.g., '1000:1000')",
)
@click.option("-d", "--detach", is_flag=True, help="Run container in background")
@click.option("--no-rm", is_flag=True, help="Do not remove container after it stops")
@click.option("--rebuild", is_flag=True, help="Force rebuild image")
@click.option("--dry-run", is_flag=True, help="Show commands without executing")
@click.option("--verbose", "-v", is_flag=True, help="Show verbose output")
@click.option("--command", "--cmd", help="Command to execute in container (quote it)")
@click.pass_context
def run(
    ctx: "Context",
    flakes: tuple[str, ...],
    output: str,
    name: str | None,
    tag: str | None,
    container_name: str | None,
    port: tuple[str, ...],
    volume: tuple[str, ...],
    env: tuple[str, ...],
    workdir: str | None,
    user: str | None,
    detach: bool,
    no_rm: bool,
    rebuild: bool,
    dry_run: bool,
    verbose: bool,
    command: str | None,
) -> None:
    """Run container (auto-builds image if not exists)."""
    config = _build_launch_config(
        flakes=flakes,
        output=output,
        name=name,
        tag=tag,
        container_name=container_name,
        port=port,
        volume=volume,
        env=env,
        workdir=workdir,
        user=user,
        detach=detach,
        no_rm=no_rm,
        rebuild=rebuild,
        dry_run=dry_run,
        verbose=verbose,
        command=command,
    )

    try:
        _execute_run(config)
    except DevboxError as exc:
        raise click.ClickException(str(exc)) from exc


def _ensure_image_exists(
    *,
    flake_refs: list[FlakeRef],
    image_ref: ImageRef,
    force_rebuild: bool,
    verbose: bool,
    mount_points: list[str] | None = None,
) -> None:
    """Build image if needed."""
    if force_rebuild:
        click.echo(f"Force rebuilding image {image_ref}...")
        build_image_with_progress(
            flake_refs, image_ref, verbose, mount_points=mount_points
        )
        return

    if image_exists(image_ref):
        return

    click.echo(f"Image {image_ref} not found, building...")
    build_image_with_progress(flake_refs, image_ref, verbose, mount_points=mount_points)


def _make_parser(separator: str, index: int) -> Callable[[str], tuple[str, str]]:
    """Create a parser function that extracts a key and returns (key, original).

    Args:
        separator: The separator to split on
        index: Which part to use as the key

    Returns:
        Parser function suitable for _merge_mappings
    """
    return lambda value: (extract_part_by_separator(value, separator, index), value)


# Predefined parsers for common mapping types
_parse_port_mapping = _make_parser(":", 0)  # host:container -> (host, original)
_parse_volume_mapping = _make_parser(":", 1)  # host:container -> (container, original)
_parse_env_var = _make_parser("=", 0)  # KEY=value -> (KEY, original)
_parse_tmpfs = _make_parser(":", 0)  # /path:opts -> (/path, original)


def _merge_mappings(
    base: list[str],
    overrides: list[str],
    parse_func: Callable[[str], tuple[str, str]],
) -> list[str]:
    """
    Merge mappings with CLI overrides taking precedence.

    Uses a dict to track unique keys, allowing O(1) lookup for duplicates.
    Order is preserved: base items first (unless overridden), then overrides.

    Args:
        base: Base mappings from config file
        overrides: CLI override mappings
        parse_func: Function to parse (key, full_value) from a mapping

    Returns:
        Merged list with overrides applied
    """
    if not overrides:
        return list(base)

    # Build lookup of override keys to their full values
    override_items = dict(parse_func(item) for item in overrides)

    # Start with base items, filtering out those that are overridden
    result = [item for item in base if parse_func(item)[0] not in override_items]

    # Append all override items (preserving CLI order)
    result.extend(overrides)

    return result


def _validate_volume_path(volume_spec: str) -> str:
    """Validate volume mount path.

    Volume format: host:container[:options]
    Raises error if container path conflicts with RESERVED_PATHS.

    Args:
        volume_spec: Volume specification string

    Returns:
        Original volume specification (unchanged)

    Raises:
        ValueError: If container path conflicts with RESERVED_PATHS
    """
    parts = volume_spec.split(":")
    if len(parts) < 2:
        return volume_spec

    container_path = parts[1]

    # Validate container path (raises error if reserved)
    _validate_mount_point(container_path)

    return volume_spec


def _prepare_container_config(
    config: ContainerLaunchConfig,
) -> dict[str, Any]:
    """Prepare docker run configuration by merging file and CLI settings.

    Args:
        config: Container launch configuration from CLI

    Returns:
        Keyword arguments dict for run_container()
    """
    # Get config from file or use empty defaults
    file_config = config.devbox_config.run if config.devbox_config else RunConfig()

    # Build extra args from config file (only non-list args)
    extra_args = file_config._to_non_list_docker_args()

    # Merge config file values with CLI overrides (CLI takes precedence)
    merged_ports = _merge_mappings(
        file_config.ports, config.ports, parse_func=_parse_port_mapping
    )
    # Add default volume mount (current directory -> /workspace)
    default_volumes = [f"{os.getcwd()}:{DEFAULT_WORKDIR}"]
    merged_volumes = _merge_mappings(
        file_config.volumes, default_volumes, parse_func=_parse_volume_mapping
    )
    # Apply CLI volume overrides
    merged_volumes = _merge_mappings(
        merged_volumes, config.volumes, parse_func=_parse_volume_mapping
    )
    merged_env = _merge_mappings(file_config.env, config.env, parse_func=_parse_env_var)
    merged_tmpfs = _merge_mappings(
        file_config.tmpfs, [], parse_func=_parse_tmpfs  # tmpfs only from config file
    )

    # Auto-inject USER_ID and GROUP_ID for entrypoint to use
    env_keys = {_parse_env_var(item)[0] for item in merged_env}
    if "USER_ID" not in env_keys:
        merged_env.append(f"USER_ID={os.getuid()}")
    if "GROUP_ID" not in env_keys:
        merged_env.append(f"GROUP_ID={os.getgid()}")

    parsed_cmd = shlex.split(config.command) if config.command else None
    merged_user = config.user if config.user is not None else file_config.user

    # Validate volume paths (raises error if conflicts with RESERVED_PATHS)
    for v in merged_volumes:
        _validate_volume_path(v)

    # Validate working directory if specified
    if config.workdir:
        _validate_mount_point(config.workdir)

    return {
        "command": parsed_cmd,
        "ports": merged_ports,
        "volumes": merged_volumes,
        "env": merged_env,
        "tmpfs": merged_tmpfs,
        "container_name": config.container_name,
        "rm": config.rm,
        "interactive": not config.detach,
        "tty": not config.detach,
        "workdir": config.workdir,
        "user": merged_user,
        "detach": config.detach,
        "extra_args": extra_args,
        "dry_run": config.dry_run,
        "verbose": config.verbose,
    }


def _run_container_with_config(config: ContainerLaunchConfig) -> None:
    """Run container with the specified configuration."""
    run_kwargs = _prepare_container_config(config)

    if config.dry_run:
        click.echo("Commands to be executed:")
    else:
        click.echo(f"Starting container {config.image_ref}...")

    run_container(config.image_ref, **run_kwargs)

    if not config.detach and not config.dry_run:
        click.echo()
        click.secho("✅ Container stopped", fg="green")


if __name__ == "__main__":
    cli()
