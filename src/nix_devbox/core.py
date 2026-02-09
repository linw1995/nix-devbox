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
_FLAKE_COMPOSED_SHELL_START = """
    composedShell = pkgs.mkShell {
      inputsFrom = ["""
_FLAKE_COMPOSED_SHELL_END = """      ];
    };"""
_FLAKE_IMAGE_PACKAGE = """
  in {{
    packages.${{system}}.image = pkgs.dockerTools.buildNixShellImage {{
      name = "{name}";
      tag = "{tag}";
      drv = composedShell;
    }};
  }};
}}"""


def _generate_inputs_section(flake_refs: list[FlakeRef]) -> list[str]:
    """Generate the inputs section of flake.nix."""
    lines = [_FLAKE_INPUTS_START]
    for i, ref in enumerate(flake_refs):
        lines.append(f'    proj{i}.url = "path:{ref.path}";')
    lines.append(_FLAKE_INPUTS_END)
    return lines


def _generate_shell_definitions(flake_refs: list[FlakeRef]) -> list[str]:
    """Generate shell variable definitions."""
    lines = []
    for i, ref in enumerate(flake_refs):
        lines.append(f"    shell{i} = proj{i}.{ref.shell};")
    return lines


def _generate_inputs_args(flake_refs: list[FlakeRef]) -> str:
    """Generate the inputs arguments for outputs function."""
    base_args = ["self", "nixpkgs"]
    proj_args = [f"proj{i}" for i in range(len(flake_refs))]
    return ", ".join(base_args + proj_args)


def _generate_inputs_from(flake_refs: list[FlakeRef]) -> list[str]:
    """Generate the inputsFrom list for composed shell."""
    return [f"        shell{i}" for i in range(len(flake_refs))]


def generate_flake(flake_refs: list[FlakeRef], image_ref: ImageRef) -> str:
    """
    Generate flake.nix content from flake references.

    Args:
        flake_refs: List of flake references to merge
        image_ref: Image name and tag reference

    Returns:
        Generated flake.nix content as string
    """
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
    lines.append(_FLAKE_COMPOSED_SHELL_START)
    lines.extend(_generate_inputs_from(flake_refs))
    lines.append(_FLAKE_COMPOSED_SHELL_END)

    lines.append(
        _FLAKE_IMAGE_PACKAGE.format(name=image_ref.name, tag=image_ref.tag)
    )

    return "\n".join(lines)
