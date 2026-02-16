"""CLI interface using Click."""

import hashlib
import logging
import os
import re
import shlex
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import click

from . import __commit_sha__, __is_dirty__, __version__ as VERSION
from .builder import build_image, get_image_labels, image_exists, run_container
from .config import (
    DEFAULT_REGISTRY,
    DevboxConfig,
    RunConfig,
    find_config,
    find_config_in_directory,
    merge_devbox_configs,
)
from .core import _validate_mount_point, generate_flake
from .exceptions import DevboxError
from .models import DEFAULT_WORKDIR, FlakeRef, ImageRef, VersionInfo, get_flake_fetcher
from .utils import extract_part_by_separator

if TYPE_CHECKING:
    from click import Context


# Constants
TEMP_DIR_PREFIX = "nix-devbox."

# Module logger
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def _get_flake_lock_hash(
    flake_refs: list[FlakeRef],
    image_ref: ImageRef,
    version_info: VersionInfo,
    mount_points: list[str] | None = None,
) -> str | None:
    """Compute MD5 hash of merged flake's lock file.

    Creates a temp directory, generates the merged flake.nix,
    runs nix flake metadata to create lock file, then computes hash.

    Args:
        flake_refs: List of flake references
        image_ref: Image reference (for flake generation)
        version_info: Version info (for flake generation)
        mount_points: Mount points (for flake generation)

    Returns:
        MD5 hash string, or None if failed
    """
    with tempfile.TemporaryDirectory(prefix=TEMP_DIR_PREFIX) as temp_dir:
        flake_content = generate_flake(
            flake_refs, image_ref, version_info, mount_points
        )
        flake_path = Path(temp_dir) / "flake.nix"
        flake_path.write_text(flake_content)

        try:
            subprocess.run(
                ["nix", "flake", "metadata", temp_dir],
                capture_output=True,
                check=True,
            )
        except subprocess.CalledProcessError:
            return None

        lock_path = Path(temp_dir) / "flake.lock"
        if not lock_path.exists():
            return None

        md5 = hashlib.md5()
        md5.update(lock_path.read_bytes())
        return md5.hexdigest()


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
    version_info: VersionInfo
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
        lines.append(f"  {i}. {ref.uri.raw} -> {ref.shell}")
    lines.append("")
    return "\n".join(lines)


def build_image_with_progress(
    flake_refs: list[FlakeRef],
    image_ref: ImageRef,
    version_info: VersionInfo,
    verbose: bool,
    dry_run: bool = False,
    mount_points: list[str] | None = None,
) -> str | None:
    """
    Build the Docker image with progress output.

    Args:
        flake_refs: List of flake references to merge
        image_ref: Target image reference
        version_info: Version information to embed in the image
        verbose: Whether to print verbose output
        dry_run: If True, show flake content without building
        mount_points: List of directories to create in image for volume mounts

    Returns:
        Lock hash string if flake.lock exists, None otherwise

    Raises:
        DevboxError: If build fails
    """
    flake_content = generate_flake(flake_refs, image_ref, version_info, mount_points)

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
        return None

    with tempfile.TemporaryDirectory(prefix=TEMP_DIR_PREFIX) as temp_dir:
        click.echo(f"Building image {image_ref}...")
        lock_hash = build_image(flake_content, image_ref, temp_dir, verbose)
        click.echo()
        click.secho(f"✅ Image built successfully: {image_ref}", fg="green")
        commit = version_info.commit_sha or "unknown"
        click.echo(f"   nix-devbox: {version_info.version} ({commit})")
        if lock_hash:
            click.echo(f"   flake lock: {lock_hash}")
        return lock_hash


def _get_version() -> str:
    """Get version string with commit info."""
    commit = __commit_sha__ if __commit_sha__ else "unknown"
    if __is_dirty__ and __commit_sha__:
        commit += "+dirty"
    return f"nix-devbox {VERSION}\ncommit: {commit}"


@click.group(invoke_without_command=True)
@click.pass_context
@click.version_option(message=_get_version(), prog_name="nix-devbox")
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


def _resolve_flake_refs(
    flakes: tuple[str, ...], devbox_config: DevboxConfig | None = None
) -> list[FlakeRef]:
    """Resolve flake references, expanding registry references.

    Args:
        flakes: Raw flake references from CLI
        devbox_config: Optional devbox config for registry resolution

    Returns:
        List of resolved FlakeRef objects
    """
    # Get registry from config or use empty
    registry = devbox_config.get_registry() if devbox_config else dict(DEFAULT_REGISTRY)

    resolved_refs = []
    for ref in flakes:
        if ref.startswith("@"):
            # Registry reference - resolve it
            resolved_url = _resolve_registry_ref(ref, registry)
            resolved_refs.append(FlakeRef.parse(resolved_url))
        else:
            # Regular flake reference
            resolved_refs.append(FlakeRef.parse(ref))

    return resolved_refs


