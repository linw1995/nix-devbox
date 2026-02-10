# Opencode Example

**English** | [简体中文](README.zh-CN.md)

Example for running [Opencode](https://opencode.ai/) AI coding agent in a containerized environment.

## Features

- Isolated opencode config in container
- Persistent data via volume mounts
- tmpfs for temporary files

## Usage

```bash
# Build and run
nix-devbox run .

# With custom args
nix-devbox run . -- /path/to/project
```

## Files

- `flake.nix` - Nix flake with opencode package
- `devbox.yaml` - Container runtime config

## Configuration

See [docs/configuration.md](../../docs/configuration.md).
