# nix-devbox

**English** | [简体中文](README.zh-CN.md)

Merge multiple flake devShells, build Docker images, and run containers.

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
```

See [docs/configuration.md](docs/configuration.md) for configuration options.

## Examples

See [examples/](examples/) directory for example configurations.

## Dependencies

- Python >= 3.9
- Nix (with flakes)
- Docker

## License

MIT
