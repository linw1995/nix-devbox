"""CLI interface using Click."""

import os
import re
import shlex
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import click

from . import __version__ as VERSION
from .builder import build_image, image_exists, run_container
from .config import (
    DevboxConfig,
    RunConfig,
    _extract_part_by_separator,
    find_config,
    merge_devbox_configs,
)
from .core import generate_flake
from .exceptions import DevboxError
from .models import FlakeRef, ImageRef

if TYPE_CHECKING:
    from click import Context


# Constants
TEMP_DIR_PREFIX = "nix-devbox."
PERMISSION_EVERYONE_READ_WRITE_EXECUTE = 0o777  # For directory creation fallback


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
    ports: tuple[str, ...] = ()
    volumes: tuple[str, ...] = ()
    env: tuple[str, ...] = ()
    workdir: str | None = None
    user: str | None = None
    detach: bool = False
    no_rm: bool = False
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
) -> None:
    """
    Build the Docker image with progress output.

    Args:
        flake_refs: List of flake references to merge
        image_ref: Target image reference
        verbose: Whether to print verbose output

    Raises:
        DevboxError: If build fails
    """
    flake_content = generate_flake(flake_refs, image_ref)

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
@click.pass_context
def build(
    ctx: "Context",
    flakes: tuple[str, ...],
    output: str,
    name: str | None,
    tag: str | None,
    verbose: bool,
) -> None:
    """Build Docker image."""
    # Handle callable default (Click passes the callable when using default=function)
    actual_output = output() if callable(output) else output
    image_ref = ImageRef.parse(actual_output, name_override=name, tag_override=tag)
    flake_refs = [FlakeRef.parse(ref) for ref in flakes]

    if verbose:
        click.echo(format_flake_refs(flake_refs))

    try:
        build_image_with_progress(flake_refs, image_ref, verbose)
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
    # Handle callable default
    actual_output = output() if callable(output) else output

    flake_refs = [FlakeRef.parse(ref) for ref in flakes]

    # Load config from the first flake directory
    devbox_config = _load_devbox_config(flake_refs)

    config = ContainerLaunchConfig(
        image_ref=ImageRef.parse(actual_output, name_override=name, tag_override=tag),
        flake_refs=flake_refs,
        container_name=container_name,
        ports=port,
        volumes=volume,
        env=env,
        workdir=workdir,
        user=user,
        detach=detach,
        no_rm=no_rm,
        rebuild=rebuild,
        dry_run=dry_run,
        verbose=verbose,
        command=command,
        devbox_config=devbox_config,
    )

    if config.verbose:
        click.echo(format_flake_refs(config.flake_refs))
        if devbox_config.run.resources.memory:
            click.echo("Using devbox config from flake directory")

    try:
        _ensure_image_exists(
            flake_refs=config.flake_refs,
            image_ref=config.image_ref,
            force_rebuild=config.rebuild,
            verbose=config.verbose,
        )
        _run_container_with_config(config)
    except DevboxError as exc:
        raise click.ClickException(str(exc)) from exc


def _ensure_image_exists(
    *,
    flake_refs: list[FlakeRef],
    image_ref: ImageRef,
    force_rebuild: bool,
    verbose: bool,
) -> None:
    """Build image if needed."""
    if force_rebuild:
        click.echo(f"Force rebuilding image {image_ref}...")
        build_image_with_progress(flake_refs, image_ref, verbose)
        return

    if image_exists(image_ref):
        return

    click.echo(f"Image {image_ref} not found, building...")
    build_image_with_progress(flake_refs, image_ref, verbose)


def _make_parser(separator: str, index: int) -> Callable[[str], tuple[str, str]]:
    """Create a parser function that extracts a key and returns (key, original).

    Args:
        separator: The separator to split on
        index: Which part to use as the key

    Returns:
        Parser function suitable for _merge_mappings
    """
    return lambda value: (_extract_part_by_separator(value, separator, index), value)


# Predefined parsers for common mapping types
_parse_port_mapping = _make_parser(":", 0)  # host:container -> (host, original)
_parse_volume_mapping = _make_parser(":", 1)  # host:container -> (container, original)
_parse_env_var = _make_parser("=", 0)  # KEY=value -> (KEY, original)
_parse_tmpfs = _make_parser(":", 0)  # /path:opts -> (/path, original)


