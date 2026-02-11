"""CLI interface using Click."""

import os
import shlex
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import click

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
VERSION = "0.1.0"
DEFAULT_IMAGE = "devbox:latest"
TEMP_DIR_PREFIX = "nix-devbox."


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


def _echo_build_start(image_ref: ImageRef) -> None:
    """Display build start message."""
    click.echo(f"Building image {image_ref}...")


def _echo_build_complete(image_ref: ImageRef) -> None:
    """Display build completion message."""
    click.echo()
    click.secho(f"✅ Image built successfully: {image_ref}", fg="green")


def build_image_with_progress(
    flake_refs: list[FlakeRef],
    image_ref: ImageRef,
    verbose: bool,
    init_commands: list[str] | None = None,
) -> None:
    """
    Build the Docker image with progress output.

    Args:
        flake_refs: List of flake references to merge
        image_ref: Target image reference
        verbose: Whether to print verbose output
        init_commands: Optional list of commands to run when shell starts

    Raises:
        DevboxError: If build fails
    """
    flake_content = generate_flake(flake_refs, image_ref, init_commands)

    with tempfile.TemporaryDirectory(prefix=TEMP_DIR_PREFIX) as temp_dir:
        _echo_build_start(image_ref)
        build_image(flake_content, image_ref, temp_dir, verbose)
        _echo_build_complete(image_ref)


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
    default=DEFAULT_IMAGE,
    help="Output image name and tag (default: devbox:latest)",
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
    image_ref = ImageRef.parse(output, name_override=name, tag_override=tag)
    flake_refs = [FlakeRef.parse(ref) for ref in flakes]

    # Load and merge devbox configs to get init commands
    devbox_config = _load_devbox_config(flake_refs)
    init_commands = (
        devbox_config.init.commands if devbox_config and devbox_config.init else []
    )

    if verbose:
        click.echo(format_flake_refs(flake_refs))
        if init_commands:
            click.echo(f"Init commands: {init_commands}")

    try:
        build_image_with_progress(flake_refs, image_ref, verbose, init_commands)
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
    configs = []
    for flake_ref in flake_refs:
        flake_path = Path(flake_ref.path) / "flake.nix"
        config = find_config(flake_path)
        # Only add non-default configs
        if config != DevboxConfig():
            configs.append(config)

    if not configs:
        return DevboxConfig()

    # Merge all configs
    return merge_devbox_configs(configs)


@cli.command()
@click.argument("flakes", nargs=-1, required=True)
@click.option(
    "-o",
    "--output",
    default=DEFAULT_IMAGE,
    help="Image name and tag (default: devbox:latest)",
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
    flake_refs = [FlakeRef.parse(ref) for ref in flakes]

    # Load config from the first flake directory
    devbox_config = _load_devbox_config(flake_refs)

    config = ContainerLaunchConfig(
        image_ref=ImageRef.parse(output, name_override=name, tag_override=tag),
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

    # Extract init commands from merged config
    file_init = config.devbox_config.init if config.devbox_config else None
    init_commands = file_init.commands if file_init else []

    try:
        _ensure_image_exists(
            flake_refs=config.flake_refs,
            image_ref=config.image_ref,
            force_rebuild=config.rebuild,
            verbose=config.verbose,
            init_commands=init_commands,
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
    init_commands: list[str] | None = None,
) -> None:
    """Build image if needed."""
    if force_rebuild:
        click.echo(f"Force rebuilding image {image_ref}...")
        build_image_with_progress(flake_refs, image_ref, verbose, init_commands)
        return

    if image_exists(image_ref):
        return

    click.echo(f"Image {image_ref} not found, building...")
    build_image_with_progress(flake_refs, image_ref, verbose, init_commands)


def _parse_port_mapping(mapping: str) -> tuple[str, str]:
    """Parse port mapping 'host:container' into (host_port, full_mapping)."""
    host_port = _extract_part_by_separator(mapping, ":", 0)
    return host_port, mapping


def _parse_volume_mapping(mapping: str) -> tuple[str, str]:
    """Parse volume mapping 'host:container[:opts]' into (container_path, full_mapping)."""
    container_path = _extract_part_by_separator(mapping, ":", 1)
    return container_path, mapping


def _parse_env_var(env_var: str) -> tuple[str, str]:
    """Parse env var 'KEY=value' into (key, full_var)."""
    key = _extract_part_by_separator(env_var, "=", 0)
    return key, env_var


def _parse_tmpfs(tmpfs: str) -> tuple[str, str]:
    """Parse tmpfs mount '/path[:opts]' into (path, full_spec).

    Examples:
        /tmp:size=100m,mode=1777 -> ("/tmp", "/tmp:size=100m,mode=1777")
        /var/cache -> ("/var/cache", "/var/cache")
    """
    path = _extract_part_by_separator(tmpfs, ":", 0)
    return path, tmpfs


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
    current_uid = os.getuid()
    current_gid = os.getgid()

    # Check if USER_ID/GROUP_ID are already set (CLI or config file)
    env_keys = {_parse_env_var(item)[0] for item in merged_env}
    if "USER_ID" not in env_keys:
        merged_env.append(f"USER_ID={current_uid}")
    if "GROUP_ID" not in env_keys:
        merged_env.append(f"GROUP_ID={current_gid}")

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
    import os
    from pathlib import Path

    for volume in volumes:
        host_path = _parse_host_path(volume)
        if not host_path:
            continue

        # Expand environment variables
        expanded = os.path.expandvars(host_path)
        if expanded.startswith("$"):
            continue

        try:
            path = Path(expanded)

            # Create the mount point directory itself
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
            elif path.stat().st_uid == 0:  # root-owned, try to fix
                try:
                    import shutil

                    shutil.chown(path, user=os.getuid(), group=os.getgid())
                except (PermissionError, OSError):
                    try:
                        os.chmod(path, 0o777)
                    except (PermissionError, OSError):
                        pass

            # Also ensure parent directory exists to prevent Docker from
            # creating it as root in the container
            parent = path.parent
            if parent and not parent.exists():
                parent.mkdir(parents=True, exist_ok=True)
            elif parent and parent.exists() and parent.stat().st_uid == 0:
                # Parent is root-owned, this will cause permission issues
                # for sibling directories in container (e.g., /build/.cache)
                try:
                    import shutil

                    shutil.chown(parent, user=os.getuid(), group=os.getgid())
                except (PermissionError, OSError):
                    try:
                        os.chmod(parent, 0o777)
                    except (PermissionError, OSError):
                        pass

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
