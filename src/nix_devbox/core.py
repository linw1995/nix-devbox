"""Core functionality for generating flake.nix content."""

from .models import FlakeRef, ImageRef

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
    # Collect all shells
    shells = [
<<SHELL_REFS>>
    ];

    # Create a merged shell derivation
    allBuildInputs = pkgs.lib.flatten (map (s: s.buildInputs or []) shells);
    allNativeBuildInputs = pkgs.lib.flatten (map (s: s.nativeBuildInputs or []) shells);

    mergedShellHook = pkgs.lib.concatStringsSep "\\n" (
      pkgs.lib.filter (x: x != "") (map (s: s.shellHook or "") shells)
    );

    mergedShell = pkgs.mkShell {
      buildInputs = allBuildInputs;
      nativeBuildInputs = allNativeBuildInputs;
      shellHook = mergedShellHook;
    };

    # Create entrypoint - use full paths for all commands
    # Uses buildNixShellImage's rcfile (finds it in /nix/store)
    entrypoint = pkgs.writeShellScriptBin "entrypoint" ''
      set -e

      # Get target UID/GID from environment (defaults to 1000:100)
      TARGET_UID="''${USER_ID:-1000}"
      TARGET_GID="''${GROUP_ID:-100}"

      # Ensure configured directories exist
      # These are directories that may not be explicitly mounted but are needed
      for dir in <<ENSURE_DIRS>>; do
        ${pkgs.coreutils}/bin/mkdir -p "$dir" 2>/dev/null || true
      done

      # Fix ownership of parent directories passed from cli.py
      # These are non-mounted directories that Docker may have auto-created as root
      CHOWN_PARENTS="''${DEVBOX_CHOWN_PARENTS:-}"
      if [ -n "$CHOWN_PARENTS" ]; then
        echo "$CHOWN_PARENTS" | tr ':' '\n' | while read -r path; do
          if [ -n "$path" ] && [ -d "$path" ]; then
            ${pkgs.coreutils}/bin/chown "$TARGET_UID:$TARGET_GID" "$path" 2>/dev/null || true
          fi
        done
      fi

      # Fix ownership of mount points under /build
      # Try to chown all directories under /build, but only succeed for
      # Docker-created directories (root-owned) or when we have permission
      for path in /build /build/* /build/*/*; do
        [ -e "$path" ] || continue
        # Attempt chown - if it fails (e.g., bind-mounted from host), that's fine
        ${pkgs.coreutils}/bin/chown "$TARGET_UID:$TARGET_GID" "$path" 2>/dev/null || true
      done

      # Always ensure /build itself is owned by target user
      ${pkgs.coreutils}/bin/chown "$TARGET_UID:$TARGET_GID" /build 2>/dev/null || true

      # Ensure target user exists in /etc/passwd and /etc/group
      if ! ${pkgs.gnugrep}/bin/grep -q "^nixbld:" /etc/group 2>/dev/null; then
        echo "nixbld:x:$TARGET_GID:" >> /etc/group
      fi
      if ! ${pkgs.gnugrep}/bin/grep -q "^nixbld:" /etc/passwd 2>/dev/null; then
        echo "nixbld:x:$TARGET_UID:$TARGET_GID::/build:/bin/bash" >> /etc/passwd
      fi

      # Find buildNixShellImage's rcfile
      rcfile=$(${pkgs.coreutils}/bin/ls /nix/store/*-nix-shell-rc 2>/dev/null | ${pkgs.coreutils}/bin/head -1)
      if [ -z "$rcfile" ]; then
        echo "Error: Could not find nix-shell-rc" >&2
        exit 1
      fi

      # Run as target user
      if [ $# -eq 0 ]; then
        exec ${pkgs.gosu}/bin/gosu "$TARGET_UID:$TARGET_GID" ${pkgs.bashInteractive}/bin/bash --rcfile "$rcfile"
      else
        # Execute command with rcfile sourced via BASH_ENV
        export BASH_ENV="$rcfile"
        exec ${pkgs.gosu}/bin/gosu "$TARGET_UID:$TARGET_GID" "$@"
      fi
    '';

    # Build base image using buildNixShellImage (full devshell environment)
    baseImage = pkgs.dockerTools.buildNixShellImage {
      drv = mergedShell;
      name = "<<NAME>>-base";
      tag = "<<TAG>>";
      uid = 1000;
      gid = 100;
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
      contents = [
        entrypoint
        pkgs.gosu
        pkgs.gnugrep
      ];
      config = {
        Entrypoint = [ "/bin/entrypoint" ];
        Cmd = [];
        User = "root";
        WorkingDir = "/build";
        Env = [
          "HOME=/build"
          "USER_ID=1000"
          "GROUP_ID=100"
        ];
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


def generate_flake(
    flake_refs: list[FlakeRef],
    image_ref: ImageRef,
    ensure_dirs: list[str] | None = None,
) -> str:
    """Generate flake.nix content from flake references."""
    if not flake_refs:
        raise ValueError("At least one flake reference is required")

    # Default directories to ensure exist
    default_dirs = ["/build"]
    ensure_dirs = ensure_dirs or []
    all_dirs = default_dirs + ensure_dirs
    dirs_str = " ".join(f'"{d}"' for d in all_dirs)

    lines = [_FLAKE_HEADER]
    lines.extend(_generate_inputs_section(flake_refs))
    lines.append("")

    inputs_args = _generate_inputs_args(flake_refs)
    lines.append(_FLAKE_OUTPUTS_START.format(inputs=inputs_args))
    lines.extend(_FLAKE_LET_START.split("\n"))
    lines.append("")

    lines.extend(_generate_shell_definitions(flake_refs))

    # Use string replace instead of format to avoid escaping issues
    image_package = _FLAKE_IMAGE_PACKAGE_TEMPLATE
    image_package = image_package.replace(
        "<<SHELL_REFS>>", _generate_shell_refs(flake_refs)
    )
    image_package = image_package.replace("<<NAME>>", image_ref.name)
    image_package = image_package.replace("<<TAG>>", image_ref.tag)
    image_package = image_package.replace("<<ENSURE_DIRS>>", dirs_str)

    lines.append(image_package)

    return "\n".join(lines)
