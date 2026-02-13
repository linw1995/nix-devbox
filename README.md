# nix-devbox

**English** | [简体中文](README.zh-CN.md)

Merge multiple flake devShells into reproducible Docker images for consistent development environments.

## Installation

```bash
uv tool install nix-devbox
```

### Development

```bash
uv venv
uv pip install -e .
```

## Usage

```bash
# Build image
nix-devbox build /path/to/project

# Run container (auto-builds if needed)
nix-devbox run /path/to/project

# Merge multiple devShells
nix-devbox build /path/to/proj1 /path/to/proj2#nodejs

# Build from remote GitHub repository
nix-devbox build github:owner/repo

# Build from remote with subdirectory
nix-devbox build "github:owner/repo?dir=dev"
```

See [docs/configuration.md](docs/configuration.md) for configuration options.

## Use Cases

### YOLO Coding Agent Development Environment

Provide a safe and stable sandboxed development environment for AI coding agents (like Claude Code, OpenCode, etc.).

**Key benefits:**

- **Reproducible environments** - Exact same toolchain versions across all agent sessions
- **Isolated workspaces** - Each project runs in its own container without polluting the host system
- **Declarative configuration** - Define all dependencies in `flake.nix`, no manual setup needed
- **Multi-language support** - Easily combine devShells for different tech stacks

**Quick start for agent development:**

```bash
# 1. Recommended: Learn to write your own flake devShells
#    (see: https://nix.dev/tutorials/first-steps/declarative-shell)
#    Or use the pre-built devShells from this project:
nix-devbox run @nix-devbox/base

# 2. Or stack multiple devShells for complex projects
nix-devbox run @nix-devbox/base @nix-devbox/opencode

# 3. The agent now has a clean, reproducible environment
# with all tools pre-installed and configured
```

If your project has a `flake.nix`, append `.` to use it. For project-specific configuration (environment variables, workdir, etc.), create a `devbox.yaml` in your project root. See [docs/configuration.md](docs/configuration.md) for details.

See [examples/stacked-example/](examples/stacked-example/) for a complete stacked devShell setup. Check out [examples/opencode/](examples/opencode/) for the OpenCode agent configuration and contribute your own agent examples!

## Examples

See [examples/](examples/) directory for example configurations.

## Dependencies

- Python >= 3.9
- Nix (with flakes)
- Docker

## License

MIT