def _resolve_registry_ref(ref: str, registry: dict[str, str]) -> str:
    """Resolve a registry reference to full URL.

    Args:
        ref: Registry reference like "@name/path" or "@name"
        registry: Registry dictionary mapping names to URLs

    Returns:
        Full flake URL

    Raises:
        DevboxError: If registry name is not found
    """
    # Remove @ prefix
    ref = ref[1:]

    # Split into name and path
    if "/" in ref:
        name, path = ref.split("/", 1)
    else:
        name = ref
        path = ""

    if name not in registry:
        available = ", ".join(registry.keys())
        raise DevboxError(f"Unknown registry '{name}'. Available: {available}")

    base_url = registry[name]

    # Append path to base URL
    if path:
        # Handle ?dir= parameter in base URL
        if "?dir=" in base_url:
            base_part, dir_part = base_url.split("?dir=", 1)
            return f"{base_part}?dir={dir_part}{path}"
        else:
            return f"{base_url}{path}"

    return base_url


def _expand_extends(
    flakes: tuple[str, ...], devbox_config: DevboxConfig
) -> tuple[str, ...]:
    """Expand extends from devbox.yaml into flake references.

    If current directory has extends defined, prepend them to the flakes list.

    Args:
        flakes: Original flake references from CLI
        devbox_config: Loaded devbox configuration

    Returns:
        Expanded tuple with extends first, then original flakes
    """
    if not devbox_config.extends:
        return flakes

    # Resolve extends using registry
    resolved_extends = []
    for ext in devbox_config.extends:
        if ext.startswith("@"):
            resolved = _resolve_registry_ref(ext, devbox_config.get_registry())
            resolved_extends.append(resolved)
        else:
            resolved_extends.append(ext)

    # Combine: extends first, then original flakes
    return tuple(resolved_extends) + flakes


def _compute_flake_lock_hash(flake_dir: Path) -> str | None:
    """Compute MD5 hash of flake.lock file.

    Args:
        flake_dir: Directory containing flake.nix

    Returns:
        MD5 hash string, or None if lock file doesn't exist or fails
    """
    try:
        subprocess.run(
            ["nix", "flake", "metadata", str(flake_dir)],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return None

    lock_path = flake_dir / "flake.lock"
    if not lock_path.exists():
        return None
    md5 = hashlib.md5()
    md5.update(lock_path.read_bytes())
    return md5.hexdigest()


def _execute_update(flakes: tuple[str, ...], verbose: bool) -> None:
    """Execute flake update for the given flake references."""
    devbox_config = find_config_in_directory(Path.cwd())
    flakes = _expand_extends(flakes, devbox_config)
    flake_refs = _resolve_flake_refs(flakes, devbox_config)

    version_info = VersionInfo.create(flake_refs)
    devbox_config = _load_devbox_config(flake_refs, devbox_config)

    mount_points: list[str] = []
    if devbox_config:
        for vol in devbox_config.run.volumes:
            parts = vol.split(":")
            if len(parts) >= 2:
                mount_points.append(parts[1])
        mount_points.extend(devbox_config.init.ensure_dirs)

    flake_content = generate_flake(
        flake_refs,
        ImageRef.parse("update-dev:latest"),
        version_info,
        mount_points if mount_points else None,
    )

    temp_dir = tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX)
    flake_path = Path(temp_dir) / "flake.nix"
    flake_path.write_text(flake_content)

    click.echo(f"Generated flake in: {temp_dir}")

    # Get lock hash before update
    old_hash = _compute_flake_lock_hash(Path(temp_dir))
    click.echo(f"flake.lock before update: {old_hash or '(none)'}")

    click.echo("Updating flake inputs...")
    try:
        result = subprocess.run(
            ["nix", "flake", "update", "--flake", temp_dir],
            capture_output=not verbose,
            text=True,
            check=True,
        )
        if verbose:
            click.echo(result.stdout)
    except subprocess.CalledProcessError as e:
        raise DevboxError(f"Failed to update flake: {e.stderr}") from e

    # Get lock hash after update
    new_hash = _compute_flake_lock_hash(Path(temp_dir))
    click.echo(f"flake.lock after update:  {new_hash or '(none)'}")

    if old_hash != new_hash:
        click.secho("✅ Flake inputs updated!", fg="green")
    else:
        click.secho("✅ Flake inputs are already up to date", fg="green")