def _merge_mappings(
    base: list[str],
    overrides: tuple[str, ...],
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
    merged_volumes = _merge_mappings(
        file_config.volumes, config.volumes, parse_func=_parse_volume_mapping
    )
    merged_env = _merge_mappings(file_config.env, config.env, parse_func=_parse_env_var)
    merged_tmpfs = _merge_mappings(
        file_config.tmpfs, (), parse_func=_parse_tmpfs  # tmpfs only from config file
    )

    # Auto-inject USER_ID and GROUP_ID to match current user
    # This ensures the container has correct permissions on mounted volumes
    env_keys = {_parse_env_var(item)[0] for item in merged_env}

    if "USER_ID" not in env_keys:
        merged_env.append(f"USER_ID={os.getuid()}")
    if "GROUP_ID" not in env_keys:
        merged_env.append(f"GROUP_ID={os.getgid()}")

    parsed_cmd = shlex.split(config.command) if config.command else None

    # User: CLI takes precedence over config file
    # If CLI doesn't specify, use config file value
    # If config file doesn't specify, default to None (entrypoint will handle user switching)
    # The entrypoint starts as root and switches to nixbld automatically
    merged_user = config.user
    if merged_user is None:
        merged_user = file_config.user
    # Note: We no longer default to current user here because the entrypoint
    # handles user switching. Setting -u would prevent entrypoint from using gosu.

    return {
        "command": parsed_cmd,
        "ports": merged_ports,
        "volumes": merged_volumes,
        "env": merged_env,
        "tmpfs": merged_tmpfs,
        "container_name": config.container_name,
        "rm": not config.no_rm,
        "interactive": not config.detach,
        "tty": not config.detach,
        "workdir": config.workdir,
        "user": merged_user,
        "detach": config.detach,
        "extra_args": extra_args,
        "dry_run": config.dry_run,
        "verbose": config.verbose,
    }


def _parse_host_path(volume: str) -> str | None:
    """Extract host path from volume mapping.

    Args:
        volume: Volume mapping string (e.g., "/host:/container:rw")

    Returns:
        Host path or None if not a bind mount
    """
    # Handle named volumes and tmpfs differently
    if volume.startswith("/") or volume.startswith("$") or volume.startswith("~"):
        # Bind mount - extract host path (before first colon)
        return volume.split(":")[0]
    return None


def _ensure_directory_with_ownership(path: Path) -> None:
    """Ensure directory exists with current user ownership.

    Creates directory if not exists, or fixes ownership if root-owned.
    """
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        return

    if path.stat().st_uid != 0:  # Not root-owned, nothing to fix
        return

    # Try to change ownership to current user
    try:
        shutil.chown(path, user=os.getuid(), group=os.getgid())
        return
    except (PermissionError, OSError):
        pass  # Fall through to chmod fallback

    # Fallback: make directory writable by everyone
    try:
        os.chmod(path, PERMISSION_EVERYONE_READ_WRITE_EXECUTE)
    except (PermissionError, OSError):
        pass  # Best effort failed, continue anyway


def _prepare_host_volumes(volumes: list[str]) -> None:
    """Prepare host directories for volume mounts.

    This ensures both the mount point and its parent directories exist on the host
    with correct permissions. When Docker creates missing directories, they become
    root-owned, which prevents container users from creating sibling directories.

    For example, mounting host:~/.config/app:/build/.config/app requires:
    - ~/.config/app to exist (mount point)
    - ~/.config to exist (parent, so Docker doesn't create /build/.config as root)

    Args:
        volumes: List of volume mappings
    """
    for volume in volumes:
        host_path = _parse_host_path(volume)
        if not host_path:
            continue

        # Expand ~ and environment variables
        expanded = os.path.expanduser(os.path.expandvars(host_path))
        if expanded.startswith(("~", "$")):
            # Path still contains unexpanded variables, skip to avoid creating
            # directories with literal '~' or '$' in the name
            continue

        try:
            path = Path(expanded)

            # Create the mount point directory itself
            _ensure_directory_with_ownership(path)

            # Also ensure parent directory exists to prevent Docker from
            # creating it as root in the container
            parent = path.parent
            if parent:
                _ensure_directory_with_ownership(parent)

        except (OSError, PermissionError):
            pass


def _run_container_with_config(config: ContainerLaunchConfig) -> None:
    """Run container with the specified configuration."""
    run_kwargs = _prepare_container_config(config)

    # Prepare host volumes (create directories, fix permissions)
    if not config.dry_run:
        _prepare_host_volumes(run_kwargs.get("volumes", []))

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
