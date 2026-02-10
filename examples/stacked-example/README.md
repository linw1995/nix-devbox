# Stacked Example

**English** | [简体中文](README.zh-CN.md)

Demonstrates layering `base` + `opencode` configurations.

## Stack Layers

```
┌─────────────────────────────────────────────────────────┐
│  Layer 3: Your Project                                  │
│  └── ./          Overrides: memory 2g, ports 9000:9000  │
└─────────────────────────────────────────────────────────┘
                         ▲ merges with
┌─────────────────────────────────────────────────────────┐
│  Layer 2: opencode/      Volumes, Env                   │
└─────────────────────────────────────────────────────────┘
                         ▲ builds on
┌─────────────────────────────────────────────────────────┐
│  Layer 1: base/          Security, Resources, Logging   │
└─────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Run the demo
cd examples/stacked-example
./demo.sh
```

Or manually:

```bash
# See merged docker command
cd examples/stacked-example
nix-devbox run ../base ../opencode . --dry-run

# Run with all layers
nix-devbox run ../base ../opencode . -- nix develop
```

## What Gets Merged

| Config | Source | Result |
|--------|--------|--------|
| memory | base: 1g → local: 2g | **2g** |
| cpus | base: 2.0 | **2.0** (inherited) |
| cap_drop | base: ALL | **ALL** (inherited) |
| volumes | opencode: 3 mounts | **3 mounts** (inherited) |
| env | opencode: 2 vars | **2 vars** (inherited) |
| ports | local: 9000:9000 | **9000:9000** (added) |

## Files

- `devbox.yaml` - Override memory, add ports
- `demo.sh` - Run this to see the stack in action
