"""Core functionality for generating flake.nix content."""

from pathlib import Path

from .models import (
    DEFAULT_WORKDIR,
    RESERVED_PATHS,
    FlakeRef,
    ImageRef,
)

# flake.nix template constants
_FLAKE_HEADER = "{"
_FLAKE_INPUTS_START = """  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";"""
_FLAKE_INPUTS_END = "  };"
_FLAKE_OUTPUTS_START = "  outputs = {{ {inputs} }}:"
_FLAKE_LET_START = """  let
    system = builtins.currentSystem;
    pkgs = import nixpkgs { inherit system; };"""

_FLAKE_IMAGE_PACKAGE_TEMPLATE = """
    # Create a merged shell derivation
    mergedShell = pkgs.mkShell {
      inputsFrom = [
<<SHELL_REFS>>
      ];
    };

    # Create entrypoint - use full paths for all commands
    entrypoint = pkgs.writeShellScriptBin "entrypoint" ''
      set -e

      # Enable debug output if NIX_DEVBOX_DEBUG is set
      if [ -n "''${NIX_DEVBOX_DEBUG:-}" ]; then
        ${pkgs.coreutils}/bin/echo "=== Nix Devbox Debug Mode ===" >&2
        ${pkgs.coreutils}/bin/echo "Current user: $(${pkgs.coreutils}/bin/id)" >&2
        ${pkgs.coreutils}/bin/echo "Arguments: $*" >&2
        ${pkgs.coreutils}/bin/echo "HOME: ''${HOME:-}" >&2
        ${pkgs.coreutils}/bin/ls -la / >&2
        ${pkgs.coreutils}/bin/echo "============================" >&2
      fi

      # Find buildNixShellImage's rcfile
      rcfile=$(${pkgs.coreutils}/bin/ls /nix/store/*-nix-shell-rc 2>/dev/null | ${pkgs.coreutils}/bin/head -1)
      if [ -z "$rcfile" ]; then
        ${pkgs.coreutils}/bin/echo "Error: Could not find nix-shell-rc" >&2
        exit 1
      fi

      # Modify passwd to use /home instead of /build (runtime fix)
      ${pkgs.gnused}/bin/sed -i 's|/build|/home|g' /etc/passwd 2>/dev/null || true

      # Run as the same uid/gid used during build
      if [ $# -eq 0 ]; then
        exec ${pkgs.gosu}/bin/gosu <<UID>>:<<GID>> ${pkgs.bashInteractive}/bin/bash --rcfile "$rcfile"
      else
        exec ${pkgs.gosu}/bin/gosu <<UID>>:<<GID>> "$@"
      fi
    '';

    # Build base image using buildNixShellImage (full devshell environment)
    baseImage = pkgs.dockerTools.buildNixShellImage {
      drv = mergedShell;
      name = "<<NAME>>-base";
      tag = "<<TAG>>";
      uid = <<UID>>;
      gid = <<GID>>;
      homeDirectory = "/build";
    };

    # Create final image with entrypoint
    # Use buildLayeredImage to properly support fromImage with fakeRootCommands
    # fakeRootCommands runs in fakeroot environment, allowing chown without VM
    image = pkgs.dockerTools.buildLayeredImage {
      name = "<<NAME>>";
      tag = "<<TAG>>";
      fromImage = baseImage;
      contents = [ entrypoint ];
      # Create mount point directories with correct ownership
      fakeRootCommands = ''
        <<EXTRA_COMMANDS>>
      '';
      # Increase maxLayers to accommodate baseImage layers + new layer
      maxLayers = 125;
      config = {
        Entrypoint = [ "/bin/entrypoint" ];
        Cmd = [];
        WorkingDir = "<<WORKDIR>>";
      };
    };
  in {
    packages.${system}.image = image;
  };
}"""


def _generate_shell_refs(flake_refs: list[FlakeRef]) -> str:
    """Generate shell references for the shells list."""
    return "\n".join(f"      shell{i}" for i in range(len(flake_refs)))


def _generate_inputs_section(flake_refs: list[FlakeRef]) -> list[str]:
    """Generate the inputs section of flake.nix."""
    proj_inputs = [
        f'    proj{i}.url = "path:{ref.path}";' for i, ref in enumerate(flake_refs)
    ]
    return [_FLAKE_INPUTS_START, *proj_inputs, _FLAKE_INPUTS_END]


def _generate_shell_definitions(flake_refs: list[FlakeRef]) -> list[str]:
    """Generate shell variable definitions."""
    return [f"    shell{i} = proj{i}.{ref.shell};" for i, ref in enumerate(flake_refs)]


def _generate_inputs_args(flake_refs: list[FlakeRef]) -> str:
    """Generate the inputs arguments for outputs function."""
    base_args = ["self", "nixpkgs"]
    proj_args = [f"proj{i}" for i in range(len(flake_refs))]
    return ", ".join(base_args + proj_args)


