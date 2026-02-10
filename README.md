# nix-devbox

**English** | [简体中文](README.zh-CN.md)

Merge multiple flake devShells, build Docker images, and run containers.

## Installation

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
```

## Command Options

| Option | Description |
|--------|-------------|
| `-o, --output name:tag` | Image name and tag |
| `-p, --port` | Port mapping |
| `-V, --volume` | Volume mount |
| `-e, --env` | Environment variable |
| `-w, --workdir` | Working directory |
| `--rebuild` | Force rebuild |
| `--dry-run` | Dry run (show commands only) |
| `-v, --verbose` | Verbose output |

## Dependencies

- Python >= 3.9
- Nix (with flakes)
- Docker
