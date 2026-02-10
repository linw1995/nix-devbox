# nix-devbox Documentation

**English** | [简体中文](README.zh-CN.md)

## Contents

- [configuration.md](./configuration.md) - `devbox.yaml` configuration reference

## Quick Start

```bash
# Enter example directory
cd examples/base

# Build image
nix-devbox build .

# Run container
nix-devbox run .
```

## Configuration Location

Place `devbox.yaml` in project root or any flake directory:

```
project/
├── flake.nix
└── devbox.yaml
```

For multiple projects, configurations are merged in load order.