def _collect_parent_directories(paths: list[str]) -> list[str]:
    """Collect parent directories of the given paths (excluding the paths themselves).

    Args:
        paths: List of directory paths

    Returns:
        Sorted list of unique parent directories, sorted by depth
    """
    all_parents: set[str] = set()

    for path in paths:
        # Normalize path and ensure it starts with /
        normalized = path.strip()
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"

        # Get parent directories only (exclude the target directory itself)
        parent = str(Path(normalized).parent)
        while parent and parent != "/":
            all_parents.add(parent)
            parent = str(Path(parent).parent)

    # Sort by depth (shorter paths first) to ensure parent dirs are created first
    return sorted(all_parents, key=lambda x: (x.count("/"), x))


def _validate_mount_point(path: str) -> str:
    """Validate user mount point path.

    Returns the path unchanged if valid, raises error if conflicts
    with Nix reserved paths.

    Args:
        path: User-specified mount point path

    Returns:
        The original path (unchanged)

    Raises:
        ValueError: If path is under RESERVED_PATHS
    """
    normalized = path.strip()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"

    for reserved in RESERVED_PATHS:
        if normalized == reserved or normalized.startswith(f"{reserved}/"):
            raise ValueError(
                f"Mount point '{path}' conflicts with reserved path '{reserved}'."
            )

    return path


def _generate_extra_commands(mount_points: list[str], uid: int, gid: int) -> str:
    """Generate fakeRootCommands script to create mount point directories.

    These commands run at image build time in a fakeroot environment
    to create directories that will be used as volume mount points.

    Note: /build is reserved for Nix internal use (buildNixShellImage's
    homeDirectory) and should not be created/modified here.

    Args:
        mount_points: List of directory paths to create
        uid: User ID for directory ownership
        gid: Group ID for directory ownership

    Returns:
        Shell script content for fakeRootCommands
    """
    if not mount_points:
        return ""

    # Collect parent directories only (mount points themselves are created by docker)
    all_dirs = _collect_parent_directories(mount_points)

    lines = [
        "# Create mount point directories with correct ownership",
        "echo '=== fakeRootCommands START ===' >&2",
    ]

    for dir_path in all_dirs:
        # Skip /tmp (needs special permissions 1777)
        # Skip /build itself (already created by buildNixShellImage with special permissions)
        if dir_path == "/tmp" or dir_path == "/build":
            continue

        # Create directory and set ownership (chown works in fakeroot)
        lines.append(f"echo 'Create directory {dir_path}' >&2")
        lines.append(f"mkdir -p '.{dir_path}' >&2")
        lines.append(f"chown {uid}:{gid} '.{dir_path}' >&2")

    lines.append("echo '=== fakeRootCommands END ===' >&2")

    return "\n        ".join(lines)


def generate_flake(
    flake_refs: list[FlakeRef],
    image_ref: ImageRef,
    mount_points: list[str] | None = None,
) -> str:
    """Generate flake.nix content from flake references."""
    if not flake_refs:
        raise ValueError("At least one flake reference is required")

    lines = [_FLAKE_HEADER]
    lines.extend(_generate_inputs_section(flake_refs))
    lines.append("")

    inputs_args = _generate_inputs_args(flake_refs)
    lines.append(_FLAKE_OUTPUTS_START.format(inputs=inputs_args))
    lines.extend(_FLAKE_LET_START.split("\n"))
    lines.append("")

    lines.extend(_generate_shell_definitions(flake_refs))

    # Get UID/GID from current runtime environment
    import os as _os

    uid = _os.getuid()
    gid = _os.getgid()
    uid_str = str(uid)
    gid_str = str(gid)

    # Collect and validate mount points
    all_mount_points = list(mount_points) if mount_points else []
    if DEFAULT_WORKDIR not in all_mount_points:
        all_mount_points.append(DEFAULT_WORKDIR)

    # Validate mount points (raises error if conflicts with RESERVED_PATHS)
    for p in all_mount_points:
        _validate_mount_point(p)

    # Generate extraCommands script for creating mount points
    extra_commands = _generate_extra_commands(all_mount_points, uid, gid)

    # Use string replace instead of format to avoid escaping issues
    image_package = _FLAKE_IMAGE_PACKAGE_TEMPLATE
    image_package = image_package.replace(
        "<<SHELL_REFS>>", _generate_shell_refs(flake_refs)
    )
    image_package = image_package.replace("<<NAME>>", image_ref.name)
    image_package = image_package.replace("<<TAG>>", image_ref.tag)
    image_package = image_package.replace("<<UID>>", uid_str)
    image_package = image_package.replace("<<GID>>", gid_str)
    image_package = image_package.replace("<<WORKDIR>>", DEFAULT_WORKDIR)
    image_package = image_package.replace("<<EXTRA_COMMANDS>>", extra_commands)

    lines.append(image_package)

    return "\n".join(lines)