@cli.command()
@click.argument("flakes", nargs=-1, required=False)
@click.option("-v", "--verbose", is_flag=True, help="Show verbose output")
@click.pass_context
def update(ctx: "Context", flakes: tuple[str, ...], verbose: bool) -> None:
    """Update flake inputs to the latest versions.

    \b
    Usage:
        nix-devbox update                  # Update current directory's flake
        nix-devbox update /path/to/flake  # Update specific flake
        nix-devbox update github:owner/repo  # Update remote flake

    \b
    This command generates a merged flake and runs 'nix flake update'
    in the generated flake directory.
    """
    if not flakes:
        flakes = (".",)

    try:
        _execute_update(flakes, verbose)
    except DevboxError as exc:
        raise click.ClickException(str(exc)) from exc


def _execute_build(
    flakes: tuple[str, ...],
    output: str,
    name: str | None,
    tag: str | None,
    verbose: bool,
    dry_run: bool = False,
) -> None:
    """Execute Docker image build with parsed arguments."""
    # Load devbox config first (for registry resolution and extends)
    devbox_config = find_config_in_directory(Path.cwd())

    # Expand extends if present
    flakes = _expand_extends(flakes, devbox_config)

    # Resolve flake refs (including registry references)
    flake_refs = _resolve_flake_refs(flakes, devbox_config)

    # Use configured image name as default if available
    actual_output = output() if callable(output) else output
    if devbox_config.image and not name and actual_output == _get_default_image_name():
        actual_output = devbox_config.image

    image_ref = ImageRef.parse(actual_output, name_override=name, tag_override=tag)

    version_info = VersionInfo.create(flake_refs)

    if verbose or dry_run:
        click.echo(format_flake_refs(flake_refs))

    # Reload devbox config with all flake configs
    devbox_config = _load_devbox_config(flake_refs, devbox_config)
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
        flake_refs,
        image_ref,
        version_info,
        verbose,
        dry_run,
        mount_points if mount_points else None,
    )


