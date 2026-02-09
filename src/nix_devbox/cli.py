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
    lines = ["将要合并的 devShell:"]
    for i, ref in enumerate(refs, 1):
        lines.append(f"  {i}. {ref.path} -> {ref.shell}")
    lines.append("")
    return "\n".join(lines)


def _echo_build_start(image_ref: ImageRef) -> None:
    """Display build start message."""
    click.echo(f"开始构建镜像 {image_ref}...")


def _echo_build_complete(image_ref: ImageRef) -> None:
    """Display build completion message."""
    click.echo()
    click.secho(f"✅ 镜像构建完成: {image_ref}", fg="green")


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
    Nix devbox - 合并多个 flake 的 devShell，构建并运行 Docker 容器

    \b
    使用示例:
        # 构建镜像
        nix-devbox build /path/to/project1

        # 构建并运行
        nix-devbox run /path/to/project1

    \b
    支持的 flake-ref 格式:
        /path/to/flake              - 使用 default devShell
        /path/to/flake#shellname    - 使用指定的 devShell
        /path/to/flake#devShells.x86_64-linux.shellname - 完整属性路径
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.argument("flakes", nargs=-1, required=True)
@click.option(
    "-o",
    "--output",
    default=DEFAULT_IMAGE,
    help="输出镜像名称和标签 (默认: devbox:latest)",
    metavar="name:tag",
)
@click.option("-n", "--name", help="输出镜像名称 (覆盖 --output 中的名称)")
@click.option("-t", "--tag", help="输出镜像标签 (覆盖 --output 中的标签)")
@click.option("-v", "--verbose", is_flag=True, help="显示详细信息")
@click.pass_context
def build(
    ctx: "Context",
    flakes: tuple[str, ...],
    output: str,
    name: str | None,
    tag: str | None,
    verbose: bool,
) -> None:
    """构建 Docker 镜像。"""
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
    help="镜像名称和标签 (默认: devbox:latest)",
    metavar="name:tag",
)
@click.option("-n", "--name", help="镜像名称 (覆盖 --output 中的名称)")
@click.option("-t", "--tag", help="镜像标签 (覆盖 --output 中的标签)")
@click.option("--container-name", help="容器名称")
@click.option(
    "-p", "--port", multiple=True, help="端口映射 (可多次使用，如: -p 8080:80)"
)
@click.option(
    "--volume",
    "-V",
    multiple=True,
    help="卷挂载 (可多次使用，如: -V /host:/container)",
)
@click.option(
    "-e", "--env", multiple=True, help="环境变量 (可多次使用，如: -e KEY=value)"
)
@click.option("-w", "--workdir", help="工作目录")
@click.option("-d", "--detach", is_flag=True, help="后台运行容器")
@click.option("--no-rm", is_flag=True, help="停止后不自动删除容器")
@click.option("--rebuild", is_flag=True, help="强制重新构建镜像")
@click.option("--dry-run", is_flag=True, help="只显示要执行的命令，不实际运行")
@click.option("--verbose", "-v", is_flag=True, help="显示详细信息")
@click.option("--cmd", help="要在容器中执行的命令 (用引号包裹)")
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
    """运行容器（自动构建镜像如果不存在）。"""
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
        click.echo(f"强制重新构建镜像 {image_ref}...")
        build_image_with_progress(flake_refs, image_ref, verbose)
        return

    if image_exists(image_ref):
        return

    click.echo(f"镜像 {image_ref} 不存在，开始构建...")
    build_image_with_progress(flake_refs, image_ref, verbose)


def _run_container_with_config(config: RunConfig) -> None:
    """Run container with the specified configuration."""
    if config.dry_run:
        click.echo("模拟运行容器...")
    else:
        click.echo(f"启动容器 {config.image_ref}...")

    extra_args = ["--dry-run"] if config.dry_run else []

    run_container(
        config.image_ref,
        command=shlex.split(config.cmd) if config.cmd else None,
        ports=list(config.ports),
        volumes=list(config.volumes),
        env=list(config.env),
        container_name=config.container_name,
        rm=not config.no_rm,
        interactive=not config.detach,
        tty=not config.detach,
        workdir=config.workdir,
        detach=config.detach,
        extra_args=extra_args,
        verbose=config.verbose,
    )

    if not config.detach and not config.dry_run:
        click.echo()
        click.secho("✅ 容器已停止", fg="green")


if __name__ == "__main__":
    cli()
