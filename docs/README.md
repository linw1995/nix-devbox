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

## Flake References

nix-devbox supports various flake URL formats:

### Local Paths

```bash
# Absolute or relative paths (auto-converted to path: format)
nix-devbox build /path/to/project
nix-devbox build ./my-project
nix-devbox build ../projects/app
```

### Remote URLs

```bash
# GitHub repositories
github:owner/repo
github:owner/repo/main
github:owner/repo/v1.0.0
github:owner/repo?dir=subdir

# GitLab
gitlab:owner/repo
gitlab:owner/repo/branch

# Git with HTTPS
git+https://github.com/owner/repo
git+https://github.com/owner/repo?ref=main

# HTTP/HTTPS tarballs
https://example.com/flake.tar.gz

# Other supported schemes
sourcehut:~owner/repo
hg+https://example.com/repo
```

### Subdirectory Support

For flakes located in a subdirectory of a repository:

```bash
nix-devbox build "github:owner/repo?dir=dev"
```

The `dir` parameter specifies the subdirectory containing `flake.nix`.

### Shell Selection

Append `#shellname` to select a specific devShell:

```bash
# Local path with custom shell
nix-devbox build ./project#nodejs

# Remote URL with custom shell
nix-devbox build "github:NixOS/nixpkgs#hello"

# Full attribute path
nix-devbox build ./project#devShells.x86_64-linux.custom
```

### Remote devbox.yaml

When using remote URLs, nix-devbox automatically fetches the flake and reads any `devbox.yaml` configuration from it. This works transparently with the config merge feature.
