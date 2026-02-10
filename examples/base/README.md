# Base Example

**English** | [简体中文](README.zh-CN.md)

Basic nix-devbox example demonstrating `devbox.yaml` configuration.

## Files

- `flake.nix` - Nix flake definition
- `devbox.yaml` - Runtime configuration

## Usage

```bash
# Build image
nix-devbox build .

# Run container (with config)
nix-devbox run .

# Show docker commands
nix-devbox run . --dry-run
```

## Configuration

See [docs/configuration.md](../../docs/configuration.md).
