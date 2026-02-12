"""Core functionality for generating flake.nix content."""

from .models import DEFAULT_WORKDIR, FlakeRef, ImageRef

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

      # Find buildNixShellImage's rcfile
      rcfile=$(${pkgs.coreutils}/bin/ls /nix/store/*-nix-shell-rc 2>/dev/null | ${pkgs.coreutils}/bin/head -1)
      if [ -z "$rcfile" ]; then
        echo "Error: Could not find nix-shell-rc" >&2
        exit 1
      fi

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
    # Use buildImage (non-layered) to avoid layer count issues with fromImage
    # buildNixShellImage can use many layers, and adding more layers on top
    # can exceed Docker's 127 layer limit. buildImage creates a single layer.
    image = pkgs.dockerTools.buildImage {
      name = "<<NAME>>";
      tag = "<<TAG>>";
      fromImage = baseImage;
      contents = [ entrypoint pkgs.gosu ];
      # Create mount point directories with correct ownership
      # This ensures volumes can be mounted properly at runtime
      extraCommands = ''
        <<EXTRA_COMMANDS>>
      '';
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


def _generate_extra_commands(mount_points: list[str], uid: int, gid: int) -> str:
    """Generate extraCommands script to create mount point directories.

    These commands run at image build time to create directories
    that will be used as volume mount points.

    Args:
        mount_points: List of directory paths to create
        uid: User ID for directory ownership
        gid: Group ID for directory ownership

    Returns:
        Shell script content for extraCommands
    """
    if not mount_points:
        return ""

    lines = ["# Create mount point directories with correct ownership"]
    for path in mount_points:
        # Normalize path and ensure it starts with /
        normalized = path.strip()
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        # Use mkdir -p to create parent directories if needed
        lines.append(f"mkdir -p '.{normalized}'")
        lines.append(f"chown {uid}:{gid} '.{normalized}'")

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

    # Collect mount points: user-specified + default workdir
    all_mount_points = list(mount_points) if mount_points else []
    if DEFAULT_WORKDIR not in all_mount_points:
        all_mount_points.append(DEFAULT_WORKDIR)

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
