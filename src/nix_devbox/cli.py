"""CLI interface using Click."""

import shlex
import tempfile
from dataclasses import dataclass
from typing import TYPE_CHECKING

import click

from .builder import build_image, image_exists, run_container
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
class RunConfig:
    """Configuration for running a container."""

    image_ref: ImageRef
    flake_refs: list[FlakeRef]
    container_name: str | None = None
    ports: tuple[str, ...] = ()
    volumes: tuple[str, ...] = ()
    env: tuple[str, ...] = ()
    workdir: str | None = None
    detach: bool = False
    no_rm: bool = False
    rebuild: bool = False
    dry_run: bool = False
    verbose: bool = False
    cmd: str | None = None


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

    with tempfile.TemporaryDirectory(prefix=TEMP_DIR_PREFIX) as tmp_dir:
        _echo_build_start(image_ref)
        build_image(flake_content, image_ref, tmp_dir, verbose)
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

    if verbose:
        click.echo(format_flake_refs(flake_refs))

    try:
        build_image_with_progress(flake_refs, image_ref, verbose)
    except DevboxError as exc:
        raise click.ClickException(str(exc)) from exc


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
@click.option("-d", "--detach", is_flag=True, help="Run container in background")
@click.option("--no-rm", is_flag=True, help="Do not remove container after it stops")
@click.option("--rebuild", is_flag=True, help="Force rebuild image")
@click.option("--dry-run", is_flag=True, help="Show commands without executing")
@click.option("--verbose", "-v", is_flag=True, help="Show verbose output")
@click.option("--cmd", help="Command to execute in container (quote it)")
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
    detach: bool,
    no_rm: bool,
    rebuild: bool,
    dry_run: bool,
    verbose: bool,
    cmd: str | None,
) -> None:
    """Run container (auto-builds image if not exists)."""
    config = RunConfig(
        image_ref=ImageRef.parse(output, name_override=name, tag_override=tag),
        flake_refs=[FlakeRef.parse(ref) for ref in flakes],
        container_name=container_name,
        ports=port,
        volumes=volume,
        env=env,
        workdir=workdir,
        detach=detach,
        no_rm=no_rm,
        rebuild=rebuild,
        dry_run=dry_run,
        verbose=verbose,
        cmd=cmd,
    )

    if config.verbose:
        click.echo(format_flake_refs(config.flake_refs))

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


def _run_container_with_config(config: RunConfig) -> None:
    """Run container with the specified configuration."""
    if config.dry_run:
        click.echo("Commands to be executed:")
    else:
        click.echo(f"Starting container {config.image_ref}...")

    parsed_cmd = shlex.split(config.cmd) if config.cmd else None
    run_container(
        config.image_ref,
        command=parsed_cmd,
        ports=list(config.ports),
        volumes=list(config.volumes),
        env=list(config.env),
        container_name=config.container_name,
        rm=not config.no_rm,
        interactive=not config.detach,
        tty=not config.detach,
        workdir=config.workdir,
        detach=config.detach,
        dry_run=config.dry_run,
        verbose=config.verbose,
    )

    if not config.detach and not config.dry_run:
        click.echo()
        click.secho("✅ Container stopped", fg="green")


if __name__ == "__main__":
    cli()