@cli.command()
@click.argument("flakes", nargs=-1, required=True)
@click.option(
    "-o",
    "--output",
    default=_get_default_image_name,
    help="Output image name and tag (default: <dirname>-dev:latest, or image from devbox.yaml)",
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


def _load_devbox_config(
    flake_refs: list[FlakeRef], base_config: DevboxConfig | None = None
) -> DevboxConfig:
    """Load and merge devbox configs from all flake directories and current directory.

    Configs are merged in order:
    1. First flake's config is the base
    2. Subsequent flake configs override/merge
    3. Current directory's devbox.yaml (if exists) takes highest priority
    4. Optional base_config is used as starting point (includes project registry)
    """
    fetcher = get_flake_fetcher()

    # Start with base config if provided
    configs = [base_config] if base_config else []

    # Load config from each flake directory
    for flake_ref in flake_refs:
        if flake_ref.uri.is_local:
            # Extract the actual path from path:/absolute/path format
            path_str = flake_ref.uri.url
            if path_str.startswith("path:"):
                path_str = path_str[5:]
            configs.append(find_config(Path(path_str) / "flake.nix"))
        else:
            # For remote URLs, fetch the flake and look for devbox.yaml
            try:
                flake_path = fetcher.fetch(flake_ref.uri.url)
                # If subdir is specified, look for devbox.yaml in the subdir
                if flake_ref.uri.subdir:
                    flake_path = flake_path / flake_ref.uri.subdir
                configs.append(find_config(flake_path / "flake.nix"))
            except (RuntimeError, FileNotFoundError) as e:
                # Log warning but don't fail - remote flake may not have devbox.yaml
                # FileNotFoundError: nix command not available (e.g., in dry-run mode without nix)
                logger.warning(f"Could not fetch remote flake {flake_ref.uri.url}: {e}")
                configs.append(DevboxConfig())

    # Load config from current directory (highest priority)
    current_dir_config = find_config_in_directory(Path.cwd())
    if current_dir_config != DevboxConfig():
        configs.append(current_dir_config)

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

    # Load devbox config first (for registry resolution and extends)
    devbox_config = find_config_in_directory(Path.cwd())

    # Expand extends if present
    flakes = _expand_extends(flakes, devbox_config)

    # Resolve flake refs (including registry references)
    flake_refs = _resolve_flake_refs(flakes, devbox_config)

    # Reload devbox config with all flake configs
    devbox_config = _load_devbox_config(flake_refs, devbox_config)

    # Use configured image name as default if available and no CLI override
    final_output = actual_output
    if devbox_config.image and not name and actual_output == _get_default_image_name():
        final_output = devbox_config.image

    version_info = VersionInfo.create(flake_refs)

    return ContainerLaunchConfig(
        image_ref=ImageRef.parse(final_output, name_override=name, tag_override=tag),
        flake_refs=flake_refs,
        version_info=version_info,
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

    # Skip image check/build in dry-run mode
    if not config.dry_run:
        _ensure_image_exists(
            flake_refs=config.flake_refs,
            image_ref=config.image_ref,
            version_info=config.version_info,
            force_rebuild=config.rebuild,
            verbose=config.verbose,
            mount_points=mount_points if mount_points else None,
        )
    _run_container_with_config(config)


@cli.command(
    context_settings=dict(
        allow_extra_args=True,
        allow_interspersed_args=False,
    )
)
@click.argument("flakes", nargs=-1, required=True)
@click.option(
    "-o",
    "--output",
    default=_get_default_image_name,
    help="Image name and tag (default: <dirname>-dev:latest, or image from devbox.yaml)",
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
) -> None:
    """Run container (auto-builds image if not exists).

    Use -- to pass arguments to the container command:
        nix-devbox run /path/to/flake -- ls -la
        nix-devbox run /path/to/flake -- python script.py
    """
    # With allow_interspersed_args=False, Click preserves -- in the positional args
    # So we can find -- in flakes and split there
    if "--" in flakes:
        sep_index = flakes.index("--")
        cmd_args = flakes[sep_index + 1 :]
        command = " ".join(cmd_args) if cmd_args else None
        actual_flakes = flakes[:sep_index]
    else:
        command = None
        actual_flakes = flakes

    if not actual_flakes:
        raise click.UsageError("At least one flake reference is required")

    config = _build_launch_config(
        flakes=actual_flakes,
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
    version_info: VersionInfo,
    force_rebuild: bool,
    verbose: bool,
    mount_points: list[str] | None = None,
) -> None:
    """Build image if needed."""
    if force_rebuild:
        click.echo(f"Force rebuilding image {image_ref}...")
        build_image_with_progress(
            flake_refs, image_ref, version_info, verbose, mount_points=mount_points
        )
        return

    if not image_exists(image_ref):
        click.echo(f"Image {image_ref} not found, building...")
        build_image_with_progress(
            flake_refs, image_ref, version_info, verbose, mount_points=mount_points
        )
        return

    labels = get_image_labels(image_ref)
    image_version = labels.get("dev.nixdevbox.version")
    image_commit = labels.get("dev.nixdevbox.commit")
    image_lock_hash = labels.get("dev.nixdevbox.lock_hash")

    local_lock_hash = _get_flake_lock_hash(
        flake_refs, image_ref, version_info, mount_points
    )

    diffs: list[str] = []

    if not image_version:
        diffs.append("version (missing)")
    elif image_version != version_info.version:
        diffs.append(f"version ({image_version} -> {version_info.version})")

    if not image_commit:
        diffs.append("commit (missing)")
    elif version_info.commit_sha and image_commit != version_info.commit_sha:
        diffs.append(f"commit ({image_commit} -> {version_info.commit_sha})")

    if not image_lock_hash:
        diffs.append("lock_hash (missing)")
    elif local_lock_hash and image_lock_hash != local_lock_hash:
        diffs.append(f"lock_hash ({image_lock_hash} -> {local_lock_hash})")

    if diffs:
        click.secho(
            f"⚠️  Image version mismatch detected:\n"
            f"    - Image built with: nix-devbox v{image_version or 'unknown'}, commit={image_commit or 'unknown'}, lock_hash={image_lock_hash or 'unknown'}\n"
            f"    - Current version:   nix-devbox v{version_info.version}, commit={version_info.commit_sha or 'unknown'}, lock_hash={local_lock_hash or 'unknown'}\n"
            f"    - Differences: {', '.join(diffs)}\n"
            f"\n"
            f"Run with --rebuild to rebuild the image.",
            fg="yellow",
        )
        return

    return


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
        file_config.tmpfs,
        [],
        parse_func=_parse_tmpfs,  # tmpfs only from config file
    )

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
